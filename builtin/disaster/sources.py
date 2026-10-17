"""灾害预警插件的数据源层。

三个数据源（均免 key）：
- 地震主源：ICL 成都高新减灾研究所  mobile-new.chinaeew.cn（秒级，含逐县烈度/倒计时）
- 地震备源：Wolfx  open API  api.wolfx.jp（四川/台网/福建/重庆 多源，速报列表补漏）
- 气象灾害：中央气象台  www.nmc.cn/rest/findAlarm（按中文省名过滤）

设计要点：
- 全部异步（QNetworkAccessManager），回调在 GUI 线程；不新增线程
- **每个请求都设 setTransferTimeout**（主程序 weather 插件缺此项）
- 同源单飞保护（tag 在途时不重复发），失败记录到 SourceStatus 并指数退避
- 解析函数是**纯函数**（不碰 Qt），便于离线单测；逐字段 .get 容错，
  兼容 Wolfx 的 `Magnitude/Magunitude`、ICL 的 `sations` 等历史拼写
"""
import json
import math
import re
import time
import calendar
from urllib.parse import quote

from PySide6.QtCore import QUrl
from PySide6.QtNetwork import (QNetworkAccessManager, QNetworkRequest,
                              QNetworkReply)

UA = "ClassBoard-DisasterAlert/1.0"
TIMEOUT_MS = 8000
BJ_OFFSET = 8 * 3600          # 北京时间固定 UTC+8

# ---------- 端点 ----------
ICL_LIST_URL = ("https://mobile-new.chinaeew.cn/v1/earlywarnings"
                "?updates=0&start_at={start_ms}")
ICL_DETAIL_URL = "https://mobile-new.chinaeew.cn/v1/earlywarnings/{eid}"
WOLFX_EEW_URLS = {
    "wolfx_sc": "https://api.wolfx.jp/sc_eew.json",
    "wolfx_cenc": "https://api.wolfx.jp/cenc_eew.json",
    "wolfx_fj": "https://api.wolfx.jp/fj_eew.json",
    "wolfx_cq": "https://api.wolfx.jp/cq_eew.json",
}
WOLFX_EQLIST_URL = "https://api.wolfx.jp/cenc_eqlist.json"
# nmc.cn 的 province 参数用 **UTF-8 百分号编码**（与官网前端一致）；
# 且必须带 `X-Requested-With: XMLHttpRequest`，否则其前置网关会返回
# HTTP 417 Expectation Failed（实测）
NMC_LIST_URL = ("http://www.nmc.cn/rest/findAlarm"
                "?pageNo=1&pageSize=50&signaltype=&signallevel=&province={province}")
# 兜底：不带省过滤的全国列表（本地再按省名过滤标题）
NMC_NATIONWIDE_URL = ("http://www.nmc.cn/rest/findAlarm"
                      "?pageNo=1&pageSize=200&signaltype=&signallevel=&province=")
NMC_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "http://www.nmc.cn/publish/alarm.html",
}


def nmc_url(province):
    return NMC_LIST_URL.format(province=quote(province or "", safe=""))

_inflight = set()


# ---------------- 源状态 ----------------
class SourceStatus:
    """单个数据源的可用性 / 退避状态。"""

    def __init__(self, key, label):
        self.key = key
        self.label = label
        self.ok = None          # None=未用过
        self.fail = 0
        self.last_ok_ts = 0.0
        self.last_err = ""
        self.next_retry_ts = 0.0
        self.enabled = True

    def on_ok(self, now=None):
        now = time.time() if now is None else now
        self.ok = True
        self.fail = 0
        self.last_ok_ts = now
        self.next_retry_ts = 0.0
        self.last_err = ""

    def on_fail(self, err, now=None):
        now = time.time() if now is None else now
        self.ok = False
        self.fail += 1
        self.last_err = str(err)[:80]
        self.next_retry_ts = now + min(60.0, (2 ** min(self.fail, 5)) * 2.5)

    def ready(self, now=None):
        if not self.enabled:
            return False
        now = time.time() if now is None else now
        return now >= self.next_retry_ts

    def describe(self, now=None):
        now = time.time() if now is None else now
        if not self.enabled:
            return f"{self.label} 未启用"
        if self.ok is None:
            return f"{self.label} 等待首次请求"
        if self.ok:
            age = int(max(0, now - self.last_ok_ts))
            return f"{self.label} 正常（{age}s前）"
        return f"{self.label} 失败×{self.fail}"


# ---------------- 请求 ----------------
def make_manager():
    return QNetworkAccessManager()


def request_json(nam, url, on_ok, on_fail, tag=None, timeout_ms=TIMEOUT_MS,
                 headers=None):
    """异步 GET JSON。返回是否真正发出请求（单飞：同 tag 在途则跳过）。"""
    if nam is None:
        on_fail("网络管理器未初始化")
        return False
    if tag is not None and tag in _inflight:
        return False

    try:
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.UserAgentHeader, UA)
        req.setRawHeader(b"Accept", b"application/json, text/html;q=0.8")
        for k, v in (headers or {}).items():
            req.setRawHeader(str(k).encode("ascii", "ignore"),
                             str(v).encode("utf-8"))
        req.setTransferTimeout(int(timeout_ms))    # 关键：防长挂
        reply = nam.get(req)
    except Exception as e:
        on_fail(f"请求构造失败: {e}")
        return False

    if tag is not None:
        _inflight.add(tag)

    def _done():
        try:
            if tag is not None:
                _inflight.discard(tag)
            if reply.error() != QNetworkReply.NoError:
                on_fail(reply.errorString() or f"网络错误 {int(reply.error())}")
                return
            raw = bytes(reply.readAll())
            if not raw.strip():
                on_fail("空响应")
                return
            # 编码回退：部分国内接口返回 GBK（如 pconline 的 IP 归属地）
            data = None
            err = ""
            for enc in ("utf-8", "gbk", "gb18030"):
                try:
                    data = json.loads(raw.decode(enc))
                    break
                except Exception as e:
                    data = None
                    err = str(e)
            if data is None:
                on_fail("响应不是有效 JSON（%s）" % err[:60])
                return
            on_ok(data)
        except Exception as e:
            try:
                on_fail(f"回调异常: {e}")
            except Exception:
                pass
        finally:
            try:
                reply.deleteLater()
            except Exception:
                pass

    reply.finished.connect(_done)
    return True


# ---------------- 解析工具 ----------------
def _f(v, default=None):
    if v is None:
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return f


def _s(v, default=""):
    if v is None:
        return default
    return str(v).strip()


def parse_bj_time(text, default=None):
    """把 "YYYY-MM-DD HH:MM:SS" / "YYYY/MM/DD HH:MM" 按北京时间解析成 epoch 秒。"""
    t = _s(text)
    if not t:
        return default
    m = re.match(
        r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?",
        t)
    if not m:
        return default
    y, mo, d, h, mi = (int(m.group(i)) for i in range(1, 6))
    sec = int(m.group(6) or 0)
    try:
        return calendar.timegm((y, mo, d, h, mi, sec, 0, 0, 0)) - BJ_OFFSET
    except Exception:
        return default


def _ms_to_epoch(v):
    """毫秒时间戳 -> epoch 秒。"""
    x = _f(v)
    if x is None or x <= 0:
        return None
    return x / 1000.0 if x > 1e11 else x


# ---------------- 地震：ICL ----------------
def parse_icl_events(payload):
    """ICL 列表 / 详情 -> 归一化地震事件列表。"""
    items = []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = [data]
        elif isinstance(data.get("eventId"), (int, str)):
            items = [data]
    elif isinstance(payload, list):
        items = payload

    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        eid = it.get("eventId", it.get("event_id"))
        lat = _f(it.get("latitude"))
        lon = _f(it.get("longitude"))
        mag = _f(it.get("magnitude"))
        origin = _ms_to_epoch(it.get("startAt"))
        if eid in (None, "") or lat is None or lon is None \
                or mag is None or origin is None:
            continue
        eid = str(eid)
        counties = it.get("counties") if isinstance(it.get("counties"), list) \
            else None
        out.append({
            "kind": "quake",
            "uid": f"icl:{eid}",
            "source": "icl",
            "event_id": eid,
            "revision": int(_f(it.get("updates"), 1) or 1),
            "origin_ts": origin,
            "updated_ts": _ms_to_epoch(it.get("updateAt")) or origin,
            "lat": lat,
            "lon": lon,
            "depth": _f(it.get("depth"), 0.0) or 0.0,
            "magnitude": mag,
            "epicenter": _s(it.get("epicenter"), "未知震中"),
            "max_intensity": _f(it.get("epiIntensity")),
            "report_count": None,
            "counties": counties,
        })
    return out


def parse_icl_detail(payload, event_id):
    """ICL 详情 -> counties 列表（逐县距离/烈度/倒计时）。"""
    rows = []
    try:
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            return rows
        for c in (data.get("counties") or []):
            if not isinstance(c, dict):
                continue
            rows.append({
                "name": _s(c.get("name")),
                "full_name": _s(c.get("full_name"), _s(c.get("name"))),
                "city": _s(c.get("city")),
                "distance": _f(c.get("distance")),
                "intensity": _f(c.get("intensity")),
                "countdown": _f(c.get("countdown")),
            })
    except Exception:
        return []
    return rows


# ---------------- 地震：Wolfx ----------------
def parse_wolfx_events(payload, source_key):
    """Wolfx EEW / 速报 -> 归一化地震事件列表（兼容多种字段拼写）。"""
    items = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("list", "data", "Data", "events"):
            v = payload.get(key)
            if isinstance(v, list):
                items = v
                break
        if not items:
            items = [payload]
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        eid = it.get("EventID", it.get("eventId", it.get("ID",
                                                         it.get("id"))))
        lat = _f(it.get("Latitude", it.get("latitude", it.get("lat"))))
        lon = _f(it.get("Longitude", it.get("longitude", it.get("lon"))))
        mag = _f(it.get("Magnitude", it.get("Magunitude",
                                           it.get("mag", it.get("magnitude")))))
        origin = (parse_bj_time(it.get("OriginTime") or it.get("time")
                                or it.get("ReportTime"))
                  or _ms_to_epoch(it.get("startAt")))
        if lat is None or lon is None or mag is None or origin is None:
            continue
        if eid in (None, ""):
            eid = f"{lat:.3f},{lon:.3f},{int(origin)}"
        eid = str(eid)
        out.append({
            "kind": "quake",
            "uid": f"{source_key}:{eid}",
            "source": source_key,
            "event_id": eid,
            "revision": int(_f(it.get("ReportNum", it.get("update", 1)), 1) or 1),
            "origin_ts": origin,
            "updated_ts": parse_bj_time(it.get("ReportTime"), origin) or origin,
            "lat": lat,
            "lon": lon,
            "depth": _f(it.get("Depth", it.get("depth")), 0.0) or 0.0,
            "magnitude": mag,
            "epicenter": _s(it.get("HypoCenter", it.get("location",
                                                        it.get("place"))),
                            "未知震中"),
            "max_intensity": _f(it.get("MaxIntensity", it.get("intensity"))),
            "report_count": int(_f(it.get("ReportNum"), 0) or 0) or None,
            "counties": None,
        })
    return out


# ---------------- 气象：nmc.cn ----------------
_LEVEL_WORDS = (("红色", "red"), ("橙色", "orange"),
                ("黄色", "yellow"), ("蓝色", "blue"))
_SIGNAL_RE = re.compile(
    r"发布(.+?)(红色|橙色|黄色|蓝色)预警信号")


def parse_nmc_alerts(payload, province="", strict=False):
    """中央气象台预警列表 -> 归一化气象灾害事件。

    strict=True 时只保留标题以 province 开头的条目（用于全国列表兜底时的本地过滤）。
    """
    out = []
    try:
        data = payload.get("data") if isinstance(payload, dict) else None
        page = data.get("page") if isinstance(data, dict) else None
        items = (page or {}).get("list") if isinstance(page, dict) else None
    except Exception:
        items = None
    if not isinstance(items, list):
        return out

    for it in items:
        if not isinstance(it, dict):
            continue
        aid = _s(it.get("alertid"))
        title = _s(it.get("title"))
        if not aid or not title:
            continue
        if strict and province and not title.startswith(province):
            continue
        level = "blue"
        for word, lv in _LEVEL_WORDS:
            if word in title:
                level = lv
                break
        m = _SIGNAL_RE.search(title)
        signal = _s(m.group(1)) if m else ""
        if not signal:
            signal = title

        county = ""
        head = title.split("发布")[0] if "发布" in title else ""
        if head:
            county = head
            if province and county.startswith(province):
                county = county[len(province):]
            else:
                # 跨省/未配置省份时，通用剥离省级前缀（省/自治区/特别行政区）
                m2 = re.match(r"^(.{2,10}?(?:省|自治区|特别行政区))", county)
                if m2:
                    county = county[m2.end():]
        county = county.replace("气象台", "").replace("气象", "").strip()

        out.append({
            "kind": "weather",
            "uid": f"nmc:{aid}",
            "alert_id": aid,
            "issued_ts": parse_bj_time(it.get("issuetime")),
            "title": title,
            "signal": signal,
            "level": level,
            "province": province,
            "county": county,
            "url": _s(it.get("url")),
        })
    return out


def weather_stat(payload):
    """返回 {red, orange, yellow, blue, total}（来自 nmc 的 stat 字段，可选）。"""
    try:
        stat = (payload.get("data") or {}).get("stat") or {}
        agg = {"r": 0, "o": 0, "y": 0, "b": 0}
        for scope in ("province", "city", "county"):
            for k in agg:
                agg[k] += int((stat.get(scope) or {}).get(k) or 0)
        return {
            "red": agg["r"],
            "orange": agg["o"],
            "yellow": agg["y"],
            "blue": agg["b"],
            "total": agg["r"] + agg["o"] + agg["y"] + agg["b"],
        }
    except Exception:
        return {"red": 0, "orange": 0, "yellow": 0, "blue": 0, "total": 0}


# ---------------- 去重合并 ----------------
def _same_quake(a, b):
    """无相同 event_id 时，用位置/时间/震级近似判定同一地震。"""
    if a["event_id"] and b["event_id"] and a["event_id"] == b["event_id"]:
        return True
    return (abs(a["lat"] - b["lat"]) <= 0.5
            and abs(a["lon"] - b["lon"]) <= 0.5
            and abs(a["magnitude"] - b["magnitude"]) <= 0.5
            and abs(a["origin_ts"] - b["origin_ts"]) <= 60)


def merge_quakes(existing, incoming, max_items=8):
    """把新到达的事件合并进既有集合（按 uid / 近似判定去重，revision 大者胜）。

    返回 (merged_dict, new_or_updated_list)。
    """
    merged = dict(existing or {})
    changed = []

    for ev in incoming or []:
        hit_key = None
        if ev["uid"] in merged:
            hit_key = ev["uid"]
        else:
            for k, old in merged.items():
                if _same_quake(old, ev):
                    hit_key = k
                    break
        if hit_key is None:
            merged[ev["uid"]] = ev
            changed.append(ev)
            continue

        old = merged[hit_key]
        old_rev = int(old.get("revision", 0) or 0)
        new_rev = int(ev.get("revision", 0) or 0)
        newer = (new_rev > old_rev
                 or (new_rev == old_rev
                     and float(ev.get("updated_ts", 0) or 0)
                     > float(old.get("updated_ts", 0) or 0)))
        if newer:
            # 保持事件身份稳定：跨源命中同一地震时不改变 uid，
            # 避免 uid 在 ICL/Wolfx 之间漂移导致重复提醒
            ev["uid"] = hit_key
            ev["counties"] = ev.get("counties") or old.get("counties")
            merged[hit_key] = ev
            changed.append(ev)

    if len(merged) > max_items:
        ordered = sorted(merged.items(),
                         key=lambda kv: kv[1].get("origin_ts", 0),
                         reverse=True)
        merged = dict(ordered[:max_items])

    return merged, changed


def prune_quakes(events, now=None, max_age=180.0):
    """清理过期地震事件（发震超过 max_age 秒）。"""
    now = time.time() if now is None else now
    return {k: v for k, v in (events or {}).items()
            if now - float(v.get("origin_ts") or 0) <= max_age}


def prune_weather(events, now=None, max_age=86400.0):
    now = time.time() if now is None else now
    return {k: v for k, v in (events or {}).items()
            if v.get("issued_ts") is None
            or now - float(v["issued_ts"]) <= max_age}
