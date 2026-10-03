# -*- coding: utf-8 -*-
"""第三方依赖包管理：列出各下载源可用的包、查“被哪些插件使用”、
手动安装 / 卸载。

只做“发现 + 安装 / 删除”，安装机制完全复用 plugin_deps
（清单 → 多镜像下载 → sha256 校验 → 原子换入 packages/<包名>/）。
所有网络与磁盘重活都在 worker 线程执行，通过信号回传 UI。
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, QThread, Signal

import plugin_deps
from storage import read_json

USER_AGENT = "ClassDailyLand-PackageManager/1.0"
HTTP_TIMEOUT = 30


class Cancelled(Exception):
    """后台任务被主动中止（切换下载源 / 被新任务抢占 / 程序退出）。"""


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
        except Cancelled:
            self._sig.done.emit(None, False, "任务已取消")
        except Exception as e:
            self._sig.done.emit(None, False, str(e) or e.__class__.__name__)


class PackageStore(QObject):
    log_line = Signal(str)                    # 日志文本
    busy_changed = Signal(bool)               # 是否有任务在跑
    catalog_ready = Signal(list)              # 包列表（含本地状态）
    task_progress = Signal(str, int)          # (包名, 0-100；-1=结束)
    task_done = Signal(str, bool, str)        # (包名, 成功, 消息)

    def __init__(self, manager, settings, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.settings = settings
        self.deps_db = getattr(manager, "deps_db", None)
        self.packages_dir = getattr(manager, "packages_dir", None) or ""
        self.plugins_dir = getattr(manager, "plugins_dir", None) or ""

        self.catalog = []
        self._thread = None
        self._sig = None
        self._gen = 0
        self._cancel = threading.Event()
        self._inflight = []

    # ---------- 下载源 ----------
    @staticmethod
    def sources():
        """[(显示名, 源 id), ...]，顺序即 PACKAGE_SOURCES 定义顺序。"""
        return [(s.get("label") or sid, sid)
                for sid, s in plugin_deps.PACKAGE_SOURCES.items()]

    def source_id(self):
        try:
            sid = str(self.settings.get("packages_source", "") or "").strip()
        except Exception:
            sid = ""
        return (sid if sid in plugin_deps.PACKAGE_SOURCES
                else plugin_deps.DEFAULT_SOURCE)

    def set_source(self, sid):
        if sid not in plugin_deps.PACKAGE_SOURCES:
            return False
        self.settings["packages_source"] = sid
        self.settings.save()
        return True

    def base_urls(self):
        """当前下载源的清单地址候选（主地址 + 镜像）。

        settings.packages_base_url 非空时只认它。
        """
        try:
            custom = self.settings.get("packages_base_url", "")
        except Exception:
            custom = ""
        return plugin_deps.resolve_bases(self.source_id(), custom)

    # ---------- 本地状态 ----------
    def installed(self):
        """已登记安装的包：{包名: 条目 dict}。"""
        db = self.deps_db
        if db is None:
            return {}
        try:
            return db.all_entries()
        except Exception:
            return {}

    def used_by_map(self):
        """包名 → [使用它的插件目录名]，来源：本地插件 manifest + 登记表。"""
        result = {}
        try:
            names = sorted(os.listdir(self.plugins_dir))
        except Exception:
            names = []
        for name in names:
            meta = read_json(os.path.join(self.plugins_dir, name,
                                          "plugin.json"), default=None)
            if not isinstance(meta, dict):
                continue
            for pkg in plugin_deps.normalize_requires(meta.get("requires"),
                                                      name):
                lst = result.setdefault(pkg, [])
                if name not in lst:
                    lst.append(name)
        for pkg, ent in self.installed().items():
            for u in (ent.get("used_by") or ()):
                lst = result.setdefault(pkg, [])
                if u not in lst:
                    lst.append(u)
        return result

    # ---------- 列远端包 ----------
    @staticmethod
    def _read_body(resp, cancel):
        buf = bytearray()
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            chunk = resp.read(65536)
            if not chunk:
                break
            buf.extend(chunk)
        return bytes(buf)

    def _get_json(self, url, cancel):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            blob = self._read_body(resp, cancel)
        return json.loads(blob.decode("utf-8-sig"))

    @staticmethod
    def _names_from_items(items):
        names = []
        for it in items or ():
            if isinstance(it, str):
                n = it.strip()
            elif isinstance(it, dict):
                n = str(it.get("name") or "").strip()
            else:
                continue
            if n:
                names.append(n)
        return names

    def _list_index(self, base, cancel):
        """{base}/index.json：返回包名列表；没有 index（404）返回 None。"""
        url = str(base).rstrip("/") + "/index.json"
        try:
            data = self._get_json(url, cancel)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        if isinstance(data, dict):
            return self._names_from_items(data.get("packages"))
        if isinstance(data, list):
            return self._names_from_items(data)
        return []

    def _list_api(self, src, cancel):
        """Contents API（Gitee / GitHub 通用）：列出 packages 目录的 <包名>.json。"""
        url = str(src.get("api") or "")
        if not url:
            return None
        try:
            data = self._get_json(url, cancel)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        names = []
        if isinstance(data, list):
            for it in data:
                if (isinstance(it, dict) and it.get("type") == "file"
                        and str(it.get("name") or "").lower().endswith(".json")):
                    names.append(str(it["name"])[:-5].lower())
        return names

    def _list_names(self, cancel):
        """按当前源的能力列出远端包名；不支持列出时返回 None。"""
        src = plugin_deps.PACKAGE_SOURCES[self.source_id()]
        if src.get("api"):
            return self._list_api(src, cancel)
        return self._list_index(self.base_urls()[0], cancel)

    # ---------- 目录构建 ----------
    def _build_catalog(self, cancel):
        used = self.used_by_map()
        inst = self.installed()

        remote_names = None
        try:
            remote_names = self._list_names(cancel)
        except Cancelled:
            raise
        except Exception as e:
            self.log(f"列出远端包失败：{e}")
        if remote_names is None:
            self.log("当前下载源不支持自动列出，已改为显示：本地已装 + "
                     "插件声明的包（也可手动输入包名安装）")
            remote_set = set()
        else:
            remote_set = set(remote_names)
            self.log(f"远端发现 {len(remote_set)} 个包")

        names = set(remote_set) | set(inst.keys()) | set(used.keys())
        entries = []
        for n in sorted(names):
            ent = inst.get(n) or {}
            local_ver = ""
            if ent and os.path.isdir(os.path.join(self.packages_dir, n)):
                local_ver = str(ent.get("version") or "")
            remote_ver = ""
            if n in remote_set:
                try:
                    mf = plugin_deps.fetch_manifest(self.base_urls(), n)
                    remote_ver = str(mf.get("version") or "")
                except Cancelled:
                    raise
                except Exception:
                    remote_ver = ""
            if not local_ver:
                status = "not_installed"
            elif remote_ver and remote_ver != local_ver:
                status = "update"
            else:
                status = "installed"
            entries.append({
                "name": n,
                "version": remote_ver,
                "installed": bool(local_ver),
                "installed_version": local_ver,
                "manual": bool(ent.get("manual")),
                "used_by": used.get(n, []),
                "status": status,
            })
        return entries

    # ---------- 任务队列（新任务抢占旧任务） ----------
    def is_busy(self):
        th = self._thread
        if th is None:
            return False
        try:
            return th.isRunning()
        except RuntimeError:
            self._thread = None
            return False

    def abort(self):
        try:
            self._cancel.set()
        except Exception:
            pass

    def _dispatch(self, fn, on_ok):
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
            stale = (gen != self._gen)
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
                self.task_done.emit("", False, err)

        sig.done.connect(_done)
        self._thread = thread
        self._sig = sig
        self._inflight.append(thread)
        thread.start()
        return True

    def shutdown(self):
        self.abort()
        budget = 8.0
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

    # ---------- 对外操作 ----------
    def refresh(self):
        """刷新包列表（按当前源拉远端 + 合并本地）。"""
        def job(cancel):
            return self._build_catalog(cancel)

        def on_ok(entries):
            self.catalog = entries
            self.catalog_ready.emit(entries)

        self._dispatch(job, on_ok)

    def install(self, name):
        name = str(name or "").strip().lower()
        if not name:
            return
        if not plugin_deps.PKG_NAME_RE.match(name):
            self.task_done.emit(name, False, "包名不合法（小写字母开头）")
            return

        def job(cancel):
            db = self.deps_db
            if db is None:
                return False, "宿主不支持依赖安装"
            self.log(f"开始安装 {name} …")
            _ready, errors = plugin_deps.ensure_requirements(
                db, self.packages_dir, self.base_urls(), "", [name],
                emit=lambda ev: self._on_dep_event(name, ev),
                should_abort=lambda: cancel.is_set())
            if errors:
                return False, "；".join(errors.values())
            try:
                if self.manager is not None:
                    self.manager.refresh_dep_paths()
            except Exception:
                pass
            return True, "安装完成"

        def on_ok(result):
            ok, msg = result
            if ok:
                self._rebuild_catalog()
            self.task_done.emit(name, ok, msg)

        self._dispatch(job, on_ok)

    def uninstall(self, name):
        name = str(name or "").strip()
        if not name:
            return

        def job(cancel):
            db = self.deps_db
            if db is None:
                return False, "宿主不支持依赖管理"
            db.remove(name)
            return True, "已删除"

        def on_ok(result):
            ok, msg = result
            if ok:
                self._rebuild_catalog()
            self.task_done.emit(name, ok, msg)

        self._dispatch(job, on_ok)

    def _rebuild_catalog(self):
        try:
            self.catalog = self._build_catalog(self._cancel)
            self.catalog_ready.emit(self.catalog)
        except Exception as e:
            self.log(f"刷新列表失败: {e}")

    # ---------- 依赖安装进度 → 日志 / 进度条 ----------
    def _on_dep_event(self, name, ev):
        if not isinstance(ev, dict):
            return
        text = str(ev.get("text") or "")
        if text:
            self.log(text)
        pct = ev.get("pct")
        if isinstance(pct, (int, float)):
            self.task_progress.emit(name, int(pct))

    def log(self, text):
        self.log_line.emit(str(text))
