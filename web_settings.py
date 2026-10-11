"""设置中心（QWebEngineView 外壳）。

界面本体是项目根目录下的 ``ui/`` —— 和 .NET 版共用同一份 HTML/CSS/JS，
本模块只负责三件事：

1. 起一个 QWebEngineView 把它显示出来；
2. 通过 QWebChannel 把页面的 ``host.invoke()`` 转到既有服务上（RPC 桥）；
3. 拿不到 QtWebEngine、或找不到 ``ui/`` 时让调用方回退到原生设置窗。

**未改动**：灵动岛、副岛、班级日常主窗、下拉面板、托盘、插件宿主 —— 
它们仍是原生 Qt，本模块一行都没碰。

RPC 方法清单与 ``ui/README.md`` 的「宿主需要实现的 RPC」逐条对应，
返回值形状必须与 .NET 侧的 ``WebUiBridge.cs`` 完全一致。
"""

import json
import os
import shutil
import sys
import webbrowser

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QLabel,
                               QMessageBox, QVBoxLayout)

import paths
import theme
from settings_manager import DEFAULTS, SettingsManager

try:
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView

    WEBENGINE_AVAILABLE = True
    WEBENGINE_ERROR = ""
except Exception as _exc:                    # 缺 QtWebEngine → gui.py 回退原生设置窗
    WEBENGINE_AVAILABLE = False
    WEBENGINE_ERROR = str(_exc)


# 异步完成的哨兵：_dispatch 返回它就表示「回包稍后由信号发出」
_PENDING = object()

# 课表服务承载的两个设置键（与 .NET 的 AppSettings 之外那两个值对应）
_SCHEDULE_KEYS = {
    "schedule_advance_minutes": "advance_minutes",
    "schedule_time_offset_seconds": "time_offset_seconds",
}
_SCHEDULE_DEFAULTS = {"advance_minutes": 2, "time_offset_seconds": 0}


# ============================================================================
#  界面文件定位
# ============================================================================

def find_ui_dir():
    """返回可用的 ui/ 目录；找不到返回 None（调用方据此回退原生设置窗）。"""
    for root in (paths.RESOURCE_ROOT, paths.APP_ROOT):
        if not root:
            continue
        candidate = os.path.join(root, "ui")
        if os.path.isfile(os.path.join(candidate, "index-qt.html")):
            return candidate
    return None


def is_available():
    """Web 版设置中心是否可用：QtWebEngine 在、界面文件也在。"""
    return bool(WEBENGINE_AVAILABLE and find_ui_dir())


# ============================================================================
#  RPC 桥
# ============================================================================

class _Bridge(QObject):
    """QWebChannel 上的 ``bridge`` 对象，对应 host.js 里的 qtBridge。"""

    reply = Signal(str)

    def __init__(self, dialog):
        super().__init__(dialog)
        self._dialog = dialog
        self._settings = dialog.settings
        self._pm = dialog.plugin_manager
        self._schedule = dialog.schedule_manager
        self._controller = dialog.controller
        self._app = dialog.app
        # 值日生 / 作业管理器挂在主窗上（对应 .NET 侧注入的 IDutyService / IHomeworkService）
        self._duty = getattr(dialog, "duty_manager", None)
        self._homework = getattr(dialog, "homework_manager", None)

        self._market = None
        self._store = None

        self._log = []            # 本轮的同步日志
        self._pending = None      # (请求 id, 类型) —— 等异步任务回包
        self._deferred = None     # 回包之后再执行的动作（弹窗 / 拉起更新器）
        self._page_ready = False  # 页面报过 ui.ready 没有
        self._page_errors = []    # 页面自己报上来的脚本错误

    # ---------------------------------------------------------------- 收发

    @Slot(str)
    def invoke(self, payload):
        try:
            request = json.loads(payload)
        except Exception:
            return

        # 页面发来的通知（ui.ready / ui.error）是单程的：没有 id、不等回包。
        # 攒下来，界面起不来时用得上。（和 .NET 侧 WebUiBridge 的约定一致。）
        event = request.get("event")
        if event:
            if event == "ui.error":
                data = request.get("payload") or {}
                message = data.get("message")
                if message:
                    self._page_errors.append(str(message))
            elif event == "ui.ready":
                self._page_ready = True
            return

        req_id = request.get("id")
        method = request.get("method") or ""
        params = request.get("params") or {}

        self._deferred = None

        try:
            result = self._dispatch(method, params, req_id)
        except Exception as exc:
            self._send_error(req_id, str(exc))
            return

        if result is _PENDING:
            return                        # 异步任务完成时自己回包

        self._send(req_id, result)
        self._run_deferred()

    def _send(self, req_id, result):
        self.reply.emit(json.dumps({"id": req_id, "result": result},
                                   ensure_ascii=False))

    def _send_error(self, req_id, message):
        self.reply.emit(json.dumps({"id": req_id, "error": str(message)},
                                   ensure_ascii=False))

    def _run_deferred(self):
        """回包之后再弹窗。

        QDialog.exec() 会阻塞事件循环 —— 若在回包前就弹，页面那边
        （host.js 里 60 秒的上限）会白等，用户开着对话框停一会儿就报超时。
        """
        action = self._deferred
        self._deferred = None
        if action is not None:
            QTimer.singleShot(0, action)

    def _await(self, req_id, kind):
        self._pending = (req_id, kind)

    def _finish(self, kind, result):
        pending = self._pending
        if not pending or pending[1] != kind:
            return
        self._pending = None
        self._send(pending[0], result)

    def _fail(self, kind, message):
        pending = self._pending
        if not pending or pending[1] != kind:
            return
        self._pending = None
        self._send_error(pending[0], message)

    # ---------------------------------------------------------------- 分发

    def _dispatch(self, method, params, req_id):
        if method == "app.getVersion":
            return self._app_info()
        if method == "settings.getAll":
            return self._all_settings()
        if method == "settings.patch":
            return self._patch(params)
        if method == "settings.reset":
            return self._reset()
        if method == "plugins.list":
            return self._plugins()
        if method == "plugins.setEnabled":
            return self._set_enabled(params)
        if method == "market.status":
            return self._market_status()
        if method == "market.sync":
            return self._market_sync(req_id)
        if method == "market.rescan":
            return self._market_rescan()
        if method == "market.install":
            return self._market_install(params)
        if method == "market.uninstall":
            return self._market_uninstall(params)
        if method == "market.setEnabled":
            return self._market_set_enabled(params)
        if method == "market.updateAll":
            return self._market_update_all()
        if method == "market.setSource":
            return self._market_set_source(params)
        if method == "packages.status":
            return self._packages_status()
        if method == "packages.sync":
            return self._packages_sync(params, req_id)
        if method == "packages.install":
            return self._packages_install(params)
        if method == "packages.uninstall":
            return self._packages_uninstall(params)
        if method == "packages.setSource":
            return self._packages_set_source(params)
        if method == "dialog.open":
            return self._open_dialog(params)
        if method == "app.openFolder":
            return self._open_folder(params)

        # ---- 二级对话框（假期 / 周末 / 值日生 / 作业）----
        if method == "schedule.holidays.get":
            return self._holidays_get()
        if method == "schedule.holidays.add":
            return self._holiday_add(params)
        if method == "schedule.holidays.remove":
            return self._holiday_remove(params)
        if method == "schedule.makeup.add":
            return self._makeup_add(params)
        if method == "schedule.makeup.remove":
            return self._makeup_remove(params)
        if method == "schedule.weekend.get":
            return self._weekend_get()
        if method == "schedule.weekend.set":
            return self._weekend_set(params)
        if method == "duty.get":
            return self._duty_get()
        if method == "duty.add":
            return self._duty_add(params)
        if method == "duty.addMany":
            return self._duty_add_many(params)
        if method == "duty.remove":
            return self._duty_remove(params)
        if method == "homework.get":
            return self._homework_get()
        if method == "homework.add":
            return self._homework_add(params)
        if method == "homework.update":
            return self._homework_update(params)
        if method == "homework.remove":
            return self._homework_remove(params)
        if method == "homework.clearSubject":
            return self._homework_clear_subject(params)
        if method == "homework.save":
            self._require_homework().save_homework()
            return {"ok": True}

        # ---- 无边框窗口的窗口控制 ----
        if method == "window.minimize":
            return self._window_minimize()
        if method == "window.toggleMaximize":
            return self._window_toggle_maximize()
        if method == "window.close":
            return self._window_close()
        if method == "window.startMove":
            return self._window_start_move()
        if method == "window.startResize":
            return self._window_start_resize(params)

        if method == "update.check":
            return self._check_update()

        raise ValueError("未知的宿主方法：" + method)

    # ------------------------------------------------------------ 二级对话框
    #
    #  与 .NET 侧 WebUiBridge 的返回值形状**逐字段一致** —— 同一份 HTML 要能吃下两边。
    #  注意 Python 这边的数据是 snake_case（as_weekday / morning_split），
    #  出境前统一转成驼峰，别把 snake_case 漏到页面里。

    def _require_schedule(self):
        if self._schedule is None:
            raise RuntimeError("宿主没有提供课表服务")
        return self._schedule

    def _require_duty(self):
        if self._duty is None:
            raise RuntimeError("宿主没有提供值日生名单（请从主窗口打开设置）")
        return self._duty

    def _require_homework(self):
        if self._homework is None:
            raise RuntimeError("宿主没有提供作业管理器（请从主窗口打开设置）")
        return self._homework

    @staticmethod
    def _as_int(value, fallback=0, low=None, high=None):
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = fallback
        if low is not None:
            number = max(low, number)
        if high is not None:
            number = min(high, number)
        return number

    # ---------- 假期与调休（即时写入） ----------

    def _holidays_get(self):
        schedule = self._require_schedule()
        holidays = [{
            "start": str(h.get("start", "")),
            "end": str(h.get("end", "")),
            "name": str(h.get("name", "")),
        } for h in schedule.list_holidays()]

        makeups = [{
            "date": str(m.get("date", "")),
            "asWeekday": self._as_int(m.get("as_weekday", 0), 0, 0, 6),
        } for m in schedule.list_makeups()]

        return {"holidays": holidays, "makeupDays": makeups}

    def _holiday_add(self, params):
        self._require_schedule().add_holiday(
            str(params.get("start", "")),
            str(params.get("end", "")),
            str(params.get("name") or ""))
        return {"ok": True}

    def _holiday_remove(self, params):
        if not self._require_schedule().remove_holiday(self._as_int(params.get("index"), -1)):
            raise RuntimeError("没有这一条假期（可能已经被删掉了）。")
        return {"ok": True}

    def _makeup_add(self, params):
        self._require_schedule().add_makeup(
            str(params.get("date", "")),
            self._as_int(params.get("asWeekday"), 0, 0, 6))
        return {"ok": True}

    def _makeup_remove(self, params):
        if not self._require_schedule().remove_makeup(self._as_int(params.get("index"), -1)):
            raise RuntimeError("没有这一条调休（可能已经被删掉了）。")
        return {"ok": True}

    # ---------- 周末作息（点保存才写） ----------

    def _weekend_get(self):
        weekend = self._require_schedule().get_weekend() or {}
        return {
            "morningSplit": str(weekend.get("morning_split", "12:00")),
            "afternoonPeriods": [{
                "name": str(p.get("name", "")),
                "start": str(p.get("start", "")),
                "end": str(p.get("end", "")),
            } for p in (weekend.get("afternoon_periods") or [])],
            "courses": [str(c) for c in (weekend.get("courses") or [])],
        }

    def _weekend_set(self, params):
        split = str(params.get("morningSplit") or "").strip() or "12:00"

        periods = []
        for item in (params.get("afternoonPeriods") or []):
            if not isinstance(item, dict):
                continue
            periods.append({
                "name": str(item.get("name", "")),
                "start": str(item.get("start", "")),
                "end": str(item.get("end", "")),
            })

        courses = [str(c) for c in (params.get("courses") or [])]

        self._require_schedule().set_weekend(split, periods, courses)
        return {"ok": True}

    # ---------- 值日生名单（即时写入） ----------

    def _duty_get(self):
        duty = self._require_duty()
        return {
            "list": [str(n) for n in getattr(duty, "duty_list", [])],
            "current": duty.get_current_duty(),
            "index": self._as_int(getattr(duty, "current_index", 0), 0, 0),
        }

    def _duty_add(self, params):
        name = str(params.get("name") or "").strip()
        if not name:
            raise RuntimeError("姓名不能为空")
        self._require_duty().add_duty(name)
        return {"ok": True}

    def _duty_add_many(self, params):
        names = [str(n).strip() for n in (params.get("names") or [])]
        names = [n for n in names if n]
        if not names:
            raise RuntimeError("姓名不能为空")
        self._require_duty().add_duties(names)
        return {"ok": True, "added": len(names)}

    def _duty_remove(self, params):
        duty = self._require_duty()
        index = self._as_int(params.get("index"), -1)
        if not (0 <= index < len(getattr(duty, "duty_list", []))):
            raise RuntimeError("没有这一条值日生（可能已经被删掉了）。")
        duty.remove_duty(index)
        return {"ok": True}

    # ---------- 作业编辑器 ----------

    @staticmethod
    def _homework_subject(item):
        """组名归一化：空白科目算「未分类」—— 与 .NET 侧 HomeworkService 一致。"""
        return str(item.get("subject") or "").strip() or "未分类"

    def _homework_get(self):
        homework = self._require_homework()
        raw = homework.get_all_homework()

        items = [{
            "index": i,
            "subject": str(it.get("subject", "")),
            "content": str(it.get("content", "")),
            "date": str(it.get("date", "")),
        } for i, it in enumerate(raw)]

        # 自己分组而不是用 get_grouped_homework()：那边对空科目不归一化，
        # 会让同一个科目在两端显示成不同的组名。这里跟 .NET 对齐。
        order, buckets = [], {}
        for i, it in enumerate(raw):
            subject = self._homework_subject(it)
            if subject not in buckets:
                buckets[subject] = {"subject": subject, "date": "", "entries": []}
                order.append(subject)
            buckets[subject]["entries"].append({
                "index": i, "content": str(it.get("content", "")),
            })
            if not buckets[subject]["date"] and it.get("date"):
                buckets[subject]["date"] = str(it["date"])

        return {
            "items": items,
            "groups": [buckets[s] for s in order],
            "count": len(items),
        }

    def _homework_add(self, params):
        if not self._require_homework().add_homework(
                str(params.get("subject") or ""),
                str(params.get("content") or ""),
                str(params.get("date") or "")):
            raise RuntimeError("科目和作业内容都不能为空。")
        return {"ok": True}

    def _homework_update(self, params):
        if not self._require_homework().update_homework(
                self._as_int(params.get("index"), -1),
                str(params.get("subject") or ""),
                str(params.get("content") or ""),
                str(params.get("date") or "")):
            raise RuntimeError("这一条作业不在了（可能已经被删掉）。")
        return {"ok": True}

    def _homework_remove(self, params):
        if not self._require_homework().remove_homework(self._as_int(params.get("index"), -1)):
            raise RuntimeError("这一条作业不在了（可能已经被删掉）。")
        return {"ok": True}

    def _homework_clear_subject(self, params):
        homework = self._require_homework()
        subject = str(params.get("subject") or "")

        targets = [i for i, it in enumerate(homework.get_all_homework())
                   if self._homework_subject(it) == subject]

        # 倒序删，避免删除过程中索引前移
        for index in sorted(targets, reverse=True):
            homework.remove_homework(index)

        return {"ok": True, "removed": len(targets)}

    # ------------------------------------------------------------ 应用信息

    def _app_info(self):
        return {
            "version": self._version(),
            "platform": "win32",
            "host": "qtwebengine",
            "system": self._system_text(),
            "configPath": os.path.dirname(self._settings.path),
            "pluginsPath": self._plugins_dir(),
            "marketUrl": self._market_url(),
            # 窗口镶边归谁画 —— 设置窗口现在无边框，页内那条标题栏就是系统标题栏。
            # Qt 的无边框窗口没有系统调整边框可借，所以 resize 得由页面算边、报回来。
            "window": {
                "frame": "none",
                "resize": "js",
                "controls": ["minimize", "maximize", "close"],
            },
        }

    @staticmethod
    def _version():
        try:
            import about
            return about.get_version()
        except Exception:
            return "4.3"

    @staticmethod
    def _system_text():
        try:
            build = sys.getwindowsversion().build
        except Exception:
            build = 0
        if build >= 22000:
            name = "Windows 11"
        elif build >= 10240:
            name = "Windows 10"
        else:
            name = "Windows"
        return "%s（Build %d）" % (name, build)

    def _plugins_dir(self):
        if self._pm is not None:
            return self._pm.plugins_dir
        return paths.PLUGINS_DIR

    def _source_label(self):
        source = self._settings.get("market_source", "official")
        return {
            "official": "官方服务器 · plugins.class-daily-land.de5.net",
            "github": "GitHub · Class-Daily-Land（plugins 分支）",
            "gitee": "Gitee · class-daily-land（plugins 分支）",
        }.get(source, "插件索引服务器")

    def _market_url(self):
        source = self._settings.get("market_source", "official")
        return {
            "github": "https://github.com/LCHXXXX-1/Class-Daily-Land/tree/plugins",
            "gitee": "https://gitee.com/lchxxxx/class-daily-land/tree/plugins",
        }.get(source, "https://plugin.lchxxxx.de5.net/")

    # ---------------------------------------------------------------- 设置

    def _all_settings(self):
        data = dict(self._settings.data)

        # 「提前提醒 / 时间偏移」存在课表服务上，不在 settings.json 里
        # （源项目也是这么分的）—— 合并进来，页面才能统一读写
        if self._schedule is not None:
            schedule_data = getattr(self._schedule, "data", None) or {}
            for key, source_key in _SCHEDULE_KEYS.items():
                data[key] = int(schedule_data.get(source_key,
                                                  _SCHEDULE_DEFAULTS[source_key]))
        return data

    def _patch(self, params):
        touched_theme = False
        touched_schedule = False

        for key, value in params.items():
            if key in _SCHEDULE_KEYS:
                if self._schedule is None:
                    continue
                try:
                    self._schedule.data[_SCHEDULE_KEYS[key]] = int(value)
                    touched_schedule = True
                except (TypeError, ValueError):
                    continue
                continue

            if key not in DEFAULTS:
                continue
            if not SettingsManager._valid_type(value, DEFAULTS[key]):
                continue                      # 类型不符：忽略这一项，不写坏配置

            self._settings.set(key, value)
            if key == "theme_mode":
                touched_theme = True

        self._save_quietly(self._settings)

        if touched_schedule:
            self._save_quietly(self._schedule)
        if touched_theme:
            self._apply_theme()

        self._apply_settings()
        return {"ok": True}

    def _reset(self):
        for key, value in DEFAULTS.items():
            self._settings.set(key, value)
        self._save_quietly(self._settings)

        if self._schedule is not None:
            data = getattr(self._schedule, "data", None)
            if isinstance(data, dict):
                data.update(_SCHEDULE_DEFAULTS)
            self._save_quietly(self._schedule)

        self._apply_theme()
        self._apply_settings()
        return {"ok": True}

    @staticmethod
    def _save_quietly(obj):
        if obj is None:
            return
        try:
            obj.save()
        except Exception:
            pass

    @staticmethod
    def _apply_theme():
        try:
            theme.apply_theme(QApplication.instance())
        except Exception:
            pass

    def _apply_settings(self):
        """让主窗 / 灵动岛立刻跟上新设置（对应 v4 对话框里的 _apply）。"""
        if self._controller is not None:
            try:
                self._controller.apply_settings()
                return
            except Exception:
                pass
        apply_main = getattr(self._app, "apply_main_settings", None)
        if callable(apply_main):
            try:
                apply_main()
            except Exception:
                pass

    # ---------------------------------------------------------------- 插件

    def _plugins(self):
        if self._pm is None:
            return {"plugins": []}

        disabled = set(self._settings.get("disabled_plugins") or [])
        root = self._pm.plugins_dir

        # plugin_manager 的加载结果：(目录名, 是否成功, 说明)
        loaded = {}
        for item in getattr(self._pm, "loaded", []) or []:
            try:
                name, ok, message = item
            except (TypeError, ValueError):
                continue
            loaded[name] = (bool(ok), str(message or ""))

        plugins = []
        if os.path.isdir(root):
            for name in sorted(os.listdir(root)):
                directory = os.path.join(root, name)
                if not os.path.isdir(directory) or name == "packages":
                    continue

                meta = self._read_manifest(directory)
                ok, message = loaded.get(name, (False, ""))
                if not ok and not message:
                    message = "未加载（可能缺少 plugin.json 或入口文件）"

                plugins.append({
                    "id": name,
                    "name": (meta.get("name") or name) if meta else name,
                    "version": str(meta.get("version") or "") if meta else "",
                    "desc": str(meta.get("description") or "") if meta else "",
                    "requires": list(meta.get("requires") or []) if meta else [],
                    "enabled": name not in disabled,
                    "loaded": bool(ok),
                    "failure": "" if ok else message,
                })

        return {"plugins": plugins}

    @staticmethod
    def _read_manifest(directory):
        path = os.path.join(directory, "plugin.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _set_enabled(self, params):
        plugin_id = str(params.get("id") or "")
        enabled = bool(params.get("enabled"))
        if not plugin_id:
            raise ValueError("plugins.setEnabled 缺少 id")

        ids = [x for x in (self._settings.get("disabled_plugins") or [])
               if x != plugin_id]
        if not enabled:
            ids.append(plugin_id)

        self._settings.set("disabled_plugins", ids)
        self._save_quietly(self._settings)

        # 与原生设置窗一致：启用状态要下次启动才生效
        return {"ok": True, "restartRequired": True}

    # ------------------------------------------------------- 市场 / 依赖包

    def _emit(self, event, payload=None):
        """给页面推一条事件（单程，没有 id）。

        host.js 按「有没有 event 字段」分流 —— 有 event 的走订阅回调，
        没有的才当 RPC 回包。少了这个分流，事件会被当成对不上号的回包丢掉。
        """
        try:
            self.reply.emit(json.dumps(
                {"event": event, "payload": payload or {}},
                ensure_ascii=False))
        except Exception:
            pass

    def _ensure_market(self):
        if self._market is None:
            from plugin_market import PluginMarket
            market = PluginMarket(self._pm, self._settings, parent=self)

            market.log_line.connect(self._on_market_log)
            market.sync_finished.connect(self._on_market_finished)
            market.task_done.connect(self._on_market_task)
            market.busy_changed.connect(
                lambda busy: self._emit("market.busy", {"busy": bool(busy)}))
            market.task_progress.connect(
                lambda pid, pct: self._emit("market.progress",
                                            {"id": str(pid), "percent": int(pct)}))
            market.dep_progress.connect(self._on_market_dep)

            self._market = market
        return self._market

    def _on_market_log(self, text):
        text = str(text)
        self._log.append(text)
        self._emit("market.log", {"text": text})

    def _on_market_finished(self, ok, message):
        if ok:
            self._log.append("[完成] " + str(message))
            self._finish("market", self._market_result())
        else:
            self._fail("market", str(message))

    def _on_market_task(self, plugin_id, ok, message, restart):
        """安装 / 卸载 / 批量更新的结论。

        Python 这边这几个操作是**异步**的（丢给 QThread），RPC 早就回了
        {pending: true}，真正的结果从这里推给页面。
        """
        self._emit("market.done", {
            "id": str(plugin_id or ""),
            "ok": bool(ok),
            "message": str(message or ""),
            "restartRequired": bool(restart),
        })
        # 同步失败时 PluginMarket 走的是这条（ok=False）
        if not ok:
            self._fail("market", str(message))

    def _on_market_dep(self, ev):
        ev = ev if isinstance(ev, dict) else {}
        self._emit("market.dep", {
            "id": str(ev.get("plugin", "")),
            "stage": str(ev.get("stage", "")),
            "text": str(ev.get("text", "")),
            "percent": int(ev.get("pct", -1) or -1),
        })

    def _market_result(self):
        return self._market_status(log=self._log[-200:])

    def _market_payload(self, entries, **extra):
        market = self._ensure_market()
        try:
            busy = bool(market.is_busy())
        except Exception:
            busy = False

        payload = {
            "count": len(entries),
            "source": self._settings.get("market_source", "official"),
            "sourceLabel": self._source_label(),
            # ★ 这一端有多个可选来源，把选项交给页面去画。
            #   .NET 那边返回空数组 → 页面整行不画（它是固定单一来源）。
            "sourceOptions": [
                {"value": "official", "label": "官方服务器"},
                {"value": "github", "label": "GitHub"},
                {"value": "gitee", "label": "Gitee"},
            ],
            "lastSync": str(getattr(market, "last_sync_text", "") or ""),
            "busy": busy,
            "entries": entries,
        }
        payload.update(extra)
        return payload

    def _market_status(self, **extra):
        """列表 + 本地状态。

        用 _scan_index() 而不是直接读 catalog：前者会重新扫一遍本地插件目录，
        刚装完 / 刚卸掉的状态才是新的（也就顶替了「刷新一下」这个动作）。
        """
        market = self._ensure_market()
        try:
            raw = market._scan_index()
        except Exception:
            raw = list(market.catalog or [])

        return self._market_payload([self._map_entry(e) for e in raw], **extra)

    @staticmethod
    def _map_entry(entry):
        return {
            "id": str(entry.get("id", "") or ""),
            "name": str(entry.get("display_name") or entry.get("name")
                        or entry.get("id", "") or ""),
            "version": str(entry.get("version", "") or ""),
            "description": str(entry.get("description", "") or ""),
            "author": str(entry.get("author_name") or entry.get("author") or ""),
            "format": str(entry.get("format", "") or ""),
            "file": str(entry.get("file", "") or ""),
            "installed": bool(entry.get("installed")),
            "installedVersion": str(entry.get("installed_version") or ""),
            "disabled": bool(entry.get("disabled")),
            "updateAvailable": bool(entry.get("update_available")),
            "status": str(entry.get("status", "") or ""),
            "problem": str(entry.get("problem", "") or ""),
            "loadError": str(entry.get("load_error", "") or ""),
        }

    def _market_sync(self, req_id):
        market = self._ensure_market()
        self._log = []
        self._await(req_id, "market")
        market.check_updates()
        return _PENDING

    def _market_rescan(self):
        """刷新本地状态。

        Python 的 rescan() 也是丢给工作线程的，走一圈信号才回来；而这里要的是
        「立刻给页面一份新列表」，所以直接重新扫一遍（_market_status 会扫）。
        """
        market = self._ensure_market()
        try:
            market.rescan()
        except Exception:
            pass
        return self._market_status()

    def _market_install(self, params):
        pid = str(params.get("id") or "")
        if not pid:
            raise RuntimeError("market.install 缺少 id")
        self._ensure_market().install(pid)
        return {"ok": True, "pending": True, "message": "正在安装 …"}

    def _market_uninstall(self, params):
        pid = str(params.get("id") or "")
        if not pid:
            raise RuntimeError("market.uninstall 缺少 id")
        self._ensure_market().uninstall(pid)
        return {"ok": True, "pending": True, "message": "正在卸载 …"}

    def _market_set_enabled(self, params):
        pid = str(params.get("id") or "")
        if not pid:
            raise RuntimeError("market.setEnabled 缺少 id")
        # 这个是同步的：只改 disabled_plugins 并落盘
        self._ensure_market().set_enabled(pid, bool(params.get("enabled")))
        return {"ok": True, "restartRequired": True}

    def _market_update_all(self):
        self._ensure_market().update_all()
        return {"ok": True, "pending": True, "message": "正在批量更新 …"}

    def _market_set_source(self, params):
        source = str(params.get("source") or "")
        if source not in ("official", "github", "gitee"):
            raise RuntimeError("不认识的索引来源：" + source)
        self._settings.set("market_source", source)
        self._save_quietly(self._settings)
        self._emit("market.log", {"text": "已切换索引来源：" + source})
        return {"ok": True, "source": source, "sourceLabel": self._source_label()}

    # ---------- 依赖包 ----------

    def _ensure_store(self):
        if self._store is None:
            from package_store import PackageStore
            store = PackageStore(self._pm, self._settings, parent=self)
            store.log_line.connect(self._on_store_log)
            store.catalog_ready.connect(self._on_store_catalog)
            store.task_done.connect(self._on_store_task)
            store.busy_changed.connect(
                lambda busy: self._emit("packages.busy", {"busy": bool(busy)}))
            store.task_progress.connect(
                lambda name, pct: self._emit("packages.progress",
                                             {"name": str(name), "percent": int(pct)}))
            self._store = store
        return self._store

    def _on_store_log(self, text):
        text = str(text)
        self._log.append(text)
        self._emit("packages.log", {"text": text})

    def _on_store_catalog(self, _entries):
        self._finish("packages", self._packages_status())

    def _on_store_task(self, name, ok, message):
        self._emit("packages.done", {
            "name": str(name or ""),
            "ok": bool(ok),
            "message": str(message or ""),
        })
        if ok:
            self._finish("packages", self._packages_status())
        else:
            self._fail("packages", str(message))

    @staticmethod
    def _package_source_label(store, source_id):
        for label, sid in (store.sources() or []):
            if sid == source_id:
                return label
        return source_id

    def _packages_status(self):
        """优先用商店的完整目录；目录还没拉过（没联网）就退回本地登记表 —— 页面秒开。"""
        store = self._ensure_store()
        source_id = store.source_id()

        entries = []
        catalog = getattr(store, "catalog", None)
        for item in (catalog if isinstance(catalog, list) else []):
            entries.append({
                "name": str(item.get("name", "") or ""),
                "version": str(item.get("version", "") or ""),
                "installed": bool(item.get("installed")),
                "installedVersion": str(item.get("installed_version") or ""),
                "manual": bool(item.get("manual")),
                "usedBy": [str(x) for x in (item.get("used_by") or [])],
                "status": str(item.get("status", "") or ""),
            })

        if not entries:
            try:
                installed = store.installed() or {}
                used_by = store.used_by_map() or {}
            except Exception:
                installed, used_by = {}, {}

            for name in sorted(set(installed) | set(used_by)):
                record = installed.get(name) or {}
                entries.append({
                    "name": name,
                    "version": str(record.get("version") or ""),
                    "installed": bool(record),
                    "installedVersion": str(record.get("version") or ""),
                    "manual": bool(record.get("manual")),
                    "usedBy": [str(x) for x in (used_by.get(name) or [])],
                    "status": "installed" if record else "not_installed",
                })

        return {
            "source": source_id,
            "sourceLabel": self._package_source_label(store, source_id),
            "sourceOptions": [{"value": sid, "label": label}
                              for label, sid in (store.sources() or [])],
            "entries": entries,
        }

    def _packages_sync(self, params, req_id):
        name = str(params.get("name") or "").strip()
        store = self._ensure_store()
        self._await(req_id, "packages")
        if name:
            store.install(name)
        else:
            store.refresh()
        return _PENDING

    def _packages_install(self, params):
        name = str(params.get("name") or "").strip()
        if not name:
            raise RuntimeError("packages.install 缺少 name")
        self._ensure_store().install(name)
        return {"ok": True, "pending": True, "message": "正在准备依赖包 …"}

    def _packages_uninstall(self, params):
        name = str(params.get("name") or "").strip()
        if not name:
            raise RuntimeError("packages.uninstall 缺少 name")
        store = self._ensure_store()
        if not hasattr(store, "uninstall"):
            raise RuntimeError("这一端的依赖包商店不支持单独删除")
        store.uninstall(name)
        return {"ok": True, "pending": True, "message": "正在删除 …"}

    def _packages_set_source(self, params):
        source = str(params.get("source") or "")
        store = self._ensure_store()
        if not store.set_source(source):
            raise RuntimeError("不认识的下载源：" + source)
        self._settings.set("packages_source", source)
        self._save_quietly(self._settings)
        self._emit("packages.log", {"text": "已切换下载源：" + source})
        return {"ok": True, "source": store.source_id(),
                "sourceLabel": self._package_source_label(store, store.source_id())}

    # -------------------------------------------------- 无边框窗口的窗口控制
    #
    #  设置窗口是 Qt.FramelessWindowHint，标题栏 / 三个按钮都画在页面上，
    #  所以这几件事得由这里代劳。与 .NET 侧返回同样的形状。

    def _window_minimize(self):
        self._dialog.showMinimized()
        return {"ok": True}

    def _window_toggle_maximize(self):
        dialog = self._dialog
        if dialog.isMaximized():
            dialog.showNormal()
        else:
            dialog.showMaximized()
        return {"ok": True, "maximized": dialog.isMaximized()}

    def _window_close(self):
        # 先回包、后关窗：现在这条栈还在 QWebChannel 的调用里，
        # 直接 close 会把正在跑的栈拆掉（和弹窗类 RPC 一个道理）。
        self._deferred = self._dialog.close
        return {"ok": True}

    def _window_start_move(self):
        """接管拖动。WebView2 那边靠 app-region 由系统拖，Qt 只能显式来。"""
        handle = self._dialog.windowHandle()
        if handle is None:
            return {"ok": False}
        handle.startSystemMove()
        return {"ok": True}

    def _window_start_resize(self, params):
        """拖边缩放。页面算出鼠标落在哪条边上，这里换成 Qt 的 Edges 交给系统。"""
        handle = self._dialog.windowHandle()
        if handle is None:
            return {"ok": False}

        edge = str(params.get("edge") or "")
        edges = Qt.Edges(0)
        for name, flag in (("left", Qt.LeftEdge), ("right", Qt.RightEdge),
                           ("top", Qt.TopEdge), ("bottom", Qt.BottomEdge)):
            if name in edge:
                edges |= flag
        if edges == Qt.Edges(0):
            return {"ok": False}

        handle.startSystemResize(edges)
        return {"ok": True}

    # ------------------------------------------------------------ 对话框

    def _open_dialog(self, params):
        dialog_id = str(params.get("id") or "")

        if dialog_id.startswith("install-"):
            plugin_id = dialog_id[len("install-"):]
            market = self._ensure_market()
            self._deferred = lambda: market.install(plugin_id)
            return {"opened": True}

        actions = {
            "timetable": lambda: self._call_app("manage_timetables"),
            "weekend": lambda: self._call_app("open_weekend"),
            "holidays": lambda: self._call_app("open_holidays"),
            "statustest": lambda: self._call_app("open_status_test"),
            "duty": self._open_duty,
            "homework-editor": self._open_homework,
            "install-local": self._install_local,
        }

        action = actions.get(dialog_id)
        if action is None:
            raise ValueError("不认识的对话框：" + dialog_id)

        self._deferred = action
        return {"opened": True}

    def _call_app(self, name):
        method = getattr(self._app, name, None)
        if callable(method):
            method()

    def _open_duty(self):
        if self._app is None or not hasattr(self._app, "duty_manager"):
            return
        import menu as menu_mod
        menu_mod.DutyEditor(self._app.duty_manager, self._app,
                            parent=self._app).exec()

    def _open_homework(self):
        if self._app is None or not hasattr(self._app, "homework_manager"):
            return
        import menu as menu_mod
        menu_mod.HomeworkEditor(self._app.homework_manager, self._app,
                                parent=self._app).exec()

    def _install_local(self):
        if self._pm is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self._dialog, "选择插件文件", "",
            "Class Daily Land 插件 (*.cblplugin);;所有文件 (*)")
        if not path:
            return
        target = os.path.join(self._pm.plugins_dir, os.path.basename(path))
        try:
            shutil.copy(path, target)
        except Exception as exc:
            QMessageBox.critical(self._dialog, "安装失败", "复制文件失败：%s" % exc)
            return
        QMessageBox.information(
            self._dialog, "安装完成",
            "%s 已安装，重启后生效。" % os.path.basename(path))

    # -------------------------------------------------------------- 其它

    def _open_folder(self, params):
        folder_id = str(params.get("id") or "")

        if folder_id == "marketUrl":
            url = self._market_url()
            try:
                webbrowser.open(url)
            except Exception:
                pass
            return {"ok": True, "path": url}

        if folder_id == "plugins":
            target = self._plugins_dir()
        elif folder_id == "config":
            target = os.path.dirname(self._settings.path)
        elif folder_id == "homework":
            # 作业数据与 config.json 同放在数据根，没有单独的作业目录
            target = paths.APP_ROOT
        else:
            raise ValueError("不认识的文件夹标识：" + folder_id)

        try:
            os.makedirs(target, exist_ok=True)
            os.startfile(target)              # noqa: S606 —— Windows 专用
        except Exception:
            pass
        return {"ok": True, "path": target}

    def _check_update(self):
        """更新是独立 Launcher 干的活，这里只负责把它拉起来（回包之后再拉）。"""
        self._deferred = self._launch_updater
        return {
            "current": self._version(),
            "latest": "",
            "hasUpdate": False,
            "message": "已启动更新器，检查结果会在更新器窗口里给出。",
        }

    def _launch_updater(self):
        try:
            from launch_updater import launch_visible
        except Exception as exc:
            QMessageBox.warning(self._dialog, "更新",
                                "更新模块不可用：%s" % exc)
            return

        ok, message = launch_visible()
        if not ok:
            QMessageBox.warning(self._dialog, "更新", message)

    # -------------------------------------------------------------- 收尾

    def shutdown(self):
        for job in (self._market, self._store):
            if job is None:
                continue
            try:
                job.shutdown()
            except Exception:
                pass


# ============================================================================
#  设置窗口
# ============================================================================

class WebSettingsDialog(QDialog):
    """设置中心（Web 版）。签名与 settings_dialog_v4.SettingsDialog 对齐，便于替换。"""

    def __init__(self, settings, schedule_manager=None, plugin_manager=None,
                 controller=None, parent=None, app=None, start_page=None,
                 duty_manager=None, homework_manager=None):
        super().__init__(parent)

        self.settings = settings
        self.schedule_manager = schedule_manager
        self.plugin_manager = plugin_manager
        self.controller = controller
        self.app = app if app is not None else parent
        # 二级对话框要用：值日生名单 / 作业编辑器
        self.duty_manager = duty_manager
        self.homework_manager = homework_manager

        self.bridge = None
        self._view = None
        self._ui_dir = find_ui_dir()

        self.setWindowTitle("设置")
        self.resize(1120, 740)
        self.setMinimumSize(780, 520)

        # ★ 无边框：标题栏、最小化 / 最大化 / 关闭都画在页面上（ui/pages/settings.js
        #   的 .app-titlebar）。拖动走 window.startMove → startSystemMove()；
        #   拖边缩放走 window.startResize → startSystemResize() —— Qt 的无边框窗口
        #   没有系统调整边框可借，只能由页面算边再报回来。
        self.setWindowFlag(Qt.FramelessWindowHint, True)

        self._build(start_page)

    def _build(self, start_page):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not WEBENGINE_AVAILABLE:
            layout.addWidget(QLabel("缺少 QtWebEngine，无法显示新版设置界面。\n%s"
                                    % WEBENGINE_ERROR, self))
            return

        if self._ui_dir is None:
            layout.addWidget(QLabel("没有找到界面文件 ui/index-qt.html。", self))
            return

        view = QWebEngineView(self)
        layout.addWidget(view)

        # 暗色时先铺底色，避免加载期间闪一下白
        try:
            view.page().setBackgroundColor(
                QColor("#202020") if theme.is_dark() else QColor("#f3f3f3"))
        except Exception:
            pass

        channel = QWebChannel(view.page())
        self.bridge = _Bridge(self)
        channel.registerObject("bridge", self.bridge)
        view.page().setWebChannel(channel)

        page_settings = view.settings()
        page_settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        page_settings.setAttribute(
            QWebEngineSettings.WebAttribute.ShowScrollBars, True)

        url = QUrl.fromLocalFile(os.path.join(self._ui_dir, "index-qt.html"))
        # 不再带 chrome=native：本窗口无边框，页内标题栏就是唯一的窗口镶边
        query = "page=" + str(start_page or "general")
        url.setQuery(query)

        self._view = view
        view.load(url)

    def closeEvent(self, event):
        if self.bridge is not None:
            self.bridge.shutdown()
        super().closeEvent(event)
