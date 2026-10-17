"""灾害预警插件（地震预警 + 气象灾害）。

- 地震：ICL（成都高新减灾研究所，主源）→ Wolfx（多源，备源）
  本地视角计算：Haversine 震中距 + 烈度公式 + 深度分档查表得到
  「横波还有 N 秒到达」倒计时；算法见 quake_calc.py（移植自参考项目）
- 气象灾害：中央气象台 nmc.cn（按中文省名过滤）
- 显示：主岛加长片段（priority 11，压过媒体插件的 10）+ 副岛 + 下拉面板
- 提醒：api.notify（首次触发 / 等级升级 / 超过节流间隔）；纯视觉，无声音
- 上课策略：地震照常提醒；气象蓝/黄等级上课期间静默（可在设置页关闭）

所有网络请求为异步且带 8s 超时；失败保留旧缓存并指数退避。
"""
import os
import re
import sys
import json
import time
import tempfile
import importlib
import importlib.util

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLabel, QCheckBox, QComboBox, QSpinBox,
                               QDoubleSpinBox, QLineEdit, QPushButton,
                               QCompleter, QColorDialog)

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
from builtin.data import builtin_dir as _builtin_dir  # noqa: E402
_BUILTIN_DIR = _builtin_dir('disaster')
_CONFIG_PATH = os.path.join(_BUILTIN_DIR, 'config.json')
_CACHE_PATH = os.path.join(_BUILTIN_DIR, 'cache.json')


def _load_sibling(name):
    """加载同目录模块。

    插件是用 importlib 按**文件路径**加载的，插件目录并不在 sys.path 上，
    因此不能直接 `import sources`。这里按文件路径加载，并用带插件前缀的
    唯一模块名，避免与其他插件同名的模块（如各自的 sources.py）冲突；
    若同名模块已从**同一文件**加载过（开发/测试场景），则复用同一对象，
    以保证模块身份一致（副岛的 draw 依赖 id 稳定）。
    """
    path = os.path.abspath(os.path.join(_PLUGIN_DIR, name + ".py"))
    mod = sys.modules.get(name)
    if mod is not None:
        f = getattr(mod, "__file__", None)
        if f and os.path.abspath(f) == path:
            return mod
    uniq = "disaster_alert_" + name
    if uniq in sys.modules:
        return sys.modules[uniq]
    spec = importlib.util.spec_from_file_location(uniq, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[uniq] = m
    spec.loader.exec_module(m)
    return m


quake_calc = _load_sibling("quake_calc")
qc = quake_calc
sources = _load_sibling("sources")
src = sources
draw = _load_sibling("draw")
cities = _load_sibling("cities")   # 全国省 / 地级市 / 区县 + 经纬度

GEO_URL = "https://ipwho.is/"
# 中文 IP 定位（返回中文省/市 + 经纬度）；失败再退回 ipwho.is
GEO_URL_CN = "http://ip-api.com/json/?lang=zh-CN"
# 国内库（中文省/市全名，GBK 响应，无经纬度）—— 对中国 IP 通常比国外库准
GEO_URL_PCONLINE = "https://whois.pconline.com.cn/ipJson.jsp?json=true"

# 定位源优先级（越小越可信）：国内库 > ipwho > ip-api
GEO_PRIORITY = {"pconline": 0, "ipwho": 1, "ipapi": 2}
GEO_TIMEOUT_MS = 6000

CITY_SUFFIXES = ("特别行政区", "自治州", "自治县", "自治区", "地区", "市", "盟", "州")

PROVINCES = [
    "北京市", "天津市", "河北省", "山西省", "内蒙古自治区", "辽宁省", "吉林省",
    "黑龙江省", "上海市", "江苏省", "浙江省", "安徽省", "福建省", "江西省",
    "山东省", "河南省", "湖北省", "湖南省", "广东省", "广西壮族自治区",
    "海南省", "重庆市", "四川省", "贵州省", "云南省", "西藏自治区", "陕西省",
    "甘肃省", "青海省", "宁夏回族自治区", "新疆维吾尔自治区",
    "香港特别行政区", "澳门特别行政区", "台湾省",
]

# ipwho.is 的 region（英文）-> 中文省名，用于 IP 定位后自动选省份
_REGION_MAP = {
    "beijing": "北京市", "tianjin": "天津市", "hebei": "河北省",
    "shanxi": "山西省", "inner mongolia": "内蒙古自治区", "liaoning": "辽宁省",
    "jilin": "吉林省", "heilongjiang": "黑龙江省", "shanghai": "上海市",
    "jiangsu": "江苏省", "zhejiang": "浙江省", "anhui": "安徽省",
    "fujian": "福建省", "jiangxi": "江西省", "shandong": "山东省",
    "henan": "河南省", "hubei": "湖北省", "hunan": "湖南省",
    "guangdong": "广东省", "guangxi": "广西壮族自治区", "hainan": "海南省",
    "chongqing": "重庆市", "sichuan": "四川省", "guizhou": "贵州省",
    "yunnan": "云南省", "tibet": "西藏自治区", "xizang": "西藏自治区",
    "shaanxi": "陕西省", "gansu": "甘肃省", "qinghai": "青海省",
    "ningxia": "宁夏回族自治区", "xinjiang": "新疆维吾尔自治区",
    "hong kong": "香港特别行政区", "macau": "澳门特别行政区",
    "taiwan": "台湾省",
}

PROVINCE_NONE = "（不获取气象）"

# 文本显示宽度上限（超出部分由 draw 的跑马灯滚动展示）
EXTRA_TEXT_MAX_W = 200
SUB_TEXT_MAX_W = 190

_DEFAULTS = {
    "quake_enabled": True,
    "weather_enabled": True,
    "lat": None,
    "lon": None,
    "province": "四川省",
    "city": "",              # 本市名称（如 成都市）；填写后气象预警只显示本市
    "district": "",          # 区县（可选）：只用于精确定位与演练震中
    "threshold": 2.0,
    "quake_interval_sec": 5,
    "weather_interval_sec": 60,
    "throttle_sec": 30,
    "weather_min_level": "yellow",
    "use_subisland": True,
    "silent_low_weather_in_class": True,
    "notify_enabled": True,
    "show_status_card": True,
    # —— 预估烈度 -> 颜色分档（默认地震预警行业色标：≤2 蓝 / 3 黄 / 4-5 橙 / ≥6 红）——
    "level_thresholds": [2.0, 3.0, 5.0],
    "level_colors": {
        "blue": "#4da3ff", "yellow": "#ffd23f",
        "orange": "#ff9f0a", "red": "#ff453a",
    },
    # —— 演练参数（震中 + 震级 + 深度）——
    "drill_province": "",
    "drill_city": "",
    "drill_district": "",
    "drill_magnitude": 6.0,
    "drill_depth": 10.0,
    # —— 重要 / 一般预警的展示策略 ——
    "force_show": True,             # 重要预警强制弹出（无视上课/全屏/PPT 隐藏）
    "force_hold_sec": 60,           # 强制显示至少保持多少秒
    "important_signals": "台风,地震,海啸",
    "important_min_level": "red",   # 达到此等级也算重要（none=不启用）
    "normal_only_free_time": True,  # 一般预警只在课间与自习显示
    "normal_no_subisland": True,    # 一般预警不占用副岛
    # —— 地震警报条（主岛 + 副岛融合） ——
    "banner_enabled": True,         # 地震时用一条红色倒计时警报条取代课程显示
    # —— 避险要诀（第二层，向下拓展一排）——
    "show_safety_tips": True,
    "safety_tips": "伏地 · 遮挡 · 手抓牢 ｜ 远离窗玻璃与吊灯，勿乘电梯、勿跳楼",
    "tips_min_level": "red",        # 达到该等级才展开要诀（默认红色档）
    "tips_hold_sec": 60,            # 第一层保持多少秒后消失（只留要诀）
    "require_confirm": True,        # 需点击灵动岛→确认才恢复上课显示
    "confirm_timeout_sec": 5,       # 只点一次后多少秒退回要诀（0=不超时）
    # —— 小震：只短暂占用（顶掉课程 N 秒后自动交还，倒计时继续在主岛片段上显示）——
    "small_quake_hold_sec": 5,      # 0 = 小震完全不占用警报条
}

_state = {
    "config": dict(_DEFAULTS),
    "api": None,
    "nam": None,
    "quakes": {},          # uid -> event
    "weather": {},         # uid -> event
    "focus": None,         # 当前主展示的评估结果
    "others": [],          # 其余待展示（面板用）
    "notified": {},        # uid -> (monotonic 时间戳, 等级)
    "detail_done": set(),  # 已请求过详情的 (event_id, revision)
    "drill": None,         # 演练事件
    "banner_ok": False,    # 宿主是否支持紧急警报条（register 时探测）
    "banner_dismissed": None,   # 用户已确认收起的事件 (uid, revision)
    "banner_since_key": None,   # 计时对应的 (uid, revision)
    "banner_since": 0.0,        # 本次警报条开始占用的时刻（monotonic）
    "status": {},          # key -> SourceStatus
    "in_class": False,
    "weather_stat": None,
    "last_quake_poll": 0.0,
    "last_weather_poll": 0.0,
    "last_wolfx_poll": 0.0,
    "wolfx_rr": 0,
    "wolfx_fail": 0,
    "last_cache_save": 0.0,
    "cache_dirty": False,
    "geo_pending": False,
}


def _now():
    return time.time()


# ---------------- 配置文件 ----------------
def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def _write_json(path, data):
    """原子写（临时文件 + os.replace），避免崩溃损坏配置。"""
    folder = os.path.dirname(path) or "."
    try:
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as e:
        print("[DisasterAlert] 写文件失败:", e)
        return False


def _load_config():
    cfg = dict(_DEFAULTS)
    saved = _load_json(_CONFIG_PATH, {})
    for k, v in saved.items():
        if k in cfg:
            cfg[k] = v
    return cfg


def _save_config():
    _write_json(_CONFIG_PATH, _state["config"])


def _load_cache():
    data = _load_json(_CACHE_PATH, {})
    try:
        q = data.get("quake") or {}
        events = q.get("events") or []
        _state["quakes"] = {e["uid"]: e for e in events
                            if isinstance(e, dict) and e.get("uid")}
    except Exception:
        _state["quakes"] = {}


def _save_cache(force=False):
    now = _now()
    if not force and not _state["cache_dirty"]:
        return
    if not force and now - _state["last_cache_save"] < 30:
        return
    payload = {
        "quake": {
            "events": list(_state["quakes"].values())[-8:],
            "fetched_ts": now,
        },
        "saved_ts": now,
    }
    if _write_json(_CACHE_PATH, payload):
        _state["last_cache_save"] = now
        _state["cache_dirty"] = False


# ---------------- 派生计算 / 选主 ----------------
def _normalize_province(name):
    """把 '四川' / '四川省' / 'Sichuan' / 'Sichuan Sheng' 归一化成 PROVINCES 里的中文全名。"""
    n = (name or "").strip()
    if not n:
        return ""
    if n in PROVINCES:
        return n
    for p in PROVINCES:
        if p.startswith(n) or n.startswith(p[:2]):
            return p
    # 英文（ipwho.is 会返回 "Sichuan Sheng" 这种带后缀的写法）
    low = n.lower().strip()
    for drop in (" sheng", " shi", " province", " municipality",
                 " autonomous region", " zizhiqu"):
        if low.endswith(drop):
            low = low[: -len(drop)].strip()
    if low in _REGION_MAP:
        return _REGION_MAP[low]
    for k, v in _REGION_MAP.items():
        if len(low) >= 4 and (low.startswith(k) or k.startswith(low)):
            return v
    return ""


def _city_key(city):
    """取城市用于标题匹配的关键词（去掉后缀后取前两字，如 成都市→成都、阿坝藏族羌族自治州→阿坝）。"""
    c = (city or "").strip()
    if not c:
        return ""
    for suf in CITY_SUFFIXES:
        if c.endswith(suf) and len(c) > len(suf):
            c = c[: -len(suf)]
            break
    return c[:2] if len(c) >= 2 else c


def _important_signals():
    """重要预警类型关键词列表（逗号/顿号/空格分隔）。"""
    raw = str(_state["config"].get("important_signals") or "")
    return [s for s in re.split(r"[,，、;；\s]+", raw) if s]


def _weather_tier(ev):
    """气象预警分级：'important'（台风/地震等严重，或达到重要等级）/ 'normal'。

    - 类型命中「重要类型」关键词（可自定义，默认 台风/地震/海啸）
    - 或等级达到「重要等级门槛」（默认 红色；设为"不启用"则只看类型）
    """
    cfg = _state["config"]
    sig = str(ev.get("signal") or "")
    title = str(ev.get("title") or "")
    for s in _important_signals():
        if s in sig or s in title:
            return "important"
    min_lv = str(cfg.get("important_min_level") or "red")
    if min_lv != "none" and qc.LEVEL_RANK.get(ev.get("level"), 0) \
            >= qc.LEVEL_RANK.get(min_lv, 3):
        return "important"
    return "normal"


def _is_free_time():
    """是否处于「下课 / 自习」时段（一般预警只在这时展示）。

    自习 = 当前正在上的课名里含"自习"（含晚自习）；非上课中（课间/课后/假期）也算。
    """
    api = _state.get("api")
    if api is None:
        return True
    try:
        st = api.get_schedule_status()
    except Exception:
        st = None
    if not st:
        return True
    if st.get("status") == "ongoing":
        return "自习" in str(st.get("course") or "")
    return True


# ---------------- IP 定位（多源交叉） ----------------
def _s(v, default=""):
    if v is None:
        return default
    return str(v).strip()


def _fnum(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f


def _geo_parse(source, data):
    """各定位源响应 -> (province, city, lat, lon)；不可用返回 None。"""
    if not isinstance(data, dict):
        return None
    if source == "pconline":
        # 国内库：pro=四川省 city=资阳市（GBK 响应，已由请求层解码）
        prov = _s(data.get("pro"))
        city = _s(data.get("city"))
        if not prov and not city:
            return None
        return (prov, city, None, None)
    if source == "ipwho":
        return (_normalize_province(_s(data.get("region"))),
                _s(data.get("city")),
                _fnum(data.get("latitude")), _fnum(data.get("longitude")))
    # ipapi（lang=zh-CN）：regionName 形如 "四川"（无"省"后缀）
    return (_normalize_province(_s(data.get("regionName")) or _s(data.get("region"))),
            _s(data.get("city")),
            _fnum(data.get("lat")), _fnum(data.get("lon")))


def _is_cn(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))


def _geo_vote(probes):
    """多源定位合并（不同库对同一 IP 可能给出不同城市）。

    - 省份：按归一化中文省份**投票**，多数胜出
    - 城市：取与胜出省份一致、且优先级最高的来源（国内库优先 → 中文全名更可靠）
    - 坐标：优先取"城市与胜出城市一致"的来源，否则退回同省份来源
    - conflict：中文本土源之间城市不一致时置真（提示用户确认）
    """
    entries = []
    for name, val in (probes or {}).items():
        if not val:
            continue
        prov, city, la, lo = val
        entries.append((name, prov, city, la, lo))
    if not entries:
        return None
    entries.sort(key=lambda e: GEO_PRIORITY.get(e[0], 9))

    prov_votes = {}
    for e in entries:
        if e[1]:
            prov_votes[e[1]] = prov_votes.get(e[1], 0) + 1
    province = (sorted(prov_votes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
                if prov_votes else "")

    same = [e for e in entries if not province or not e[1] or e[1] == province]
    city = next((e[2] for e in same if e[2]), "")
    chosen_key = _city_key(city) if city else ""

    def pick_coord(cands):
        """三级优先：① 中文城市与胜出城市一致 → ② 非中文城市（跨语言无法比对，
        取优先级最高的，如 ipwho 的 Ziyang ≈ 资阳）→ ③ 同省份任意来源。"""
        for e in cands:
            if e[3] is None and e[4] is None:
                continue
            if chosen_key and e[2] and _is_cn(e[2]) \
                    and _city_key(e[2]) == chosen_key:
                return e[3], e[4]
        for e in cands:
            if e[3] is None and e[4] is None:
                continue
            if e[2] and not _is_cn(e[2]):
                return e[3], e[4]
        for e in cands:
            if e[3] is not None or e[4] is not None:
                return e[3], e[4]
        return None, None

    lat, lon = pick_coord(same)
    if lat is None and lon is None:
        lat, lon = pick_coord(entries)

    cn_keys = {_city_key(e[2]) for e in same if e[2] and _is_cn(e[2])}
    return {
        "province": province,
        "city": city,
        "lat": lat,
        "lon": lon,
        "conflict": len(cn_keys) > 1,
        "sources": [e[0] for e in same],
    }


def _weather_split(now):
    """按城市/等级/分级/时段过滤后，拆成 (本市预警, 省内其他预警)。"""
    cfg = _state["config"]
    if not cfg.get("weather_enabled", True):
        return [], []
    if not cfg.get("province") or cfg.get("province") == PROVINCE_NONE:
        return [], []
    low = cfg.get("weather_min_level", "yellow")
    key = _city_key(cfg.get("city"))
    free = _is_free_time()
    local, others = [], []
    for ev in _state["weather"].values():
        if not qc.level_at_least(ev.get("level"), low):
            continue
        tier = _weather_tier(ev)
        if tier == "normal":
            # 上课期间低等级静默（地震/台风等重要预警不受此限）
            if (_state["in_class"]
                    and cfg.get("silent_low_weather_in_class", True)
                    and ev.get("level") in ("blue", "yellow")):
                continue
            # 一般预警只在课间与自习展示
            if cfg.get("normal_only_free_time", True) and not free:
                continue
        if key and key in (ev.get("title") or ""):
            local.append(ev)
        else:
            others.append(ev)

    def order(lst):
        return sorted(lst, key=lambda e: (
            0 if _weather_tier(e) == "important" else 1,
            -qc.LEVEL_RANK.get(e.get("level"), 0),
            -(e.get("issued_ts") or 0)))
    return order(local), order(others)


def _weather_active(now):
    """本插件在主岛/副岛展示的气象预警：设了城市则只展示本市。"""
    local, others = _weather_split(now)
    if local:
        return local
    if _city_key(_state["config"].get("city")):
        return []           # 已设置城市：本市无预警就不占岛（省内其他只在面板列出）
    return others           # 未设置城市：保持省级展示


def _evaluate_quakes(now):
    cfg = _state["config"]
    if not cfg.get("quake_enabled", True):
        return []
    lat, lon = cfg.get("lat"), cfg.get("lon")
    if lat is None or lon is None:
        return []
    events = list(_state["quakes"].values())
    if _state["drill"]:
        events.append(_state["drill"])
    out = []
    for ev in events:
        r = qc.evaluate(ev, lat, lon, now, cfg.get("threshold", 2.0),
                    thresholds=cfg.get("level_thresholds"))
        if r and r.get("displayable"):
            r["event"] = ev
            out.append(r)
    out.sort(key=lambda e: (0 if e["triggered"] else 1,
                            -e["local_intensity"],
                            e["remain_sec"]))
    return out


def _refresh_focus(now=None):
    """重新评估所有事件、决定主展示对象、刷新绘制视图并（按节流）提醒。"""
    now = _now() if now is None else now
    quakes = _evaluate_quakes(now)
    focus = quakes[0] if quakes else None
    others = quakes[1:5]

    if focus is None:
        local, prov_others = _weather_split(now)
        has_city = bool(_city_key(_state["config"].get("city")))
        pool = local if local else ([] if has_city else prov_others)
        if pool:
            focus = {"kind": "weather", "event": pool[0],
                     "level": pool[0].get("level") or "yellow",
                     "triggered": True}
            others = [{"kind": "weather", "event": w} for w in pool[1:4]]
        # 面板里额外列出"省内其他"（设置了本市时才有意义）
        exclude = pool[0] if pool else None
        _state["weather_others"] = (
            [w for w in prov_others if w is not exclude][:3] if has_city else [])

    _state["focus"] = focus
    _state["others"] = others

    _sync_draw_view(focus)
    _maybe_notify(focus, now)
    return focus


def _sync_draw_view(focus):
    """把当前焦点整理成 draw 模块需要的精简视图。"""
    if focus is None:
        draw.clear_view()
        return
    cfg = _state["config"]
    if focus.get("kind") == "quake":
        ev = focus.get("event") or {}
        mag = ev.get("magnitude") or 0
        place = (ev.get("epicenter") or "未知震中")
        short = place[-2:] if len(place) > 2 else place
        inten = focus.get("local_intensity") or 0
        extra_n = len(_state["others"]) if _state["others"] else 0
        suffix = f" ·+{extra_n}" if extra_n else ""
        if focus.get("phase") == "incoming":
            sec = max(0, int(round(focus.get("remain_sec") or 0)))
            main = f"横波还有 {sec} 秒 · 预估烈度{inten:g}"
            sub = f"M{mag:g} {short} · 预估烈度{inten:g} · {sec}s{suffix}"
            pulse = True
        else:
            main = f"横波已到达 · 预估烈度{inten:g}"
            sub = f"M{mag:g} {short} · 已到达{suffix}"
            pulse = False
        draw.update_view(kind="quake", level=focus.get("level"),
                         main=main, sub=sub, icon="quake", pulse=pulse,
                         colors=_state["config"].get("level_colors"))
    else:
        ev = focus.get("event") or {}
        lv = focus.get("level") or "yellow"
        name = qc.level_word(lv)
        sig = ev.get("signal") or "预警"
        county = ev.get("county") or ev.get("province") or ""
        n = len(_state["others"]) + 1
        suffix = f" ·+{n - 1}" if n > 1 else ""
        draw.update_view(kind="weather", level=lv,
                         main=f"{sig}{name}",
                         sub=f"{sig}{name} · {county}{suffix}",
                         icon="weather", pulse=False,
                         colors=cfg.get("level_colors"))


def _notify(text, force=False):
    """弹提醒条；宿主不支持 force 参数时自动降级为普通提醒（保证不丢提醒）。"""
    api = _state.get("api")
    if api is None:
        return False
    try:
        api.notify(text, force=bool(force))
        return True
    except TypeError:
        try:
            api.notify(text)
            return True
        except Exception:
            return False
    except Exception:
        return False


def _maybe_notify(focus, now):
    cfg = _state["config"]
    api = _state.get("api")
    if api is None or not cfg.get("notify_enabled", True) or focus is None:
        return
    uid = (focus.get("event") or {}).get("uid")
    if not uid:
        return

    if focus.get("kind") == "quake":
        if not focus.get("triggered"):
            return
        level = focus.get("level")
        last = _state["notified"].get(uid)
        throttle = max(5, int(cfg.get("throttle_sec", 30)))
        if last is not None:
            last_t, last_lv = last
            upgraded = qc.LEVEL_RANK.get(level, 0) > qc.LEVEL_RANK.get(
                last_lv, 0)
            if not upgraded and now - last_t < throttle:
                return
        ev = focus.get("event") or {}
        sec = max(0, int(round(focus.get("remain_sec") or 0)))
        # 地震：强制弹出（无视上课/PPT 全屏导致的灵动岛隐藏）
        if not _notify(f"⚠️ {ev.get('epicenter', '')} "
                       f"M{ev.get('magnitude', 0):g} · 横波还有 {sec} 秒",
                       force=bool(cfg.get("force_show", True))):
            return
        _state["notified"][uid] = (now, level)
    else:
        # 气象：仅首次出现的中高等级（橙/红）提醒
        lv = focus.get("level") or "yellow"
        if qc.LEVEL_RANK.get(lv, 0) < qc.LEVEL_RANK.get("orange", 2):
            return
        if uid in _state["notified"]:
            return
        ev = focus.get("event") or {}
        # 台风/地震等重要类型才强制弹出；暴雨高温等一般预警安静提醒
        force = (bool(cfg.get("force_show", True))
                 and _weather_tier(ev) == "important")
        if not _notify(f"⚠️ {ev.get('county', '')}{ev.get('signal', '')}"
                       f"{qc.level_word(lv)}预警", force=force):
            return
        _state["notified"][uid] = (now, lv)

    _prune_seen()


def _prune_seen():
    live = set(_state["quakes"].keys()) | set(_state["weather"].keys())
    if _state["drill"]:
        live.add(_state["drill"]["uid"])
    for k in list(_state["notified"].keys()):
        if k not in live:
            _state["notified"].pop(k, None)


# ---------------- 轮询 ----------------
def _status(key, label):
    st = _state["status"].get(key)
    if st is None:
        st = _state["status"][key] = src.SourceStatus(key, label)
    return st


def _tick():
    """每秒执行：课表状态、轮询调度、重新评估、刷新显示。"""
    api = _state.get("api")
    now = _now()
    try:
        _state["in_class"] = bool(api.is_in_class()) if api else False
    except Exception:
        _state["in_class"] = False

    cfg = _state["config"]
    if cfg.get("quake_enabled", True):
        if _state["wolfx_fail"] >= 2:
            _poll_wolfx(now)
        else:
            _poll_icl(now)
    if cfg.get("weather_enabled", True) and cfg.get("province") \
            and cfg.get("province") != PROVINCE_NONE:
        _poll_weather(now)

    _refresh_focus(now)
    _save_cache()


def _poll_icl(now):
    st = _status("icl", "ICL")
    interval = max(3, int(_state["config"].get("quake_interval_sec", 5)))
    if now - _state["last_quake_poll"] < interval or not st.ready(now):
        return
    _state["last_quake_poll"] = now
    start_ms = int((now - 7200) * 1000)

    def ok(data):
        st.on_ok()
        _state["wolfx_fail"] = 0
        events = src.parse_icl_events(data)
        if not events and isinstance(data, dict) and "data" in data:
            # 空列表是正常情况（近期无预警），不是失败
            pass
        _ingest_quakes(events)

    def fail(msg):
        st.on_fail(msg)
        _state["wolfx_fail"] += 1

    src.request_json(_state["nam"], src.ICL_LIST_URL.format(start_ms=start_ms),
                     ok, fail, tag="icl_list")


def _poll_wolfx(now):
    """ICL 连续失败后启用：四端点 round-robin，总频率 1 请求 / 2 秒。"""
    if now - _state["last_wolfx_poll"] < 2.0:
        return
    keys = list(src.WOLFX_EEW_URLS.keys())
    key = keys[_state["wolfx_rr"] % len(keys)]
    _state["wolfx_rr"] += 1
    _state["last_wolfx_poll"] = now
    st = _status(key, "Wolfx-" + key.split("_")[-1].upper())

    def ok(data):
        st.on_ok()
        events = src.parse_wolfx_events(data, key)
        _ingest_quakes(events)
        # 备源成功即视为可用，逐步恢复主源
        _state["wolfx_fail"] = max(0, _state["wolfx_fail"] - 1)

    def fail(msg):
        st.on_fail(msg)

    src.request_json(_state["nam"], src.WOLFX_EEW_URLS[key], ok, fail, tag=key)


def _ingest_quakes(events):
    if not events:
        return
    merged, changed = src.merge_quakes(_state["quakes"], events)
    _state["quakes"] = src.prune_quakes(merged, _now())
    _state["cache_dirty"] = True
    if changed:
        _fetch_details(changed)
        _refresh_focus()


def _fetch_details(events):
    """对触发阈值内的事件补取 ICL 逐县详情（每个 revision 至多一次）。"""
    cfg = _state["config"]
    lat, lon = cfg.get("lat"), cfg.get("lon")
    if lat is None or lon is None:
        return
    for ev in events:
        if ev.get("source") != "icl" or ev.get("counties"):
            continue
        r = qc.evaluate(ev, lat, lon, _now(), cfg.get("threshold", 2.0),
                    thresholds=cfg.get("level_thresholds"))
        if not r or not r.get("displayable"):
            continue
        key = (ev.get("event_id"), ev.get("revision"))
        if key in _state["detail_done"]:
            continue
        _state["detail_done"].add(key)
        eid = ev.get("event_id")
        tag = f"icl_detail:{eid}:{ev.get('revision')}"

        def make_ok(target=ev):
            def ok(data):
                rows = src.parse_icl_detail(data, target.get("event_id"))
                if rows:
                    target["counties"] = rows
                    _state["cache_dirty"] = True
                    _refresh_focus()
            return ok

        src.request_json(_state["nam"],
                         src.ICL_DETAIL_URL.format(eid=eid),
                         make_ok(), lambda msg: None, tag=tag)


def _poll_weather(now):
    cfg = _state["config"]
    province = cfg.get("province")
    st = _status("nmc", "NMC")
    interval = max(60, int(cfg.get("weather_interval_sec", 60)))
    if now - _state["last_weather_poll"] < interval or not st.ready(now):
        return
    _state["last_weather_poll"] = now

    def ok(data, strict=False):
        st.on_ok()
        alerts = src.parse_nmc_alerts(data, province, strict=strict)
        _state["weather"] = {a["uid"]: a for a in alerts}
        _state["weather"] = src.prune_weather(_state["weather"], _now())
        _state["weather_stat"] = src.weather_stat(data)
        _refresh_focus()

    def fail(msg):
        # 省过滤请求失败（网关拦截/接口变更）→ 全国列表兜底，本地按省名过滤
        src.request_json(_state["nam"], src.NMC_NATIONWIDE_URL,
                         lambda d: ok(d, True),
                         lambda m2: st.on_fail(f"{msg} / {m2}"),
                         tag="nmc_all")

    src.request_json(_state["nam"], src.nmc_url(province),
                     ok, fail, tag="nmc", headers=src.NMC_HEADERS)


# ---------------- 演练 ----------------
def drill_epicenter():
    """演练震中：指定了城市就用它的坐标，否则用本市东北方向约 50km 的模拟点。

    返回 (lat, lon, 显示名)；本地坐标未设置时返回 (None, None, "")。
    """
    cfg = _state["config"]
    prov = cfg.get("drill_province") or ""
    city = cfg.get("drill_city") or ""
    dist = cfg.get("drill_district") or ""
    if city:
        c = cities.coord_of(prov, city, dist)
        if c:
            return float(c[0]), float(c[1]), f"{city}{dist}"
    lat, lon = cfg.get("lat"), cfg.get("lon")
    if lat is None or lon is None:
        return None, None, ""
    return float(lat) + 0.45, float(lon) + 0.45, ""


def drill_estimate():
    """演练预估结果（设置页预览与演练共用同一套算法）。"""
    cfg = _state["config"]
    lat, lon = cfg.get("lat"), cfg.get("lon")
    if lat is None or lon is None:
        return None
    ela, elo, place = drill_epicenter()
    if ela is None:
        return None
    mag = float(cfg.get("drill_magnitude") or 6.0)
    depth = float(cfg.get("drill_depth") or 10.0)
    d = qc.haversine_km(float(lat), float(lon), ela, elo)
    inten = qc.intensity_at(mag, d)
    return {
        "distance_km": d,
        "intensity": inten,
        "countdown_sec": qc.countdown_seconds(depth, d),
        "level": qc.level_of(inten, cfg.get("level_thresholds")),
        "lat": ela, "lon": elo, "place": place,
        "magnitude": mag, "depth": depth,
    }


def _start_drill():
    """生成一次演练事件：震中 / 震级 / 深度 全部来自设置页参数。"""
    cfg = _state["config"]
    api = _state.get("api")
    est = drill_estimate()
    if est is None:
        if api:
            api.notify("请先在设置里选择城市（或填写经纬度）")
        return False
    now = _now()
    # 倒计时**完全由算法给出**（震中距离 + 震源深度查表），与真实预警同一套计算，
    # 不提供"人为设定到达秒数"，避免演练结果失真。
    cd = est["countdown_sec"]
    place = "【演练】" + (est["place"] or "模拟震中")
    _state["banner_dismissed"] = None     # 演练重新开始 -> 清掉上次的"已确认"
    _state["banner_since_key"] = None     # 并重新开始"警报条占用计时"
    _state["drill"] = {
        "kind": "quake", "uid": "drill:1", "source": "drill",
        "event_id": "drill", "revision": 1,
        "origin_ts": now,                  # 发震时刻 = 现在 → 横波 cd 秒后到达
        "updated_ts": now, "lat": est["lat"], "lon": est["lon"],
        "depth": est["depth"], "magnitude": est["magnitude"],
        "epicenter": place, "max_intensity": None,
        "report_count": 1, "counties": None,
    }
    _refresh_focus()
    if api:
        api.log("演练：震中 %s（%.4f, %.4f），距 %.1fkm，预估烈度 %.1f，"
                "倒计时 %.1fs" % (est["place"] or "就近模拟",
                                  est["lat"], est["lon"],
                                  est["distance_km"], est["intensity"], cd))
        api.request_refresh()
    return True


def _stop_drill():
    _state["drill"] = None
    _state["notified"].pop("drill:1", None)
    _refresh_focus()
    api = _state.get("api")
    if api:
        api.request_refresh()
    return True


# ---------------- 显示位 0：紧急警报条（地震，主岛 + 副岛融合成一条） ----------------
def _banner_text(focus):
    """警报条文案：震中城市 · 震级 · 预估烈度 · 横波倒计时 · 距震中。"""
    ev = focus.get("event") or {}
    mag = ev.get("magnitude") or 0
    place = (ev.get("epicenter") or "未知震中").strip()
    inten = focus.get("local_intensity") or 0
    dist = float(focus.get("distance_km") or 0)
    if focus.get("phase") == "incoming":
        sec = max(0, int(round(_banner_remain(focus))))
        wave = f"横波还有 {sec} 秒"
    else:
        wave = "横波已到达"
    return (f"{place} · M{mag:g} · 预估烈度{inten:g} · {wave} · "
            f"距震中 {dist:.0f}km")


def _banner_remain(focus):
    """实时剩余秒数（用到达时刻重算，使红条以 ~30fps 平滑收缩）。"""
    arrive = focus.get("arrive_ts")
    if arrive:
        try:
            return max(0.0, float(arrive) - _now())
        except (TypeError, ValueError):
            pass
    return max(0.0, float(focus.get("remain_sec") or 0))


def banner_spec():
    """地震时：主岛与副岛融合成一条倒计时警报条，顶掉上课状态。

    **大震**（默认红色档，达 `tips_min_level`）：
    - 向下拓展一排"避险要诀"，前 `tips_hold_sec` 秒两层、之后只留要诀；
    - 一直顶掉课程显示，点击灵动岛 → 再点一次确认，才恢复上课显示。

    **小震**（未达门槛）：
    - 只**短暂占用** `small_quake_hold_sec` 秒（默认 5），之后自动把课程显示交还，
      倒计时继续在主岛加长片段上展示（不长时间占屏、也不需要确认）。

    气象灾害（含橙色/红色）不使用警报条——保持原来的主岛片段 + 提醒条，
    避免把台风/暴雨等长时间预警长时间占满屏幕。
    """
    cfg = _state["config"]
    focus = _state.get("focus")
    if not focus or focus.get("kind") != "quake":
        return None
    if not cfg.get("quake_enabled", True):
        return None
    if not cfg.get("banner_enabled", True):
        return None

    ev = focus.get("event") or {}
    uid = ev.get("uid") or ""
    try:
        revision = int(ev.get("revision") or 0)
    except (TypeError, ValueError):
        revision = 0
    # 用户已点“确认”收起过的事件不再弹（该事件升级 revision 后重新出现）
    done = _state.get("banner_dismissed")
    if done and done[0] == uid and revision <= done[1]:
        return None

    # —— 小震：只短暂占用 ——
    # 维护本次占用计时；同一事件（uid+revision）连续调用不重置。
    key = (uid, revision)
    if _state.get("banner_since_key") != key:
        _state["banner_since_key"] = key
        _state["banner_since"] = time.monotonic()
    if not _is_big_quake(focus):
        hold = _small_hold_sec()
        if hold <= 0:
            return None                     # 小震完全不占用警报条
        if time.monotonic() - float(_state.get("banner_since") or 0) >= hold:
            return None                     # 占用时间到 -> 把课程显示交还回去

    try:
        window = max(1.0, float(focus.get("countdown_sec") or 0))
    except (TypeError, ValueError):
        window = 1.0
    remain = _banner_remain(focus)
    ratio = max(0.0, min(1.0, remain / window)) if remain > 0 else 0.0

    spec = {
        "text": _banner_text(focus),
        "ratio": ratio,
        # 颜色按**预估烈度**分档（≤2 蓝 / 3 黄 / 4-5 橙 / ≥6 红，可在设置里改）
        "color": qc.level_color(focus.get("level"), cfg.get("level_colors")),
        "min_width": 460,
        "priority": 100,             # 独占：任何其它插件片段都让位
        "on_click": _on_banner_click,
        "on_confirm": _on_banner_confirm,
    }
    tips = _safety_tips()
    if tips:
        spec["extra"] = {"text": tips}
        try:
            spec["extra_hold_sec"] = max(5, int(cfg.get("tips_hold_sec", 60)))
        except (TypeError, ValueError):
            spec["extra_hold_sec"] = 60
        spec["require_confirm"] = bool(cfg.get("require_confirm", True))
        try:
            spec["confirm_timeout_sec"] = max(
                0.0, float(cfg.get("confirm_timeout_sec", 5)))
        except (TypeError, ValueError):
            spec["confirm_timeout_sec"] = 5.0
    return spec


def _is_big_quake(focus=None):
    """是否达到「大震」门槛（默认红色档）。

    大震：警报条长期占用 + 展开避险要诀 + 需点击确认才恢复上课；
    小震：只短暂占用（`small_quake_hold_sec`，默认 5 秒）后自动交还课程显示。
    """
    gate = str(_state["config"].get("tips_min_level") or "red")
    if gate == "none":
        return True
    lv = (focus or _state.get("focus") or {}).get("level") or "blue"
    return qc.LEVEL_RANK.get(lv, 0) >= qc.LEVEL_RANK.get(gate, 3)


def _small_hold_sec():
    """小震的警报条占用时长（秒）；0 = 小震完全不占用警报条。"""
    try:
        return max(0.0, float(
            _state["config"].get("small_quake_hold_sec", 5)))
    except (TypeError, ValueError):
        return 5.0


def _safety_tips():
    """当前要显示的避险要诀（空字符串 = 不显示第二层）。"""
    cfg = _state["config"]
    if not cfg.get("show_safety_tips", True):
        return ""
    if not _is_big_quake():
        return ""              # 小震不展开要诀
    return str(cfg.get("safety_tips") or "").strip()


def _on_banner_confirm():
    """用户点击"确认"：收起警报条、恢复上课显示。

    记录 (uid, revision)，同一事件不再打扰；若事件升级（revision 变大）
    则会重新弹出。
    """
    focus = _state.get("focus") or {}
    ev = focus.get("event") or {}
    if focus.get("kind") == "quake" and ev.get("uid"):
        try:
            revision = int(ev.get("revision") or 0)
        except (TypeError, ValueError):
            revision = 0
        _state["banner_dismissed"] = (ev.get("uid"), revision)
    api = _state.get("api")
    if api:
        api.log("用户已确认地震预警 -> 收起警报条，恢复上课显示")
        api.request_refresh()


def _on_banner_click():
    """点击警报条 = 重新播报一次当前地震预警。"""
    _on_extra_click()


# ---------------- 显示位 1：主岛加长片段 ----------------
def _focus_visible():
    return _state.get("focus") is not None


def _extra_text():
    v = draw.view()
    return v.get("main") or ""


def _extra_width():
    """文本区最宽 200px，超长交给 draw 里的跑马灯滚动，避免把岛撑得太长。"""
    txt = _extra_text()
    if not txt:
        return 0
    tw = min(draw.text_width(txt, 13, True), EXTRA_TEXT_MAX_W)
    w = int(20 + 7 + tw + 16)
    return max(110, min(400, w))


def _banner_taking_over():
    """当前是否真的由警报条独占显示（片段/副岛让位）。

    直接以 `banner_spec()` 是否有内容为准，这样"小震占用时间到了""用户已确认"
    "警报条被关掉"等情形都会自动把显示位还给片段与副岛
    （小震过后倒计时继续在主岛片段上展示）。
    注意：`banner_spec()` 不依赖本函数，不会形成递归。
    """
    if not _state.get("banner_ok"):
        return False
    return banner_spec() is not None


def extra_spec():
    if not _focus_visible() or _banner_taking_over():
        return None
    return {
        "width": _extra_width(),
        "draw": draw.draw_main_extra,
        "on_click": _on_extra_click,
        "priority": 11,
    }


def _on_extra_click():
    """点击片段 = 重新播报一次当前预警（受节流限制）。"""
    focus = _state.get("focus")
    api = _state.get("api")
    if focus is None or api is None:
        return
    uid = (focus.get("event") or {}).get("uid")
    if focus.get("kind") == "quake":
        ev = focus.get("event") or {}
        sec = max(0, int(round(focus.get("remain_sec") or 0)))
        text = (f"⚠️ {ev.get('epicenter', '')} M{ev.get('magnitude', 0):g} · "
                f"横波还有 {sec} 秒" if focus.get("phase") == "incoming"
                else f"⚠️ {ev.get('epicenter', '')} · 横波已到达")
    else:
        ev = focus.get("event") or {}
        text = (f"⚠️ {ev.get('county', '')}{ev.get('signal', '')}"
                f"{qc.level_word(focus.get('level'))}预警")
    try:
        _notify(text, force=bool(_state["config"].get("force_show", True)))
    except Exception:
        pass


# ---------------- 显示位 2：副岛 ----------------
def _sub_length():
    """文本区最宽 190px，超长交给 draw 里的跑马灯滚动。"""
    txt = (draw.view().get("sub") or "")
    tw = min(draw.text_width(txt, 13, True), SUB_TEXT_MAX_W)
    w = int(20 + 16 + tw + 16)
    return max(60, min(380, w))


def sub_spec():
    if not _focus_visible() or _banner_taking_over():
        return None
    cfg = _state["config"]
    if not cfg.get("use_subisland", True):
        return None
    focus = _state.get("focus") or {}
    if focus.get("kind") == "weather":
        ev = focus.get("event") or {}
        # 一般预警（暴雨/高温等）不占用副岛，让位给天气/媒体插件；
        # 台风、地震等重要预警则主岛 + 副岛一起占用
        if _weather_tier(ev) == "normal" and cfg.get("normal_no_subisland", True):
            return None
    return {
        "length": _sub_length(),
        "draw": draw.draw_sub,       # 模块级稳定函数：id 不变，不会反复自动展开
        "auto_collapse": False,      # 有预警时保持展开
        "priority": 11,              # 压过天气(0)与媒体(10)
    }


# ---------------- 显示位 3：下拉面板 ----------------
def _panel_lines():
    cfg = _state["config"]
    focus = _state.get("focus")
    lines = []

    if focus and focus.get("kind") == "quake":
        ev = focus.get("event") or {}
        src_name = "演练" if ev.get("source") == "drill" else \
            ("ICL" if ev.get("source") == "icl" else "Wolfx")
        lines.append(f"地震预警 · {src_name}")
        lines.append(f"M{ev.get('magnitude', 0):g} {ev.get('epicenter', '')}")
        lines.append(f"发震 {qc.fmt_clock(ev.get('origin_ts'))} · "
                     f"深 {ev.get('depth', 0):g}km")
        lines.append(f"本地 {focus.get('distance_km', 0):.1f}km · "
                     f"烈度 {focus.get('local_intensity', 0):g}")
        if focus.get("phase") == "incoming":
            lines.append(f"横波还有 {max(0, int(round(focus.get('remain_sec') or 0)))} 秒到达")
        else:
            lines.append("横波已到达")
        rc = ev.get("report_count")
        if rc:
            lines.append(f"第{rc}报 · 更新 {qc.fmt_clock_hm(ev.get('updated_ts'))}")
        counties = ev.get("counties") or []
        if counties:
            near = min(counties, key=lambda c: c.get("distance") or 1e9)
            lines.append(f"最近县 {near.get('name', '')} "
                         f"{near.get('distance', 0):.0f}km "
                         f"烈度{near.get('intensity', 0):.1f}")
    elif focus and focus.get("kind") == "weather":
        ev = focus.get("event") or {}
        city = cfg.get("city") or ""
        lines.append(f"气象灾害预警 · {cfg.get('province', '')}")
        if city:
            lines.append(f"本市 {city}")
        lines.append(f"{ev.get('county', '')} · {ev.get('signal', '')}"
                     f"{qc.level_word(focus.get('level'))}")
        lines.append(f"发布 {qc.fmt_clock_hm(ev.get('issued_ts'))}")
        for o in _state["others"]:
            e2 = o.get("event") or {}
            if o.get("kind") != "weather":
                continue
            lines.append(f"· {e2.get('signal', '')}"
                         f"{qc.level_word(o.get('level'))} "
                         f"{e2.get('county', '')} "
                         f"{qc.fmt_clock_hm(e2.get('issued_ts'))}")
        wo = _state.get("weather_others") or []
        if wo:
            lines.append(f"省内其他 {len(wo)} 条")
            for w in wo[:2]:
                lines.append(f"· {w.get('signal', '')}"
                             f"{qc.level_word(w.get('level'))} "
                             f"{w.get('county', '')}")
    else:
        wo = _state.get("weather_others") or []
        if wo:
            lines.append(f"本市无预警 · 省内其他 {len(wo)} 条")
            for w in wo[:3]:
                lines.append(f"· {w.get('signal', '')}"
                             f"{qc.level_word(w.get('level'))} "
                             f"{w.get('county', '')} "
                             f"{qc.fmt_clock_hm(w.get('issued_ts'))}")
        elif not cfg.get("show_status_card", True):
            return []
        else:
            lines.append("灾害预警 · 监测中")
        lines.append(_status("icl", "ICL").describe())
        if cfg.get("province") and cfg.get("province") != PROVINCE_NONE:
            lines.append(_status("nmc", "NMC").describe())
        if cfg.get("lat") is None or cfg.get("lon") is None:
            lines.append("未设置坐标 · 无法计算地震倒计时")
        else:
            scope = (cfg.get("city") or "") + (cfg.get("district") or "")
            scope = scope or cfg.get("province") or ""
            lines.append(f"坐标 {cfg.get('lat')}, {cfg.get('lon')} · "
                         f"阈值 {cfg.get('threshold', 2.0):g}"
                         + (f" · {scope}" if scope else ""))
        if _state["in_class"]:
            lines.append("上课中 · 气象低等级已静默")
    return lines


def panel_spec():
    lines = _panel_lines()
    if not lines:
        return None
    return {
        "text": "\n".join(lines),
        "width": 240,
        "height": 20 + len(lines) * 22 + 14,
        "order": 80,
        "position": "right",
    }


# ---------------- 设置页 ----------------
CITY_ANY = "（不限）"
DIST_ANY = "（不限）"
DRILL_AUTO = "（就近模拟）"


def _find_province_index(province):
    if province in PROVINCES:
        return PROVINCES.index(province) + 1
    return 0


def _attach_completer(box):
    """给可编辑下拉框加"包含匹配"补全，方便在全国几百个城市里搜索。"""
    try:
        comp = QCompleter(box.model(), box)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        comp.setCompletionMode(QCompleter.PopupCompletion)
        box.setCompleter(comp)
    except Exception:
        pass


def _combo_value(box, any_label):
    """取下拉框的值：占位项 / 空 -> ''；用户手输 -> 文本本身。"""
    txt = (box.currentText() or "").strip()
    if not txt or txt == any_label:
        return ""
    i = box.findText(txt)
    if i >= 0:
        data = box.itemData(i)
        return str(data) if data else txt
    return txt


def _select_or_set(box, value):
    """优先精确选中，选不到就写入编辑框（保留用户手输的城市名）。"""
    i = box.findText(value) if value else -1
    if i >= 0:
        box.setCurrentIndex(i)
    else:
        box.setCurrentIndex(box.count() - 1)
        if value:
            box.setEditText(value)


def _fill_city_box(box, prov, keep=""):
    """按省份刷新城市下拉（末项恒为「（不限）」）。"""
    box.blockSignals(True)
    box.clear()
    if prov and prov != PROVINCE_NONE:
        for name, _la, _lo in cities.cities_of(prov):
            box.addItem(name, name)
    box.addItem(CITY_ANY, "")
    _select_or_set(box, keep)
    box.blockSignals(False)


def _fill_district_box(box, prov, city, keep=""):
    """按省 + 市刷新区县下拉（末项恒为「（不限）」）。"""
    box.blockSignals(True)
    box.clear()
    if prov and city:
        full = cities._match_key(cities.cities_of(prov), city) or city
        for name, _la, _lo in cities.districts_of(prov, full):
            box.addItem(name, name)
    box.addItem(DIST_ANY, "")
    _select_or_set(box, keep)
    box.blockSignals(False)


def build_settings(api):
    cfg = _state["config"]

    w = QWidget()
    root = QVBoxLayout(w)
    root.setContentsMargins(0, 0, 0, 0)

    # --- 定位与位置 ---
    form = QFormLayout()
    form.setHorizontalSpacing(24)
    form.setVerticalSpacing(10)

    province = QComboBox()
    province.addItem(PROVINCE_NONE, PROVINCE_NONE)
    for p in PROVINCES:
        province.addItem(p, p)
    province.setCurrentIndex(_find_province_index(cfg.get("province")))

    # 城市 / 区县：全国三级下拉（可输入关键字搜索）
    city_box = QComboBox()
    city_box.setObjectName("cityBox")
    city_box.setEditable(True)
    city_box.setInsertPolicy(QComboBox.NoInsert)
    city_box.setMinimumWidth(200)
    _attach_completer(city_box)

    district_box = QComboBox()
    district_box.setObjectName("districtBox")
    district_box.setEditable(True)
    district_box.setInsertPolicy(QComboBox.NoInsert)
    district_box.setMinimumWidth(170)
    _attach_completer(district_box)

    lat_edit = QLineEdit("" if cfg.get("lat") is None else str(cfg["lat"]))
    lat_edit.setObjectName("latEdit")
    lat_edit.setPlaceholderText("选定城市后自动填入，也可手动微调")
    lon_edit = QLineEdit("" if cfg.get("lon") is None else str(cfg["lon"]))
    lon_edit.setObjectName("lonEdit")
    lon_edit.setPlaceholderText("如 104.6419")

    geo_btn = QPushButton("IP 自动定位")
    geo_btn.setMaximumWidth(130)

    geo_hint = QLabel("城市决定气象预警的过滤范围（只显示本市的预警）；"
                      "坐标用于地震倒计时，选定城市/区县后会自动填入。")
    geo_hint.setObjectName("hint")
    geo_hint.setWordWrap(True)

    form.addRow("省份（气象预警）", province)
    form.addRow("城市", city_box)
    form.addRow("区县（可选）", district_box)
    form.addRow("纬度", lat_edit)
    form.addRow("经度", lon_edit)
    form.addRow("", geo_btn)
    form.addRow("", geo_hint)

    _fill_city_box(city_box, cfg.get("province") or "", cfg.get("city") or "")
    _fill_district_box(district_box, cfg.get("province") or "",
                       cfg.get("city") or "", cfg.get("district") or "")

    # --- 预警参数 ---
    threshold = QDoubleSpinBox()
    threshold.setRange(0.0, 12.0)
    threshold.setSingleStep(0.5)
    threshold.setDecimals(1)
    threshold.setValue(float(cfg.get("threshold", 2.0)))

    min_level = QComboBox()
    for key, name in (("blue", "蓝色"), ("yellow", "黄色"),
                      ("orange", "橙色"), ("red", "红色")):
        min_level.addItem(name, key)
    min_level.setCurrentIndex(
        {"blue": 0, "yellow": 1, "orange": 2, "red": 3}.get(
            cfg.get("weather_min_level", "yellow"), 1))

    throttle = QSpinBox()
    throttle.setRange(10, 300)
    throttle.setSuffix(" 秒")
    throttle.setValue(int(cfg.get("throttle_sec", 30)))

    q_interval = QSpinBox()
    q_interval.setRange(3, 30)
    q_interval.setSuffix(" 秒")
    q_interval.setValue(int(cfg.get("quake_interval_sec", 5)))

    w_interval = QSpinBox()
    w_interval.setRange(60, 300)
    w_interval.setSuffix(" 秒")
    w_interval.setValue(int(cfg.get("weather_interval_sec", 60)))

    form.addRow("烈度阈值", threshold)
    form.addRow("气象最低等级", min_level)
    form.addRow("提醒节流", throttle)
    form.addRow("地震轮询间隔", q_interval)
    form.addRow("气象轮询间隔", w_interval)

    # --- 重要 / 一般预警策略（分级展示） ---
    important_sig = QLineEdit(str(cfg.get("important_signals") or ""))
    important_sig.setPlaceholderText("如：台风,地震,海啸（逗号分隔）")

    important_lv = QComboBox()
    for key, name in (("red", "红色"), ("orange", "橙色"),
                      ("yellow", "黄色"), ("none", "不启用")):
        important_lv.addItem(name, key)
    important_lv.setCurrentIndex(
        {"red": 0, "orange": 1, "yellow": 2, "none": 3}.get(
            cfg.get("important_min_level", "red"), 0))

    force_hold = QSpinBox()
    force_hold.setRange(10, 300)
    force_hold.setSuffix(" 秒")
    force_hold.setValue(int(cfg.get("force_hold_sec", 60)))

    form.addRow("重要预警类型", important_sig)
    form.addRow("重要等级门槛", important_lv)
    form.addRow("强制显示保持", force_hold)
    root.addLayout(form)

    # --- 预估烈度 -> 颜色分档（默认地震预警行业色标，可自定义） ---
    lv_title = QLabel("预估烈度 → 颜色分档")
    lv_title.setObjectName("sectionTitle")
    root.addWidget(lv_title)

    range_lbl = QLabel()
    range_lbl.setObjectName("hint")
    range_lbl.setWordWrap(True)
    root.addWidget(range_lbl)

    lv_form = QFormLayout()
    lv_form.setHorizontalSpacing(24)
    lv_form.setVerticalSpacing(10)

    th_boxes = []
    for label, val in zip(("蓝 → 黄 分界", "黄 → 橙 分界", "橙 → 红 分界"),
                          qc.norm_thresholds(cfg.get("level_thresholds"))):
        sb = QDoubleSpinBox()
        sb.setRange(0.0, 12.0)
        sb.setSingleStep(0.5)
        sb.setDecimals(1)
        sb.setSuffix(" 度")
        sb.setValue(float(val))
        sb.setObjectName("levelThreshold")
        th_boxes.append(sb)
        lv_form.addRow(label, sb)

    colors_cfg = dict(qc.LEVEL_COLORS)
    if isinstance(cfg.get("level_colors"), dict):
        colors_cfg.update({k: v for k, v in cfg["level_colors"].items()
                           if isinstance(v, str) and v.strip()})

    color_edits = {}
    for key, label in (("blue", "蓝色"), ("yellow", "黄色"),
                       ("orange", "橙色"), ("red", "红色")):
        row = QHBoxLayout()
        edit = QLineEdit(colors_cfg.get(key, ""))
        edit.setObjectName("levelColor_" + key)
        edit.setMaximumWidth(110)
        pick = QPushButton("选色…")
        pick.setMaximumWidth(90)

        def _pick_impl(edit=edit):
            from PySide6.QtGui import QColor
            cur = QColor((edit.text() or "").strip() or "#4da3ff")
            c = QColorDialog.getColor(cur, w, "选择颜色")
            if c is not None and c.isValid():
                edit.setText(c.name())
                save()

        pick.clicked.connect(lambda _=False, f=_pick_impl: f())
        row.addWidget(edit)
        row.addWidget(pick)
        row.addWidget(QLabel(f"（{label}）"))
        row.addStretch()
        lv_form.addRow(f"{label}条颜色", row)
        color_edits[key] = edit

    lv_hint = QLabel(
        "颜色按**预估烈度**分档（地震预警标准做法）：烈度越大越红，"
        "代表你这里晃得越厉害。\n"
        "默认：≤2.0 蓝 ｜ 3.0 黄 ｜ 4-5 橙 ｜ ≥6 红；三个分界值与四种颜色都可自定义。")
    lv_hint.setObjectName("hint")
    lv_hint.setWordWrap(True)

    def _update_range_lbl():
        r = qc.intensity_ranges([sb.value() for sb in th_boxes])
        range_lbl.setText(
            "当前分档：蓝色 %s ｜ 黄色 %s ｜ 橙色 %s ｜ 红色 %s"
            % (r["blue"], r["yellow"], r["orange"], r["red"]))

    _update_range_lbl()
    for _sb in th_boxes:
        _sb.valueChanged.connect(_update_range_lbl)

    root.addLayout(lv_form)
    root.addWidget(lv_hint)

    # --- 开关 ---
    q_on = QCheckBox("启用地震预警")
    q_on.setChecked(bool(cfg.get("quake_enabled", True)))
    w_on = QCheckBox("启用气象灾害预警")
    w_on.setChecked(bool(cfg.get("weather_enabled", True)))
    use_sub = QCheckBox("有预警时占用副岛")
    use_sub.setChecked(bool(cfg.get("use_subisland", True)))
    silent = QCheckBox("上课期间静默气象低等级预警（地震不静默）")
    silent.setChecked(bool(cfg.get("silent_low_weather_in_class", True)))
    notify_on = QCheckBox("启用主岛提醒条")
    notify_on.setChecked(bool(cfg.get("notify_enabled", True)))
    card_on = QCheckBox("无预警时下拉面板显示监测状态")
    card_on.setChecked(bool(cfg.get("show_status_card", True)))

    force_on = QCheckBox("重要预警强制弹出（上课 / PPT 全屏也弹出）")
    force_on.setChecked(bool(cfg.get("force_show", True)))
    normal_free = QCheckBox("一般预警只在课间与自习显示（上课不打扰）")
    normal_free.setChecked(bool(cfg.get("normal_only_free_time", True)))
    normal_nosub = QCheckBox("一般预警不占用副岛（把副岛留给天气/媒体）")
    normal_nosub.setChecked(bool(cfg.get("normal_no_subisland", True)))

    banner_on = QCheckBox("地震用红色警报条（主岛+副岛融合，顶掉上课显示）")
    banner_on.setChecked(bool(cfg.get("banner_enabled", True)))

    tier_hint = QLabel(
        "重要预警（台风、地震等，或达到上面「重要等级门槛」）——"
        "任何时间都显示、主岛与副岛一起占用、且强制弹出；\n"
        "一般预警（暴雨、高温等）——只在课间与自习显示，不占用副岛，安静提醒。")
    tier_hint.setObjectName("hint")
    tier_hint.setWordWrap(True)

    banner_hint = QLabel(
        "开启后：地震来临瞬间，主岛与副岛会并成一条红色倒计时条，"
        "显示「震中城市 · 震级 · 本地烈度 · 横波还有 N 秒 · 距震中」；\n"
        "它会顶掉课程与上课前倒计时，并且上课 / PPT 全屏时也照常显示。")
    banner_hint.setObjectName("hint")
    banner_hint.setWordWrap(True)
    for cb in (q_on, w_on, use_sub, silent, notify_on, card_on):
        root.addWidget(cb)

    # --- 重要 / 一般预警的分级展示 ---
    root.addWidget(force_on)
    root.addWidget(normal_free)
    root.addWidget(normal_nosub)
    root.addWidget(tier_hint)

    # --- 地震警报条 ---
    root.addWidget(banner_on)
    root.addWidget(banner_hint)

    # --- 避险要诀（警报条向下拓展的第二层） ---
    tips_on = QCheckBox("地震时展开「避险要诀」（警报条下方多一排）")
    tips_on.setChecked(bool(cfg.get("show_safety_tips", True)))

    tips_edit = QLineEdit(str(cfg.get("safety_tips") or ""))
    tips_edit.setObjectName("safetyTips")
    tips_edit.setPlaceholderText("如：伏地 · 遮挡 · 手抓牢")

    tips_lv = QComboBox()
    for key, name in (("red", "红色档（≥6 度）"), ("orange", "橙色档及以上"),
                      ("none", "不限制")):
        tips_lv.addItem(name, key)
    tips_lv.setCurrentIndex({"red": 0, "orange": 1, "none": 2}.get(
        cfg.get("tips_min_level", "red"), 0))

    tips_hold = QSpinBox()
    tips_hold.setObjectName("tipsHold")
    tips_hold.setRange(10, 600)
    tips_hold.setSuffix(" 秒")
    tips_hold.setValue(int(cfg.get("tips_hold_sec", 60)))

    confirm_on = QCheckBox("点灵动岛 + 再点一次「确认」才恢复上课显示")
    confirm_on.setChecked(bool(cfg.get("require_confirm", True)))

    confirm_timeout = QSpinBox()
    confirm_timeout.setObjectName("confirmTimeout")
    confirm_timeout.setRange(0, 60)
    confirm_timeout.setSuffix(" 秒")
    confirm_timeout.setValue(int(cfg.get("confirm_timeout_sec", 5)))

    small_hold = QSpinBox()
    small_hold.setObjectName("smallHold")
    small_hold.setRange(0, 60)
    small_hold.setSuffix(" 秒")
    small_hold.setToolTip("未达到上面「展开门槛」的小震，警报条只占用这么久，"
                          "之后自动把课程显示还回去（倒计时继续显示在主岛片段上）；"
                          "0 = 小震完全不占用警报条")
    small_hold.setValue(int(cfg.get("small_quake_hold_sec", 5)))

    confirm_form = QFormLayout()
    confirm_form.addRow("只点一次后自动退回", confirm_timeout)
    confirm_form.addRow("小震只占用", small_hold)

    tips_hint = QLabel(
        "达到门槛的地震（大震）：警报条下方多展开一排避险要诀，前 N 秒两层并存，\n"
        "之后第一层消失、只留要诀并继续顶掉课程；点击灵动岛进入待确认，再点一次才恢复上课显示；\n"
        "只点一次不管它，会自动退回要诀显示，不会因为误触而解除。\n"
        "未达门槛的地震（小震）：警报条只短暂占用（见下方「小震只占用」），"
        "随后自动交还课程显示，\n倒计时继续显示在主岛加长片段上。")
    tips_hint.setObjectName("hint")
    tips_hint.setWordWrap(True)

    tips_form = QFormLayout()
    tips_form.setHorizontalSpacing(24)
    tips_form.setVerticalSpacing(10)
    tips_form.addRow("要诀内容", tips_edit)
    tips_form.addRow("展开门槛", tips_lv)
    tips_form.addRow("第一层保持", tips_hold)

    root.addWidget(tips_on)
    root.addLayout(tips_form)
    root.addWidget(confirm_on)
    root.addLayout(confirm_form)
    root.addWidget(tips_hint)

    # --- 演练（可指定震中城市 + 震级 / 深度） ---
    drill_title = QLabel("模拟演练（可指定震中）")
    drill_title.setObjectName("sectionTitle")
    root.addWidget(drill_title)

    drill_form = QFormLayout()
    drill_form.setHorizontalSpacing(24)
    drill_form.setVerticalSpacing(10)

    d_prov = QComboBox()
    d_prov.setObjectName("drillProvince")
    d_prov.addItem(DRILL_AUTO, "")
    for p in PROVINCES:
        if p != PROVINCE_NONE:
            d_prov.addItem(p, p)
    _i = d_prov.findData(cfg.get("drill_province") or "")
    d_prov.setCurrentIndex(_i if _i >= 0 else 0)

    d_city = QComboBox()
    d_city.setObjectName("drillCity")
    d_city.setEditable(True)
    d_city.setInsertPolicy(QComboBox.NoInsert)
    d_city.setMinimumWidth(200)
    _attach_completer(d_city)

    d_dist = QComboBox()
    d_dist.setObjectName("drillDistrict")
    d_dist.setEditable(True)
    d_dist.setInsertPolicy(QComboBox.NoInsert)
    d_dist.setMinimumWidth(170)
    _attach_completer(d_dist)

    d_mag = QDoubleSpinBox()
    d_mag.setObjectName("drillMagnitude")
    d_mag.setRange(3.0, 9.0)
    d_mag.setSingleStep(0.1)
    d_mag.setDecimals(1)
    d_mag.setSuffix(" 级")
    d_mag.setValue(float(cfg.get("drill_magnitude") or 6.0))

    d_depth = QDoubleSpinBox()
    d_depth.setObjectName("drillDepth")
    d_depth.setRange(1.0, 60.0)
    d_depth.setSingleStep(1.0)
    d_depth.setDecimals(0)
    d_depth.setSuffix(" km")
    d_depth.setValue(float(cfg.get("drill_depth") or 10.0))

    # 到达倒计时不提供输入：完全由震中距离 + 深度算出来（与真实预警同一套算法）
    d_lead = QLabel("由震中与深度自动计算")
    d_lead.setObjectName("hint")

    drill_form.addRow("震中省份", d_prov)
    drill_form.addRow("震中城市", d_city)
    drill_form.addRow("震中区县（可选）", d_dist)
    drill_form.addRow("震级", d_mag)
    drill_form.addRow("震源深度", d_depth)
    drill_form.addRow("到达倒计时", d_lead)
    root.addLayout(drill_form)

    _fill_city_box(d_city, cfg.get("drill_province") or "",
                   cfg.get("drill_city") or "")
    _fill_district_box(d_dist, cfg.get("drill_province") or "",
                       cfg.get("drill_city") or "",
                       cfg.get("drill_district") or "")

    drill_preview = QLabel()
    drill_preview.setObjectName("hint")   # 跟随宿主题的提示文字样式
    drill_preview.setWordWrap(True)
    root.addWidget(drill_preview)

    drill_row = QHBoxLayout()
    drill_btn = QPushButton("开始演练")
    stop_btn = QPushButton("停止演练")
    drill_row.addWidget(drill_btn)
    drill_row.addWidget(stop_btn)
    drill_row.addStretch()
    root.addLayout(drill_row)

    hint = QLabel("演练走与真实预警完全相同的链路（倒计时算法 / 警报条 / 提醒），"
                  "震中与震级由你指定，不需要等真实地震。"
                  "选「（就近模拟）」则在本市附近生成一个模拟震中。")
    hint.setObjectName("hint")
    hint.setWordWrap(True)
    root.addWidget(hint)

    # --- 数据源状态 ---
    status = QLabel()
    status.setObjectName("hint")
    status.setWordWrap(True)
    root.addWidget(status)

    src_hint = QLabel("数据源：ICL（成都高新减灾研究所）+ Wolfx 备用、"
                      "中央气象台 nmc.cn。均为公开接口，"
                      "预警信息仅供参考，请以官方发布为准。")
    src_hint.setObjectName("hint")
    src_hint.setWordWrap(True)
    root.addWidget(src_hint)

    # --- 保存 ---
    def _collect_colors():
        """收集用户自定义配色（只接受 #RRGGBB 形式，非法项忽略）。"""
        out = {}
        for key, edit in color_edits.items():
            v = (edit.text() or "").strip()
            if re.match(r"^#?[0-9A-Fa-f]{6}$", v):
                out[key] = v if v.startswith("#") else "#" + v
        return out

    def save(*_):
        c = _state["config"]
        prov = province.currentData()
        c["province"] = prov
        c["city"] = _combo_value(city_box, CITY_ANY)
        c["district"] = _combo_value(district_box, DIST_ANY)
        c["lat"] = _parse_float(lat_edit.text())
        c["lon"] = _parse_float(lon_edit.text())
        c["threshold"] = float(threshold.value())
        c["weather_min_level"] = min_level.currentData()
        c["throttle_sec"] = int(throttle.value())
        c["quake_interval_sec"] = int(q_interval.value())
        c["weather_interval_sec"] = int(w_interval.value())
        c["quake_enabled"] = bool(q_on.isChecked())
        c["weather_enabled"] = bool(w_on.isChecked())
        c["use_subisland"] = bool(use_sub.isChecked())
        c["silent_low_weather_in_class"] = bool(silent.isChecked())
        c["notify_enabled"] = bool(notify_on.isChecked())
        c["show_status_card"] = bool(card_on.isChecked())
        c["important_signals"] = important_sig.text().strip()
        c["important_min_level"] = important_lv.currentData()
        c["force_hold_sec"] = int(force_hold.value())
        c["force_show"] = bool(force_on.isChecked())
        c["normal_only_free_time"] = bool(normal_free.isChecked())
        c["normal_no_subisland"] = bool(normal_nosub.isChecked())
        c["banner_enabled"] = bool(banner_on.isChecked())
        # 避险要诀（第二层）
        c["show_safety_tips"] = bool(tips_on.isChecked())
        c["safety_tips"] = tips_edit.text().strip()
        c["tips_min_level"] = tips_lv.currentData()
        c["tips_hold_sec"] = int(tips_hold.value())
        c["require_confirm"] = bool(confirm_on.isChecked())
        # 预估烈度分档（阈值 + 颜色）
        c["level_thresholds"] = [float(sb.value()) for sb in th_boxes]
        cols = _collect_colors()
        if cols:
            c["level_colors"] = cols
        # 演练参数
        c["drill_province"] = _combo_value(d_prov, DRILL_AUTO)
        c["drill_city"] = _combo_value(d_city, CITY_ANY)
        c["drill_district"] = _combo_value(d_dist, DIST_ANY)
        c["drill_magnitude"] = float(d_mag.value())
        c["drill_depth"] = float(d_depth.value())
        c["confirm_timeout_sec"] = int(confirm_timeout.value())
        c["small_quake_hold_sec"] = int(small_hold.value())
        _save_config()
        _refresh_focus()
        api.request_refresh()
        _update_drill_preview()

    # --- 位置联动：省 -> 市 -> 区县，选定后自动填坐标 ---
    def _apply_city_coord():
        if province.currentData() == PROVINCE_NONE:
            return
        city = _combo_value(city_box, CITY_ANY)
        if not city:
            return
        c = cities.coord_of(province.currentData(), city,
                            _combo_value(district_box, DIST_ANY))
        if c:
            lat_edit.setText("%.4f" % c[0])
            lon_edit.setText("%.4f" % c[1])

    def on_province_changed(*_):
        prov = province.currentData()
        prov = "" if prov == PROVINCE_NONE else prov
        _fill_city_box(city_box, prov, "")
        _fill_district_box(district_box, prov, "", "")
        save()

    def on_city_changed(*_):
        prov = province.currentData()
        prov = "" if prov == PROVINCE_NONE else prov
        city = _combo_value(city_box, CITY_ANY)
        _fill_district_box(district_box, prov, city, "")
        _apply_city_coord()
        save()

    def on_district_changed(*_):
        _apply_city_coord()
        save()

    # --- 演练联动：震中省市县 + 实时预览 ---
    def on_drill_where_changed(*_):
        prov = _combo_value(d_prov, DRILL_AUTO)
        _fill_city_box(d_city, prov, _combo_value(d_city, CITY_ANY))
        _fill_district_box(d_dist, prov, _combo_value(d_city, CITY_ANY),
                           _combo_value(d_dist, DIST_ANY))
        save()

    def on_drill_city_changed(*_):
        prov = _combo_value(d_prov, DRILL_AUTO)
        _fill_district_box(d_dist, prov, _combo_value(d_city, CITY_ANY), "")
        save()

    def _update_drill_preview():
        lat = _parse_float(lat_edit.text())
        lon = _parse_float(lon_edit.text())
        if lat is None or lon is None:
            drill_preview.setText(
                "请先在上方选择本地城市（或填写经纬度），然后才能预览演练效果。")
            return
        prov = _combo_value(d_prov, DRILL_AUTO)
        city = _combo_value(d_city, CITY_ANY)
        dist = _combo_value(d_dist, DIST_ANY)
        c = cities.coord_of(prov, city, dist) if city else None
        if c:
            ela, elo = c
            where = f"{city}{dist}"
        else:
            ela, elo = lat + 0.45, lon + 0.45
            where = "本地附近（模拟）"
        d = qc.haversine_km(lat, lon, ela, elo)
        inten = qc.intensity_at(d_mag.value(), d)
        cd = qc.countdown_seconds(d_depth.value(), d)
        lv = qc.level_of(inten, [sb.value() for sb in th_boxes])
        note = ""
        if inten <= float(threshold.value()):
            note = ("  ⚠ 预估烈度低于「烈度阈值」，演练不会有任何显示"
                    "（换更近的震中或提高震级）")
        elif cd > 120:
            note = "  ⚠ 距离较远，倒计时会比较长"
        drill_preview.setText(
            "震中：%s ｜ 距你约 %.0fkm ｜ 预估烈度 %.1f（%s档） ｜ "
            "横波约 %.0f 秒后到达\n（倒计时由震中距离与震源深度算出，"
            "与真实预警同一套算法，不可手改）%s"
            % (where, d, inten, qc.level_name(lv), cd, note))

    province.currentIndexChanged.connect(on_province_changed)
    city_box.currentIndexChanged.connect(on_city_changed)
    city_box.editTextChanged.connect(lambda *_: _update_drill_preview())
    district_box.currentIndexChanged.connect(on_district_changed)
    lat_edit.editingFinished.connect(save)
    lon_edit.editingFinished.connect(save)
    threshold.valueChanged.connect(save)
    min_level.currentIndexChanged.connect(save)
    throttle.valueChanged.connect(save)
    q_interval.valueChanged.connect(save)
    w_interval.valueChanged.connect(save)
    important_sig.editingFinished.connect(save)
    important_lv.currentIndexChanged.connect(save)
    force_hold.valueChanged.connect(save)
    for sb in th_boxes:
        sb.valueChanged.connect(save)
    for edit in color_edits.values():
        edit.editingFinished.connect(save)
    for cb in (q_on, w_on, use_sub, silent, notify_on, card_on,
               force_on, normal_free, normal_nosub, banner_on,
               tips_on, confirm_on):
        cb.toggled.connect(save)
    tips_edit.editingFinished.connect(save)
    tips_lv.currentIndexChanged.connect(save)
    tips_hold.valueChanged.connect(save)
    confirm_timeout.valueChanged.connect(save)
    small_hold.valueChanged.connect(save)

    d_prov.currentIndexChanged.connect(on_drill_where_changed)
    d_city.currentIndexChanged.connect(on_drill_city_changed)
    d_dist.currentIndexChanged.connect(save)
    d_mag.valueChanged.connect(save)
    d_depth.valueChanged.connect(save)

    def _geo_done():
        geo_btn.setEnabled(True)
        geo_btn.setText("IP 自动定位")

    def on_geo():
        """三源交叉定位：多数一致的城市胜出，避免单一 IP 库定位偏差。"""
        from PySide6.QtCore import QTimer as _QT
        geo_btn.setEnabled(False)
        geo_btn.setText("定位中…")
        probes = {}
        state = {"left": 0, "done": False}

        def finish():
            if state["done"]:
                return
            state["done"] = True
            _geo_done()
            res = _geo_vote(probes)
            if not res:
                status.setText("定位失败：三个定位源都不可用，请手动填写经纬度与城市")
                return
            if res.get("lat") is not None and res.get("lon") is not None:
                lat_edit.setText("%.4f" % res["lat"])
                lon_edit.setText("%.4f" % res["lon"])
            if res.get("province"):
                province.setCurrentIndex(_find_province_index(res["province"]))
            city = res.get("city") or ""
            if city and not city.endswith(CITY_SUFFIXES):
                city += "市"
            prov = res.get("province") or province.currentData()
            if city:
                # 用城市下拉框承载定位结果（保留原 IP 定位给的坐标）
                _fill_city_box(city_box, prov, city)
                _fill_district_box(district_box, prov, city, "")
            save()

            detail = " ｜ ".join(
                "%s：%s%s" % (n, (v or ("", "", "", ""))[0],
                              (v or ("", "", "", ""))[1])
                for n, v in sorted(probes.items(),
                                   key=lambda kv: GEO_PRIORITY.get(kv[0], 9)))
            if res.get("conflict"):
                status.setText(
                    f"⚠ 定位源结果不一致，已按多数取「{res.get('province', '')}"
                    f"{city}」，请确认城市是否正确 —— {detail}")
            else:
                status.setText(f"定位：{res.get('province', '')}{city} —— {detail}")

        def probe(name, url):
            state["left"] += 1

            def ok(d):
                val = _geo_parse(name, d)
                if val:
                    probes[name] = val
                state["left"] -= 1
                if state["left"] <= 0:
                    finish()

            def fail(_msg):
                state["left"] -= 1
                if state["left"] <= 0:
                    finish()

            src.request_json(_state["nam"], url, ok, fail,
                             tag="geo_" + name, timeout_ms=GEO_TIMEOUT_MS)

        probe("pconline", GEO_URL_PCONLINE)
        probe("ipwho", GEO_URL)
        probe("ipapi", GEO_URL_CN)
        _QT.singleShot(GEO_TIMEOUT_MS + 800, finish)   # 兜底（防个别源不回调）

    geo_btn.clicked.connect(on_geo)
    drill_btn.clicked.connect(lambda: _start_drill())
    stop_btn.clicked.connect(lambda: _stop_drill())

    def refresh_status():
        parts = [_status("icl", "ICL").describe()]
        if _state["wolfx_fail"] >= 2:
            parts.append(f"备用源 Wolfx 已启用（失败计数 {_state['wolfx_fail']}）")
        if _state["config"].get("province") and \
                _state["config"].get("province") != PROVINCE_NONE:
            parts.append(_status("nmc", "NMC").describe())
        if _state["in_class"]:
            parts.append("当前上课中")
        if _state.get("drill"):
            parts.append("演练进行中")
        status.setText(" ｜ ".join(parts))

    _update_drill_preview()
    refresh_status()
    from PySide6.QtCore import QTimer
    timer = QTimer(w)
    timer.setInterval(1000)
    timer.timeout.connect(refresh_status)
    timer.start()

    root.addStretch()
    return w


def _parse_float(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


# ---------------- 生命周期 ----------------
def _on_load():
    _load_cache()
    api = _state.get("api")
    if api:
        cfg = _state["config"]
        api.log("已加载，缓存地震事件 %d 条" % len(_state["quakes"]))
        if cfg.get("lat") is None or cfg.get("lon") is None:
            api.log("尚未设置坐标，地震倒计时不可用（请在设置页填写或点 IP 定位）")


def _on_start():
    _refresh_focus()


def _on_stop():
    _save_cache(force=True)


def register(api):
    _state["api"] = api
    _state["config"] = _load_config()
    _state["nam"] = src.make_manager()

    api.add_island_extra(extra_spec)
    api.add_subisland(sub_spec)
    api.add_panel(panel_spec)
    api.add_settings_page("灾害预警", build_settings, icon="⚠️")

    # 紧急警报条（主岛 + 副岛融合）：老版宿主没有该接口时自动跳过，
    # 此时地震仍走"主岛片段 + 副岛"的老路径（见 _banner_taking_over）
    if hasattr(api, "add_island_banner"):
        api.add_island_banner(banner_spec)
        _state["banner_ok"] = True

    api.on_load(_on_load)
    api.on_start(_on_start)
    api.on_stop(_on_stop)
    api.set_interval(1, _tick)

    api.log("已注册（地震: ICL+Wolfx / 气象: nmc.cn）")
