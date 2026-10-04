import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile

from PySide6.QtCore import QObject, QThread, Signal

import paths
import plugin_deps
from storage import read_json, write_json
from plugin_manager import PluginManager

REPO = "LCHXXXX-1/Class-Daily-Land"
BRANCH = "plugins"
# GitHub 回退索引：plugins 分支根目录的 list.json。
# raw 打头、jsDelivr 殿后：jsDelivr 会缓存 GitHub 文件（分支引用能滞后
# 好几个小时），刚发布的插件可能半天刷不出来，所以先去 raw 拿新鲜的；
# raw 不通就 8 秒放弃、交给 jsDelivr 兜底，既新鲜又不卡住。
GITHUB_LIST_URLS = [
    f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/list.json",
    f"https://cdn.jsdelivr.net/gh/{REPO}@{BRANCH}/list.json",
]
USER_AGENT = "ClassDailyLand-PluginMarket/4.2"

# 远程聚合列表（主用的索引来源，优先级最高）
REMOTE_LIST_URL = "https://plugins.class-daily-land.de5.net/list.json"

# Gitee 索引：同一插件仓库 plugins 分支根目录的 list.json。
# 注意要用 raw 直链（/blob/ 是网页，拿不到 JSON）。
GITEE_REPO = "lchxxxx/class-daily-land"
GITEE_BRANCH = "plugins"
GITEE_LIST_URLS = [
    f"https://gitee.com/{GITEE_REPO}/raw/{GITEE_BRANCH}/list.json",
]

# 各来源列表的本地缓存文件名（下划线开头，避免与插件实体文件混淆）
REMOTE_CACHE_NAME = "_remote_list.json"
GITHUB_CACHE_NAME = "_github_list.json"
GITEE_CACHE_NAME = "_gitee_list.json"

# 三类超时（秒）：索引同步、索引首地址、插件包下载。
# 插件包给到 60 秒——慢网下 90KB 的包也得让人家爬完嘛，别半路掐断。
LIST_TIMEOUT = 30
# 首地址专享的短上限：它内容最新但不一定通（raw.githubusercontent.com），
# 8 秒没动静就换镜像，不磨蹭。
FAST_LIST_TIMEOUT = 8
DOWNLOAD_TIMEOUT = 60

# GitHub 的 list.json 存的是 github.com/.../raw/... 直链，会 302 跳到
# raw.githubusercontent.com——国内常年连不上。认出来，换成镜像候选。
_GH_BLOB_RE = re.compile(
    r"^https://github\.com/([^/]+/[^/]+)/raw/([^/]+)/(.+)$")
_GH_RAW_RE = re.compile(
    r"^https://raw\.githubusercontent\.com/([^/]+/[^/]+)/([^/]+)/(.+)$")
JSDELIVR_GH = "https://cdn.jsdelivr.net/gh/{repo}@{branch}/{path}"

_SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_SEMVER_RE = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")
# 远程列表的 id（package_name）允许带点号，例如 class.lchx.clock，别大惊小怪
_REMOTE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


# ---------------- SemVer ----------------
def parse_version(text):
    """解析 SemVer → 可比较元组；非法返回 None。正式版大于同号预发布版。"""
    m = _SEMVER_RE.match(str(text or "").strip())
    if not m:
        return None
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    pre = m.group(4)
    if pre is None:
        return (major, minor, patch, 1, ())
    parts = []
    for seg in pre.split("."):
        parts.append((0, int(seg)) if seg.isdigit() else (1, seg))
    return (major, minor, patch, 0, tuple(parts))


def version_gt(a, b):
    """a 是否比 b 新；b 非法/缺失视为最旧。"""
    pa = parse_version(a)
    if pa is None:
        return False
    pb = parse_version(b)
    if pb is None:
        return True
    return pa > pb


# ---------------- 索引条目校验（远程：单文件聚合列表） ----------------
def parse_remote_list(data):
    """解析远程聚合列表，返回统一的内部 entry 列表。

    远程格式（见 https://plugins.class-daily-land.de5.net/list.json）::

        {
          "plugins": [
            {
              "package_name": "class.lchx.clock",
              "name": "clock",
              "display_name": "时钟",
              "author_id": "lchx",
              "author_name": "LCHXXXX",
              "version": "1.0.0",
              "description": "在灵动岛下拉面板显示当前时间和日期",
              "file": "plugins/class.lchx.clock.cblplugin",
              "sha256": "de39...5e1",
              "size": 802,
              "url": "https://plugin.lchxxxx.de5.net/plugins/....cblplugin",
              "uploaded_at": "2026-09-26T13:25:16.677621+00:00"
            }
          ],
          "updated_at": "2026-09-26T13:25:17.093600+00:00"
        }

    映射关系：
    - package_name -> id
    - display_name -> name
    - url          -> download_url
    - file         -> file（去掉 "plugins/" 前缀，只留文件名）
    - author_name  -> author

    条目不合法也**不丢**：以前一条脏数据就把插件悄悄抹掉，屏幕上只剩
    "这插件哪去了"，查都没处查。现在照样生成 entry，原因塞进 ``problem``，
    由市场渲染成"⚠ + 原因"并禁掉安装按钮。
    整体结构不合法（不是对象 / 缺 plugins 数组）才抛 ValueError。
    """
    if not isinstance(data, dict):
        raise ValueError("远程列表不是 JSON 对象")
    raw = data.get("plugins")
    if not isinstance(raw, list):
        raise ValueError("远程列表缺少 plugins 数组")

    entries = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue

        pid = str(item.get("package_name") or "").strip()
        version = str(item.get("version") or "").strip()
        sha = str(item.get("sha256") or "").strip().lower()
        url = str(item.get("url") or "").strip()
        # file 在远程列表里形如 "plugins/xxx.cblplugin"，只取纯文件名
        fname = os.path.basename(str(item.get("file") or "").strip())
        if not fname or fname in (".", ".."):
            fname = f"{pid}.cblplugin" if pid else ""

        # ---- 逐项体检：只记原因，不丢条目 ----
        problem = ""
        if not pid:
            problem = "索引里缺少 package_name"
        elif not _REMOTE_ID_RE.match(pid):
            problem = "package_name 不合法（只许字母数字和 . _ -）：%r" % pid
        elif pid in seen:
            problem = "package_name 在索引里重复：%s" % pid
        elif parse_version(version) is None:
            problem = "版本号不是 SemVer（x.y.z）：%r" % version
        elif not _SHA_RE.match(sha):
            problem = "sha256 不是 64 位十六进制：%r" % (sha[:20] or "空")
        elif not url:
            problem = "索引里没有下载地址（url）"
        elif not url.startswith("https://"):
            problem = "下载地址必须是 https：%r" % url[:40]

        if pid:
            seen.add(pid)
        entries.append({
            "id": pid or (fname or "?"),
            "name": str(item.get("display_name")
                        or item.get("name") or pid or "未命名"),
            "version": version or "0.0.0",
            "format": "cblplugin",
            "file": fname,
            "download_url": url,
            "sha256": sha,
            "description": str(item.get("description") or ""),
            "author": str(item.get("author_name") or ""),
            "problem": problem,
        })
    return entries, sum(1 for e in entries if e["problem"])


# ---------------- 主动取消（切换服务器 / 新任务抢占） ----------------
class Cancelled(Exception):
    """后台任务被主动中止：切换索引来源、被新任务抢占或程序退出。"""


# ---------------- 后台任务载体 ----------------
class _JobSignals(QObject):
    done = Signal(object, bool, str)


class _JobThread(QThread):
    def __init__(self, sig, fn):
        super().__init__()
        self._sig = sig
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
            self._sig.done.emit(result, True, "")
        except Exception as e:
            self._sig.done.emit(None, False,
                                str(e) or e.__class__.__name__)


# ---------------- 市场核心 ----------------
class PluginMarket(QObject):
    log_line = Signal(str)                       # 日志文本
    busy_changed = Signal(bool)                  # 是否有任务在跑
    sync_finished = Signal(bool, str)            # 同步结果
    catalog_ready = Signal(list)                 # 插件列表（含本地状态）
    task_progress = Signal(str, int)             # (插件id, 0-100；-1=结束)
    task_done = Signal(str, bool, str, bool)     # (id, 成功, 消息, 需重启)
    dep_progress = Signal(dict)                  # 依赖安装进度事件

    def __init__(self, manager, settings, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.settings = settings
        self.cache_dir = paths.MARKET_CACHE_DIR
        self.plugins_dir = (manager.plugins_dir if manager
                            else paths.PLUGINS_DIR)
        self.catalog = []
        self.last_sync_text = ""
        self._thread = None
        self._sig = None
        self._cur_id = ""
        self._gen = 0                       # 任务代号：新任务抢占时作废旧结果
        self._cancel = threading.Event()    # 当前任务的取消信号
        self._inflight = []                 # 仍在收尾的线程（含被抢占的旧任务）

    # ---------- 任务队列（新任务抢占旧任务，旧任务被立即取消） ----------
    def is_busy(self):
        thread = self._thread
        if thread is None:
            return False
        try:
            return thread.isRunning()
        except RuntimeError:
            # C++ 对象已被 deleteLater 销毁
            self._thread = None
            return False

    def abort(self):
        """请求立即中止当前后台任务（网络读取会在下一个分片处退出）。"""
        try:
            self._cancel.set()
        except Exception:
            pass

    def _dispatch(self, fn, on_ok):
        # 新任务到来（切换索引来源 / 再次检查更新 / 安装等）时，不再拒绝，
        # 而是把仍在跑的旧任务就地取消，立刻开跑新任务。
        gen = self._gen + 1
        self._gen = gen
        if self.is_busy():
            self.log("已中止上一个任务，改用新的…")
            self.abort()

        cancel = threading.Event()
        self._cancel = cancel
        self.busy_changed.emit(True)
        sig = _JobSignals()
        thread = _JobThread(sig, lambda: fn(cancel))

        def _done(result, ok, err):
            stale = (gen != self._gen)      # 已被更新的任务取代 → 结果作废
            # 先断开引用，避免后续 is_busy/shutdown 访问已销毁的 QThread
            if self._thread is thread:
                self._thread = None
            if self._sig is sig:
                self._sig = None
            try:
                self._inflight.remove(thread)
            except ValueError:
                pass
            thread.deleteLater()
            sig.deleteLater()
            if stale:
                return
            self.busy_changed.emit(False)
            if ok:
                try:
                    on_ok(result)
                except Exception as e:
                    self.log_line.emit(f"界面刷新失败: {e}")
            else:
                self.log_line.emit(f"操作失败: {err}")
                self.task_done.emit("", False, err, False)

        sig.done.connect(_done)
        self._thread = thread
        self._sig = sig
        self._inflight.append(thread)
        thread.start()
        return True

    def shutdown(self):
        """退出设置窗口时调用：等待后台任务收尾，避免线程向已析构对象发信号。"""
        self.abort()
        budget = 8.0            # 秒：总等待预算，别为被抢占的旧任务卡太久
        for th in list(self._inflight):
            if budget <= 0:
                break
            t0 = time.monotonic()
            try:
                if th.isRunning():
                    th.wait(int(budget * 1000))
            except RuntimeError:
                pass
            budget -= (time.monotonic() - t0)
        self._inflight = []

    def log(self, text):
        self.log_line.emit(str(text))

    # ---------- 同步 ----------
    def check_updates(self):
        """按设置挑索引来源 → 拉索引 → 刷新目录。

        联网全挂时**退回本地缓存**（上次同步成功的那份），
        别让网络一抽风就把列表清空、只剩一句"同步没成功"。
        连缓存都没有，那才算真失败。
        """
        def job(cancel):
            source = self.settings.get("market_source", "official")
            self.log(f"开始同步插件索引（来源：{source}）…")
            errors = []

            def attempt(label, fn, cache_name):
                """试一个来源：成了返回 (方式, 条目)，败了记原因返回 None。"""
                try:
                    method = fn(cancel)
                    return method, self._scan_index(preferred=cache_name)
                except Cancelled:
                    raise                    # 主动中止（切源/退出）：不兜底
                except Exception as e:
                    errors.append("%s：%s" % (label, e))
                    self.log(f"{label} 同步失败（{e}）")
                    return None

            if source == "github":
                got = attempt("GitHub", self._sync_github_list,
                              GITHUB_CACHE_NAME)
            elif source == "gitee":
                got = attempt("Gitee", self._sync_gitee_list,
                              GITEE_CACHE_NAME)
            else:
                got = attempt("官方服务器", self._sync_remote_list,
                              REMOTE_CACHE_NAME)
                if got is None:
                    self.log("换 GitHub 顶上…")
                    got = attempt("GitHub", self._sync_github_list,
                                  GITHUB_CACHE_NAME)
            if got is not None:
                return got

            # 所有来源都没连上：退回本地缓存，别把列表清空
            entries = self._scan_index()
            if entries:
                self.log("联网同步全失败（%s），改用本地缓存的索引"
                         % "；".join(errors))
                return "本地缓存", entries
            raise RuntimeError("；".join(errors) or "索引同步失败")

        def on_ok(res):
            method, entries = res
            self.catalog = entries
            self.last_sync_text = time.strftime("%H:%M:%S")
            self.sync_finished.emit(
                True, f"已通过 {method} 同步 · 发现 {len(entries)} 个插件")
            self.catalog_ready.emit(entries)

        self._dispatch(job, on_ok)

    def rescan(self):
        """不联网，只重新扫描缓存 + 本地插件目录。"""
        def job(cancel):
            return self._scan_index()

        def on_ok(entries):
            self.catalog = entries
            self.catalog_ready.emit(entries)

        self._dispatch(job, on_ok)

    # ---------- 远程聚合列表 ----------
    def _sync_remote_list(self, cancel=None):
        """下载远程聚合列表写进本地缓存，返回来源标识 'remote-list'，不要改动。"""
        req = urllib.request.Request(REMOTE_LIST_URL,
                                     headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=LIST_TIMEOUT) as resp:
            blob = self._read_body(resp, cancel)
        try:
            data = json.loads(blob.decode("utf-8"))
        except UnicodeDecodeError as e:
            raise RuntimeError(f"远程列表编码不对劲：{e}") from e
        except json.JSONDecodeError as e:
            raise RuntimeError(f"远程列表不是有效 JSON：{e}") from e

        entries, skipped = parse_remote_list(data)
        if skipped:
            self.log(f"远程列表里 {skipped} 条记录有问题，"
                     f"仍会显示在列表中并标注原因")
        if not entries:
            # 空列表按"不可用"处理，交给 GitHub 兜底，避免页面空白
            raise RuntimeError("远程列表里没有任何可用插件")

        os.makedirs(self.cache_dir, exist_ok=True)
        write_json(os.path.join(self.cache_dir, REMOTE_CACHE_NAME), data)
        self.log(f"远程列表同步成功（{len(entries)} 个插件）")
        return "remote-list"

    def _read_list_cache(self, name):
        """读聚合列表的本地缓存；不存在 / 损坏 / 为空就还你一个 None。"""
        path = os.path.join(self.cache_dir, name)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            entries, _skipped = parse_remote_list(data)
        except Exception as e:
            self.log(f"列表缓存 {name} 罢工了（{e}）")
            return None
        return entries or None

    # ---------- GitHub / Gitee 索引：plugins 分支的 list.json ----------
    def _sync_mirror_list(self, urls, cache_name, source_id, label,
                          cancel=None):
        """从多个镜像 URL 拉取聚合列表写进本地缓存，返回来源标识。

        格式与官方远程列表一致（服务端审核通过时同步推送），
        复用 parse_remote_list() 解析；多个镜像按顺序试，全失败才报错。
        """
        data = None
        last_err = ""
        for i, url in enumerate(urls):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            # 头一个地址最新但不一定通，给它短上限；换镜像再放宽
            t = FAST_LIST_TIMEOUT if i == 0 else LIST_TIMEOUT
            try:
                req = urllib.request.Request(url,
                                             headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=t) as resp:
                    blob = self._read_body(resp, cancel)
                data = json.loads(blob.decode("utf-8-sig"))
                break
            except Cancelled:
                raise
            except Exception as e:
                last_err = str(e) or e.__class__.__name__
                self.log(f"{label} 列表源不通（{url.split('/')[2]}）：{last_err}")
        if data is None:
            raise RuntimeError(f"{label} 列表拉取失败：{last_err}")

        entries, skipped = parse_remote_list(data)
        if skipped:
            self.log(f"{label} 列表里 {skipped} 条记录有问题，"
                     f"仍会显示在列表中并标注原因")
        if not entries:
            raise RuntimeError(f"{label} 列表里没有任何可用插件")

        os.makedirs(self.cache_dir, exist_ok=True)
        write_json(os.path.join(self.cache_dir, cache_name), data)
        self.log(f"{label} 列表同步成功（{len(entries)} 个插件）")
        return source_id

    def _sync_github_list(self, cancel=None):
        """下载 GitHub plugins 分支根目录的 list.json（raw + jsDelivr 镜像）。"""
        return self._sync_mirror_list(
            GITHUB_LIST_URLS, GITHUB_CACHE_NAME, "github-list", "GitHub",
            cancel)

    def _sync_gitee_list(self, cancel=None):
        """下载 Gitee plugins 分支根目录的 list.json（raw 直链）。"""
        return self._sync_mirror_list(
            GITEE_LIST_URLS, GITEE_CACHE_NAME, "gitee-list", "Gitee",
            cancel)

    # ---------- 索引扫描 + 本地状态 ----------
    def _scan_index(self, preferred=None):
        """读索引条目（优先 preferred 缓存，其次官方列表，再退 GitHub / Gitee）。

        返回的每个 entry 都已附加本地状态
        （installed / installed_version / update_available / status ...），
        标签已直接给出，直接用即可。
        """
        names = [preferred] if preferred else []
        names += [REMOTE_CACHE_NAME, GITHUB_CACHE_NAME, GITEE_CACHE_NAME]
        for name in names:
            if not name:
                continue
            entries = self._read_list_cache(name)
            if entries:
                scanned = self._installed_index()
                return [self._local_status(e, scanned) for e in entries]
        self.log("索引尚未同步")
        return []

    @staticmethod
    def _norm_name(name):
        """目录名 / 插件 id 归一化：忽略大小写，下划线当连字符。"""
        return str(name or "").strip().lower().replace("_", "-")

    def _installed_index(self):
        """扫一遍 plugins/ 下已安装的插件目录。

        返回 [(目录名, plugin.json 内容或 None)]。每次扫描只做一遍，
        整批 entry 复用，避免逐条 listdir。
        """
        items = []
        try:
            names = sorted(os.listdir(self.plugins_dir))
        except Exception:
            return items
        for name in names:
            pdir = os.path.join(self.plugins_dir, name)
            if not os.path.isdir(pdir):
                continue
            meta = read_json(os.path.join(pdir, "plugin.json"), default=None)
            items.append((name, meta if isinstance(meta, dict) else None))
        return items

    def _match_installed(self, pid, installed):
        """在已安装目录里找 pid 对应的那一个，返回 (目录名, meta)。

        匹配顺序：
        1. 目录名 == 索引 id（从市场装的插件就是这样）；
        2. 包内 plugin.json 的 id == 索引 id；
        3. 归一化后相等（忽略大小写、下划线/连字符，以及
           class.<作者>.<名字> 这种命名空间前缀）。

        第 3 步是模糊匹配，只在候选唯一时采用——两个作者的同名插件
        （各自都叫 weather）就不会互相串台，宁可显示"未安装"。
        找不到返回 (None, None)。
        """
        for name, meta in installed:
            if name == pid:
                return name, meta
        for name, meta in installed:
            if meta is not None and str(meta.get("id") or "") == pid:
                return name, meta

        want = self._norm_name(pid)
        short = self._norm_name(str(pid).split(".")[-1])
        loose = []
        for name, meta in installed:
            keys = {self._norm_name(name)}
            if meta is not None:
                keys.add(self._norm_name(meta.get("id")))
                keys.add(self._norm_name(meta.get("name")))
            keys.discard("")
            if want and want in keys:
                loose.append((name, meta))
            elif short and short in keys:
                loose.append((name, meta))
        if len(loose) == 1:
            return loose[0]
        return None, None

    def _local_status(self, entry, scanned=None):
        pid = entry["id"]
        if scanned is None:
            scanned = self._installed_index()
        dir_name, meta = self._match_installed(pid, scanned)

        load_error = ""
        if self.manager is not None:
            for name, ok, msg in self.manager.loaded:
                if not ok and (name == pid or name == dir_name):
                    load_error = str(msg)
                    break
        disabled_ids = self._disabled_ids()
        disabled = pid in disabled_ids or (
            bool(dir_name) and dir_name in disabled_ids)
        installed = meta is not None
        local_ver = str(meta.get("version", "")) if meta else ""
        entry["installed"] = installed
        entry["installed_dir"] = dir_name or ""
        entry["installed_version"] = local_ver
        entry["disabled"] = disabled
        entry["load_error"] = load_error
        entry["update_available"] = bool(
            installed and version_gt(entry["version"], local_ver))
        if entry.get("problem"):
            # 索引记录本身有问题：照样显示，但标成"装不了"并写明原因
            entry["status"] = "invalid"
        elif not installed:
            entry["status"] = "not_installed"
        elif disabled:
            entry["status"] = "disabled"
        elif entry["update_available"]:
            entry["status"] = "update"
        elif load_error:
            entry["status"] = "failed"
        else:
            entry["status"] = "installed"
        return entry

    def _disabled_ids(self):
        try:
            return set(self.settings.get("disabled_plugins") or [])
        except Exception:
            return set()

    # ---------- 下载 / 安装 ----------
    def install(self, plugin_id):
        entry = next((e for e in self.catalog if e["id"] == plugin_id), None)
        if entry is None:
            self.task_done.emit(plugin_id, False, "插件不在当前索引中", False)
            return
        if entry.get("problem"):
            self.task_done.emit(
                plugin_id, False,
                "索引里这条记录有问题，装不了：" + entry["problem"], False)
            return
        if self.is_busy():
            self.log_line.emit("上一个任务仍在进行中，请稍候…")
            return

        def job(cancel):
            return self._install(dict(entry), cancel)

        def on_ok(result):
            ok, msg, restart = result
            try:
                self.catalog = self._scan_index()
                self.catalog_ready.emit(self.catalog)
            except Exception as e:
                self.log(f"刷新列表失败: {e}")
            self.task_done.emit(plugin_id, ok, msg, restart)

        self._dispatch(job, on_ok)

    def update_all(self):
        targets = [dict(e) for e in self.catalog
                   if e.get("update_available") and not e.get("disabled")]
        if not targets:
            self.log("没有可更新的插件")
            return
        if self.is_busy():
            self.log_line.emit("上一个任务仍在进行中，请稍候…")
            return

        def job(cancel):
            results = []
            for e in targets:
                if cancel.is_set():
                    break
                self.log(f"更新 {e['name']} → {e['version']} …")
                ok, msg, _ = self._install(e, cancel)
                results.append((e["name"], ok, msg))
            return results

        def on_ok(results):
            done = sum(1 for _n, ok, _m in results if ok)
            self.log(f"批量更新完成：成功 {done} / {len(results)}")
            for name, ok, msg in results:
                if not ok:
                    self.log(f"  ✗ {name}: {msg}")
            try:
                self.catalog = self._scan_index()
                self.catalog_ready.emit(self.catalog)
            except Exception as e:
                self.log(f"刷新列表失败: {e}")

        self._dispatch(job, on_ok)

    @staticmethod
    def download_candidates(url):
        """把一个下载地址展开成候选镜像（按优先级排好队）。

        GitHub 直链（github.com/<repo>/raw/<branch>/<path> 或
        raw.githubusercontent.com/<repo>/<branch>/<path>）换成 jsDelivr
        CDN 打头——同一个文件、同一份 sha256，国内连得上；后面再排
        两种 GitHub 原形态。非 GitHub 地址原样退回，只有一个。
        """
        url = str(url or "").strip()
        if not url:
            return []
        m = _GH_BLOB_RE.match(url) or _GH_RAW_RE.match(url)
        cands = []
        if m:
            repo, branch, path = m.group(1), m.group(2), m.group(3)
            cands.append(JSDELIVR_GH.format(repo=repo, branch=branch,
                                           path=path))
            cands.append(f"https://raw.githubusercontent.com/{repo}/"
                         f"{branch}/{path}")
            cands.append(f"https://github.com/{repo}/raw/{branch}/{path}")
        cands.append(url)

        out = []
        for c in cands:
            if c.startswith("https://") and c not in out:
                out.append(c)
        return out

    def _download_once(self, url, dest, cancel=None):
        """单次下载，写满 dest；返回落盘字节数。"""
        if not url.startswith("https://"):
            raise RuntimeError("下载地址不是 https")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
            total = int(resp.headers.get("content-length") or 0)
            done = 0
            last_pct = -1
            with open(dest, "wb") as f:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = done * 100 // total
                        if pct != last_pct:
                            last_pct = pct
                            self.task_progress.emit(self._cur_id, pct)
        if total and done != total:
            raise RuntimeError(f"只下到 {done}/{total} 字节，连接被截断")
        return done

    def _download(self, urls, dest, cancel=None, expect_sha=None):
        """下载插件包：候选镜像挨个试，每下一次就验一次 sha256。

        urls 可以是单个地址，也可以是一串候选。哪个镜像连不上、被截断、
        校验不过，就换下一个；全军覆没才抛异常，异常里写明每个源的原因。
        成功时返回命中的地址，日志好交代实际走了哪条路。
        """
        if isinstance(urls, str):
            urls = [urls]
        errors = []
        for i, url in enumerate(urls):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            host = url.split("/")[2] if "//" in url else url
            try:
                if i:
                    self.log(f"换下载源重试（{host}）…")
                self.task_progress.emit(self._cur_id, 0)
                self._download_once(url, dest, cancel)
                if expect_sha:
                    got = self._sha256(dest)
                    if got != expect_sha:
                        raise RuntimeError(
                            f"SHA-256 校验失败（实际 {got[:12]}…，期望 "
                            f"{expect_sha[:12]}…）")
                return url
            except Cancelled:
                raise
            except Exception as e:
                reason = str(e) or e.__class__.__name__
                errors.append(f"{host}: {reason}")
                self.log(f"下载源 {host} 没成功（{reason}）")
        raise RuntimeError("所有下载源都失败 → " + "；".join(errors))

    @staticmethod
    def _sha256(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()

    @staticmethod
    def _read_body(resp, cancel=None):
        """分片读取响应体，便于中途响应取消（切换服务器 / 退出）。"""
        buf = bytearray()
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            chunk = resp.read(65536)
            if not chunk:
                break
            buf.extend(chunk)
        return bytes(buf)

    @staticmethod
    def _safe_extract(pkg, dest):
        """解压 ZIP 到 dest，防目录穿越；支持包内唯一顶层目录。"""
        with zipfile.ZipFile(pkg) as zf:
            members = [n for n in zf.namelist() if not n.endswith("/")]
            root = PluginManager._package_root(members)
            if root is None:
                raise RuntimeError("插件包内未找到 plugin.json")
            os.makedirs(dest, exist_ok=True)
            for n in members:
                rel = n[len(root):] if root else n
                target = PluginManager._safe_join(dest, rel)
                if target is None:
                    raise RuntimeError(f"插件包含非法路径: {n}")
                parent = os.path.dirname(target)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with zf.open(n) as fsrc, open(target, "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst)

    @staticmethod
    def _finalize_meta(dest, entry):
        """合并市场元数据进包内 plugin.json；entry 等 loader 字段以包为准。"""
        meta_path = os.path.join(dest, "plugin.json")
        meta = read_json(meta_path, default=None)
        if not isinstance(meta, dict):
            return False
        entry_path = PluginManager._resolve_entry(
            dest, meta.get("entry", "main.py"))
        if not os.path.isfile(entry_path):
            return False
        # 把 entry 归一化为真实存在的相对路径（兼容 "main" / "main.py"）
        meta["entry"] = os.path.relpath(entry_path, dest).replace("\\", "/")
        for key in ("id", "format", "file", "download_url", "sha256",
                    "author", "minAppVersion"):
            if key in entry:
                meta[key] = entry[key]
        if meta.get("version") != entry["version"]:
            meta["version"] = entry["version"]
        if not meta.get("name"):
            meta["name"] = entry["name"]
        if not meta.get("description") and entry.get("description"):
            meta["description"] = entry["description"]
        write_json(meta_path, meta)
        return True

    def _install_plugin_deps(self, plugin_id, plugin_dir, cancel=None):
        """装完插件本体后处理 requires；成功返回补充文案，失败抛异常。

        调用方 _install 本身跑在后台线程，可以直接同步下载。
        返回 None = 没有依赖或全部就绪；返回字符串 = 给用户看的补充说明。
        """
        meta = read_json(os.path.join(plugin_dir, "plugin.json"),
                         default=None)
        requires = (meta or {}).get("requires")
        names = plugin_deps.normalize_requires(requires)
        if not names:
            return None
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        mgr = self.manager
        db = getattr(mgr, "deps_db", None)
        root = getattr(mgr, "packages_dir", None)
        if db is None or not root:
            raise RuntimeError("插件里声明了依赖，但宿主不支持依赖安装")
        base = mgr.packages_base_url()
        self.log(f"{plugin_id} 声明依赖：{'、'.join(names)}，开始准备…")

        def emit(ev):
            if not isinstance(ev, dict):
                return
            ev.setdefault("plugin", plugin_id)
            self.dep_progress.emit(ev)
            # 顺手把整体进度映射成百分比喂给老的进度条
            try:
                if ev.get("count"):
                    frac = (int(ev.get("index") or 1) - 1) / float(ev["count"])
                    sub = max(0, min(100, int(ev.get("pct") or 0))) / 100.0
                    self.task_progress.emit(plugin_id,
                                            int((frac + sub / ev["count"])
                                                * 100))
            except (TypeError, ValueError, ZeroDivisionError):
                pass

        def _abort():
            return (bool(cancel is not None and cancel.is_set())
                    or bool(getattr(mgr, "_deps_abort", False)))

        _ready, errors = plugin_deps.ensure_requirements(
            db, root, base, plugin_id, names, emit=emit,
            should_abort=_abort)
        if errors:
            raise RuntimeError("依赖安装失败：" + "；".join(errors.values()))
        try:
            if self.manager is not None:
                self.manager.refresh_dep_paths()
        except Exception:
            pass
        return f"依赖（{'、'.join(names)}）已就绪"

    def _install(self, entry, cancel=None):
        """在线程中执行：下载 → 校验 → 备份 → 解压 → 写元数据。
        返回 (成功, 消息, 是否需重启)。"""
        pid = entry["id"]
        self._cur_id = pid
        # 已装目录不一定叫索引 id（手动丢进来的包按包内 id / 文件名词干落盘），
        # 这种就走原地升级，别另起一个目录——否则同一个插件会被加载两遍。
        existing, _meta = self._match_installed(pid, self._installed_index())
        dest = os.path.join(self.plugins_dir, existing or pid)
        was_installed = os.path.isdir(dest)
        tmpdir = tempfile.mkdtemp(prefix="cb_plugin_")
        pkg = os.path.join(tmpdir, "package")
        try:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            self.log(f"下载 {entry['name']} v{entry['version']} …")
            self.task_progress.emit(pid, 0)
            # GitHub 来源的包地址是国内连不上的 github.com/…/raw/…，
            # 这里展开成候选镜像（jsDelivr 优先），逐个试到 sha256 对上为止。
            cands = self.download_candidates(entry["download_url"])
            used = self._download(cands, pkg, cancel=cancel,
                                  expect_sha=entry["sha256"])
            if len(cands) > 1:
                self.log(f"{entry['name']} 实际下载源：{used.split('/')[2]}")
            if not zipfile.is_zipfile(pkg):
                raise RuntimeError("插件包不是有效的 ZIP（.cblplugin）")

            bak = dest + ".bak"
            if os.path.isdir(bak):
                shutil.rmtree(bak, ignore_errors=True)
            moved = False
            if was_installed:
                os.replace(dest, bak)
                moved = True
            try:
                self._safe_extract(pkg, dest)
                if not self._finalize_meta(dest, entry):
                    raise RuntimeError("插件包缺少 plugin.json 或入口文件")
            except Exception:
                if os.path.isdir(dest):
                    shutil.rmtree(dest, ignore_errors=True)
                if moved:
                    os.replace(bak, dest)
                raise
            if moved:
                shutil.rmtree(bak, ignore_errors=True)

            verb = "更新" if was_installed else "装上"
            self.log(f"{entry['name']} {verb}成功")

            # ---- 第三方依赖：读 requires → 后台装（本线程就是后台）----
            deps_note = self._install_plugin_deps(pid, dest, cancel)
            if deps_note:
                return True, f"{verb}成功，{deps_note}", was_installed
            return True, f"{verb}成功", was_installed
        except Exception as e:
            self.log(f"{entry['name']} 安装失败: {e}")
            return False, str(e), False
        finally:
            self.task_progress.emit(pid, -1)
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ---------- 卸载 ----------
    def uninstall(self, plugin_id):
        entry = next((e for e in self.catalog if e["id"] == plugin_id), None)

        def job(cancel):
            # 目录名不一定等于索引 id：手动丢进来的 .cbplugin 会按包内 id /
            # 文件名词干落盘（比如 plugins/clock），这里统一解析出真实目录。
            dir_name, meta = self._match_installed(
                plugin_id, self._installed_index())
            if dir_name is None:
                return (False, "本地没找到这个插件的目录", False)
            pdir = os.path.join(self.plugins_dir, dir_name)
            marker = os.path.join(pdir, ".cblplugin.json")
            managed = (isinstance(meta, dict) and meta.get("id")) or \
                os.path.isfile(marker)
            if not managed:
                return (False, "内置/本地插件不能从市场卸载", False)
            try:
                if os.path.isdir(pdir):
                    shutil.rmtree(pdir)
                leftovers = [plugin_id + ".cblplugin",
                             dir_name + ".cblplugin"]
                if entry and entry.get("file"):
                    leftovers.append(entry["file"])
                for name in leftovers:
                    f = os.path.join(self.plugins_dir, name)
                    if os.path.isfile(f):
                        try:
                            os.remove(f)
                        except OSError:
                            pass
                # 依赖回收：把自己从各包 used_by 摘掉，used_by 空的包才删
                freed = []
                if self.manager is not None:
                    try:
                        freed = self.manager.release_plugin_deps(plugin_id)
                    except Exception as e:
                        self.log(f"依赖回收出错（不影响卸载）: {e}")
                extra = ("，顺带回收依赖 " + "、".join(freed)) if freed else ""
                self.log(f"已卸载 {plugin_id}")
                return True, "已卸载，重启后彻底生效" + extra, True
            except Exception as e:
                return False, f"卸载失败: {e}", True

        def on_ok(result):
            ok, msg, restart = result
            try:
                self.catalog = self._scan_index()
                self.catalog_ready.emit(self.catalog)
            except Exception as e:
                self.log(f"刷新列表失败: {e}")
            self.task_done.emit(plugin_id, ok, msg, restart)

        self._dispatch(job, on_ok)

    # ---------- 启用 / 禁用（重启后生效） ----------
    def set_enabled(self, plugin_id, enabled):
        try:
            lst = list(self.settings.get("disabled_plugins") or [])
        except Exception:
            lst = []
        if enabled and plugin_id in lst:
            lst.remove(plugin_id)
        if (not enabled) and plugin_id not in lst:
            lst.append(plugin_id)
        self.settings["disabled_plugins"] = lst
        self.settings.save()
        if self.manager is not None:
            self.manager.set_disabled_ids(lst)
        verb = "启用" if enabled else "禁用"
        self.log(f"已{verb} {plugin_id}，重启后生效")
        try:
            self.catalog = self._scan_index()
            self.catalog_ready.emit(self.catalog)
        except Exception as e:
            self.log(f"刷新列表失败: {e}")
        self.task_done.emit(plugin_id, True, f"已{verb}，重启后生效", True)