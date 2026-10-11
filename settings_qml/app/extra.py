"""完整版的五个新桥：课表编辑 / 状态测试 / 插件市场 / 依赖包 / 更新。

设计原则与 bridge.py 一致：**所有数据读写都委托主程序的既有模块**
（schedule / plugin_market / package_store / launch_updater），键名、
文件格式、落盘位置全部跟原有实现逐字节一致 —— QML 侧只做界面。

主程序模块不可用（独立演示模式又没找到 ClassDailyLand-Py）时，
每个桥进入「不可用」模式：status()/list() 返回 available=False，
页面上如实显示原因，不装做完。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot


def _import_py(name: str):
    """导入 ClassDailyLand-Py 的模块；没有就返回 None（调用方走不可用分支）。"""
    try:
        return __import__(name)
    except Exception:  # noqa: BLE001 - ImportError / 模块自身的连带错误一律当不可用
        return None


def _err(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


def _norm_timetable(schedule: Any, periods: Any, timetable: Any):
    """QML 传来的节次 / 课程表过一遍主程序的 normalize_timetable 校验。

    校验逻辑（时间格式、节次上限、课程截断）跟主程序完全同源 ——
    这里不自己造一套规则，免得两处标准慢慢长岔。
    返回 (规范化对象, "") 或 (None, 错误信息)。
    """
    ok, norm, err = schedule.normalize_timetable({
        "periods": periods, "timetable": timetable})
    return (norm, "") if ok else (None, err or "课表数据没有通过校验")


# ============================================================ 课表编辑器

class TimetableStore(QObject):
    """课表的增删改查 / 导入导出 / 临时调课 —— 全部委托 ScheduleManager。

    导入导出的文件格式（JSON 的 format/version/kind 字段、CSV 的
    CSV_HEADERS 表头、BOM+CRLF）都由主程序模块决定，这里一个字节都不碰。
    """

    changed = Signal()

    def __init__(self, parent: QObject | None = None, schedule: Any = None) -> None:
        super().__init__(parent)
        self._schedule = schedule          # ScheduleManager 实例
        self._mod = _import_py("schedule")  # normalize_timetable 等模块级函数

    @Slot(result=bool)
    def isAvailable(self) -> bool:
        return self._schedule is not None

    @Slot(result="QVariantList")
    def list(self) -> list[dict[str, Any]]:  # noqa: A003
        if self._schedule is None:
            return []
        manager = self._schedule
        active = manager.active_name
        result = []
        for name, tt in manager.data["timetables"].items():
            periods = tt.get("periods", []) if isinstance(tt, dict) else []
            timetable = tt.get("timetable", {}) if isinstance(tt, dict) else {}
            result.append({
                "name": str(name),
                "active": name == active,
                "periods": len(periods),
                "courses": sum(len(v or []) for v in timetable.values()
                               if isinstance(v, list)),
            })
        return result

    @Slot(str, result="QVariantMap")
    def detail(self, name: str) -> dict[str, Any]:
        if self._schedule is None:
            return {}
        tt = self._schedule.get_timetable(name)
        if not tt:
            return {}
        return {
            "name": str(name),
            "periods": [dict(p) for p in tt.get("periods", [])],
            "timetable": {str(k): list(v or []) for k, v in
                          tt.get("timetable", {}).items()},
        }

    @Slot(str, result=bool)
    def switch(self, name: str) -> bool:
        if self._schedule is None:
            return False
        ok = bool(self._schedule.switch_timetable(name))
        if ok:
            self.changed.emit()
        return ok

    @Slot(str, str, result="QVariantMap")
    def create(self, name: str, copy_from: str) -> dict[str, Any]:
        if self._schedule is None:
            return _err("课表服务不可用")
        ok = self._schedule.create_timetable(name.strip(),
                                             copy_from.strip() or None)
        if not ok:
            return _err("名字为空或已存在同名课表")
        self.changed.emit()
        return {"ok": True, "name": name.strip()}

    @Slot(str, str, result="QVariantMap")
    def rename(self, old: str, new: str) -> dict[str, Any]:
        if self._schedule is None:
            return _err("课表服务不可用")
        ok = self._schedule.rename_timetable(old, new.strip())
        if not ok:
            return _err("改不了：课表不存在、名字为空或重名")
        self.changed.emit()
        return {"ok": True, "name": new.strip()}

    @Slot(str, result="QVariantMap")
    def delete(self, name: str) -> dict[str, Any]:  # noqa: A003
        if self._schedule is None:
            return _err("课表服务不可用")
        ok = self._schedule.delete_timetable(name)
        if not ok:
            return _err("删不了：默认课表或最后一张课表不能删")
        self.changed.emit()
        return {"ok": True}

    @Slot(str, "QVariant", "QVariant", result="QVariantMap")
    def update(self, name: str, periods: Any, timetable: Any) -> dict[str, Any]:
        """保存一张课表（节次 + 课程）。写入前过 normalize_timetable 校验。"""
        if self._schedule is None or self._mod is None:
            return _err("课表服务不可用")
        norm, err = _norm_timetable(self._mod, periods, timetable)
        if norm is None:
            return _err(err)
        if not self._schedule.update_timetable(name, norm["periods"],
                                               norm["timetable"]):
            return _err("课表不存在")
        self.changed.emit()
        return {"ok": True}

    # ---------------- 导入 / 导出 ----------------

    @Slot(str, str, str, result="QVariantMap")
    def export(self, name: str, fmt: str, target_dir: str) -> dict[str, Any]:
        """导出为 JSON / CSV 文件，落到 target_dir，文件名用主程序的规则。"""
        import os  # noqa: PLC0415

        if self._schedule is None:
            return _err("课表服务不可用")
        fmt = "csv" if str(fmt).lower() == "csv" else "json"
        try:
            filename = self._schedule.export_filename(fmt=fmt, names=[name])
            path = os.path.join(target_dir, filename)
            written = self._schedule.write_export(path, fmt=fmt, names=[name])
            return {"ok": True, "path": str(written)}
        except Exception as exc:  # noqa: BLE001
            return _err(f"导出失败：{exc}")

    @Slot(str, str, result="QVariantMap")
    def exportText(self, name: str, fmt: str) -> dict[str, Any]:
        if self._schedule is None:
            return _err("课表服务不可用")
        try:
            text = self._schedule.export_text(
                fmt="csv" if str(fmt).lower() == "csv" else "json", names=[name])
            return {"ok": True, "text": text}
        except Exception as exc:  # noqa: BLE001
            return _err(f"导出失败：{exc}")

    @Slot(str, str, result="QVariantMap")
    def previewImport(self, text: str, filename: str) -> dict[str, Any]:
        if self._schedule is None:
            return _err("课表服务不可用")
        try:
            return dict(self._schedule.preview_import(text, filename))
        except Exception as exc:  # noqa: BLE001
            return _err(str(exc) or "解析失败")

    @Slot(str, str, str, result="QVariantMap")
    def importText(self, text: str, mode: str, filename: str) -> dict[str, Any]:
        if self._schedule is None:
            return _err("课表服务不可用")
        try:
            result = self._schedule.import_text(
                text, mode="replace" if mode == "replace" else "merge",
                filename=filename)
            self.changed.emit()
            return {"ok": True, **result}
        except Exception as exc:  # noqa: BLE001
            return _err(str(exc) or "导入失败")

    @Slot(str, str, result="QVariantMap")
    def importFromFile(self, path: str, mode: str) -> dict[str, Any]:
        if self._schedule is None:
            return _err("课表服务不可用")
        try:
            result = self._schedule.import_file(
                path, mode="replace" if mode == "replace" else "merge")
            self.changed.emit()
            return {"ok": True, **result}
        except Exception as exc:  # noqa: BLE001
            return _err(str(exc) or "导入失败")

    @Slot(str, result="QVariantMap")
    def previewFile(self, path: str) -> dict[str, Any]:
        if self._schedule is None:
            return _err("课表服务不可用")
        try:
            return dict(self._schedule.preview_file(path))
        except Exception as exc:  # noqa: BLE001
            return _err(str(exc) or "解析失败")

    # ---------------- 临时调课 ----------------

    @Slot(result="QVariantMap")
    def tempAdjust(self) -> dict[str, Any]:
        if self._schedule is None:
            return {"date": "", "courses": []}
        data = self._schedule.get_temp_adjust()
        return {"date": str(data.get("date") or ""),
                "courses": [str(c) for c in (data.get("courses") or [])]}

    @Slot(str, "QVariant", result="QVariantMap")
    def setTempAdjust(self, date: str, courses: Any) -> dict[str, Any]:
        if self._schedule is None:
            return _err("课表服务不可用")
        items = [str(c).strip() for c in (courses or [])
                 if str(c).strip()] if isinstance(courses, list) else []
        self._schedule.set_temp_adjust(date.strip(), items)
        self.changed.emit()
        return {"ok": True}

    @Slot(result="QVariantMap")
    def clearTempAdjust(self) -> dict[str, Any]:
        if self._schedule is None:
            return _err("课表服务不可用")
        self._schedule.clear_temp_adjust()
        self.changed.emit()
        return {"ok": True}


# ============================================================ 状态测试

class StatusTester(QObject):
    """参数试算 + 灵动岛预览数据 + 情景演示（驱动真实灵动岛）。

    试算逻辑照 test_dialog.StatusTestDialog._update 搬的：
    schedule.get_status() 是权威，这里只负责把它翻成 QML 好画的形状。
    """

    def __init__(self, parent: QObject | None = None, schedule: Any = None,
                 settings: Any = None, controller: Any = None) -> None:
        super().__init__(parent)
        self._schedule = schedule
        self._settings = settings
        self._controller = controller

    @Slot(result=bool)
    def isAvailable(self) -> bool:
        return self._schedule is not None

    @Slot(str, int, int, int, result="QVariantMap")
    def compute(self, iso_time: str, offset: int, advance: int,
                countdown: int) -> dict[str, Any]:
        if self._schedule is None:
            return {"state": "none", "text": "课表服务不可用（演示模式）",
                    "ratio": 0.0, "width": 0.6, "isEnd": False, "detail": []}
        try:
            now = datetime.fromisoformat(iso_time)
        except ValueError:
            now = datetime.now()

        status = self._schedule.get_status(
            now, advance_minutes=int(advance), offset_seconds=int(offset))
        st = status.get("status")
        until_sec = status.get("until_sec")

        if st == "upcoming" and until_sec is not None and until_sec <= countdown:
            state = "countdown"
            text = f"下节 {status['course']} · {until_sec}s"
            ratio = max(0.0, min(1.0, until_sec / max(1, countdown)))
            width = 1.0
        elif st == "upcoming":
            state = "upcoming"
            text = f"下节 {status['course']} · {status['until_min']}分钟后"
            ratio, width = 0.0, 0.6
        elif st == "ongoing":
            state = "ongoing"
            text = f"本节：{status['course']} 还剩 {status['remain_min']}分钟"
            ratio, width = 1.0, 1.0
        elif st == "holiday":
            state = "none"
            name = status.get("name") or ""
            text = f"假期中 · {name}" if name else "假期中"
            ratio, width = 0.0, 0.6
        elif st == "none":
            state = "none"
            text = "今日无课"
            ratio, width = 0.0, 0.6
        else:
            state = "done"
            text = "今日课程已结束"
            ratio, width = 0.0, 0.6

        lines = [
            f"状态：{state}（schedule={st}）",
            f"岛文案：{text}",
            f"测试时刻：{now.strftime('%H:%M:%S')}",
            f"参数：偏移 {int(offset):+d}s，提前 {int(advance)} 分，"
            f"倒计时窗口 {int(countdown)}s",
        ]

        idx = status.get("index")
        periods = self._schedule.periods_for(now)
        if idx is not None and 0 <= idx < len(periods):
            p = periods[idx]
            lines.append(f"课程：{status.get('course')}（{p.get('name', '')}）")
            lines.append(f"课表时间：{p['start']} - {p['end']}")
            # 有效上课时刻 = 课表开始 + 偏移 - 提前；进入倒计时再往前推一个窗口
            try:
                from datetime import timedelta  # noqa: PLC0415

                hh, mm = str(p["start"]).split(":")[:2]
                printed = now.replace(hour=int(hh), minute=int(mm),
                                      second=0, microsecond=0)
                effective = (printed + timedelta(seconds=int(offset))
                             - timedelta(minutes=int(advance)))
                cd_at = effective - timedelta(seconds=int(countdown))
                lines.append(f"有效上课：{effective.strftime('%H:%M:%S')}"
                             f"（提前 {int(advance)} 分 / 偏移 {int(offset)}s）")
                lines.append(f"进入倒计时：{cd_at.strftime('%H:%M:%S')}")
            except (ValueError, KeyError):
                pass
        if st == "upcoming" and until_sec is not None:
            m, s = divmod(max(0, int(until_sec)), 60)
            lines.append(f"距上课：{m}分{s:02d}秒")
        elif st == "ongoing":
            m, s = divmod(max(0, int(status.get("remain_sec", 0))), 60)
            lines.append(f"距下课：{m}分{s:02d}秒")

        return {"state": state, "text": text, "ratio": ratio, "width": width,
                "isEnd": state == "done", "detail": lines}

    @Slot(int, int, int, float, result=bool)
    def runScenario(self, advance_sec: int, countdown_sec: int,
                    end_hold_sec: int, speed: float) -> bool:
        """让**真实灵动岛**跑一轮完整情景（嵌入模式）；演示模式返回 False。"""
        if self._controller is None:
            return False
        try:
            return bool(self._controller.run_scenario_test(
                int(advance_sec), int(countdown_sec), int(end_hold_sec),
                float(speed)))
        except Exception:  # noqa: BLE001
            return False

    @Slot(int, int, int, result=bool)
    def saveParams(self, offset: int, advance: int, countdown: int) -> bool:
        """把试算参数写回：偏移/提前挂课表服务（带夹取），倒计时进 settings.json。"""
        if self._schedule is None or self._settings is None:
            return False
        try:
            self._schedule.set_time_offset_seconds(int(offset))
            self._schedule.set_advance_minutes(int(advance))
            self._settings["island_countdown_sec"] = int(countdown)
            self._settings.save()
            return True
        except Exception:  # noqa: BLE001
            return False


# ============================================================ 插件市场

class MarketStore(QObject):
    """插件市场 —— 直接复用主程序的 PluginMarket（QObject + 后台线程 + 信号）。

    异步操作（同步索引 / 安装 / 卸载 / 批量更新）的结果通过下面的信号推给
    QML；条目字段形状与 web_settings._map_entry 一致（id/name/version/...）。
    """

    logLine = Signal(str)
    busyChanged = Signal(bool)
    syncFinished = Signal(bool, str)
    catalogReady = Signal("QVariantList")
    taskProgress = Signal(str, int)
    taskDone = Signal(str, bool, str, bool)
    depProgress = Signal("QVariantMap")

    def __init__(self, parent: QObject | None = None, settings: Any = None,
                 plugin_manager: Any = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._pm = plugin_manager
        self._market: Any = None

    # ---- 内部 ----

    def _ensure(self):
        if self._market is not None:
            return self._market
        if self._settings is None or self._pm is None:
            return None
        mod = _import_py("plugin_market")
        if mod is None:
            return None
        market = mod.PluginMarket(self._pm, self._settings, parent=self)
        market.log_line.connect(self.logLine)
        market.busy_changed.connect(self.busyChanged)
        market.sync_finished.connect(self.syncFinished)
        market.task_progress.connect(self.taskProgress)
        market.dep_progress.connect(self._map_dep)
        market.task_done.connect(self._on_task_done)
        self._market = market
        return market

    def _on_task_done(self, plugin_id: str, ok: bool, message: str,
                      restart: bool) -> None:
        self.taskDone.emit(str(plugin_id or ""), bool(ok),
                           str(message or ""), bool(restart))

    def _map_dep(self, ev: Any) -> None:
        ev = ev if isinstance(ev, dict) else {}
        self.depProgress.emit({
            "id": str(ev.get("plugin", "")),
            "stage": str(ev.get("stage", "")),
            "text": str(ev.get("text", "")),
            "percent": int(ev.get("pct", -1) or -1),
        })

    @staticmethod
    def _map_entry(entry: dict[str, Any]) -> dict[str, Any]:
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

    # ---- 给 QML 的槽 ----

    @Slot(result=bool)
    def isAvailable(self) -> bool:
        return self._settings is not None and self._pm is not None \
            and _import_py("plugin_market") is not None

    @Slot(result="QVariantMap")
    def status(self) -> dict[str, Any]:
        market = self._ensure()
        if market is None:
            return {"available": False, "count": 0, "entries": [],
                    "reason": "插件市场需要主程序环境（嵌入或 bootstrap 模式）"}
        try:
            raw = market._scan_index()
        except Exception:  # noqa: BLE001
            raw = list(market.catalog or [])
        source = self._settings.get("market_source", "official")
        return {
            "available": True,
            "count": len(raw),
            "source": str(source),
            "lastSync": str(getattr(market, "last_sync_text", "") or ""),
            "busy": bool(market.is_busy()),
            "entries": [self._map_entry(e) for e in raw],
        }

    @Slot()
    def sync(self) -> None:
        market = self._ensure()
        if market is not None:
            market.check_updates()

    @Slot()
    def rescan(self) -> None:
        market = self._ensure()
        if market is not None:
            market.rescan()

    @Slot(str)
    def install(self, plugin_id: str) -> None:
        market = self._ensure()
        if market is not None:
            market.install(plugin_id)

    @Slot(str)
    def uninstall(self, plugin_id: str) -> None:
        market = self._ensure()
        if market is not None:
            market.uninstall(plugin_id)

    @Slot()
    def updateAll(self) -> None:
        market = self._ensure()
        if market is not None:
            market.update_all()

    @Slot(str, bool)
    def setEnabled(self, plugin_id: str, enabled: bool) -> None:
        market = self._ensure()
        if market is not None:
            market.set_enabled(plugin_id, enabled)

    @Slot(str, result=bool)
    def setSource(self, source: str) -> bool:
        if self._settings is None:
            return False
        if source not in ("official", "github", "gitee"):
            return False
        self._settings.set("market_source", source)
        self._settings.save()
        return True

    def shutdown(self) -> None:
        """窗口关闭时等后台任务收尾（PluginMarket.shutdown 的语义）。"""
        if self._market is not None:
            try:
                self._market.shutdown()
            except Exception:  # noqa: BLE001
                pass


# ============================================================ 依赖包管理

class PackageBridge(QObject):
    """第三方依赖包 —— 复用主程序的 PackageStore（同样 headless QObject）。"""

    logLine = Signal(str)
    busyChanged = Signal(bool)
    catalogReady = Signal("QVariantList")
    taskProgress = Signal(str, int)
    taskDone = Signal(str, bool, str)

    def __init__(self, parent: QObject | None = None, settings: Any = None,
                 plugin_manager: Any = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._pm = plugin_manager
        self._store: Any = None

    def _ensure(self):
        if self._store is not None:
            return self._store
        if self._settings is None or self._pm is None:
            return None
        mod = _import_py("package_store")
        if mod is None:
            return None
        store = mod.PackageStore(self._pm, self._settings, parent=self)
        store.log_line.connect(self.logLine)
        store.busy_changed.connect(self.busyChanged)
        store.task_progress.connect(self.taskProgress)
        store.task_done.connect(self.taskDone)
        store.catalog_ready.connect(self._on_catalog)
        self._store = store
        return store

    def _on_catalog(self, entries: Any) -> None:
        self.catalogReady.emit([self._map_entry(e) for e in (entries or [])])

    @staticmethod
    def _map_entry(entry: dict[str, Any]) -> dict[str, Any]:
        entry = entry if isinstance(entry, dict) else {}
        return {
            "name": str(entry.get("name", "") or ""),
            "installed": bool(entry.get("installed")),
            "version": str(entry.get("version", "") or ""),
            "installedVersion": str(entry.get("installed_version", "") or ""),
            "updateAvailable": bool(entry.get("update_available")),
            "usedBy": [str(u) for u in (entry.get("used_by") or [])],
            "status": str(entry.get("status", "") or ""),
            "problem": str(entry.get("problem", "") or ""),
        }

    @Slot(result=bool)
    def isAvailable(self) -> bool:
        return self._settings is not None and self._pm is not None \
            and _import_py("package_store") is not None

    @Slot(result="QVariantMap")
    def status(self) -> dict[str, Any]:
        store = self._ensure()
        if store is None:
            return {"available": False, "entries": [],
                    "reason": "依赖包管理需要主程序环境（嵌入或 bootstrap 模式）"}
        entries = [self._map_entry(e) for e in (store.catalog or [])]
        return {
            "available": True,
            "source": str(store.source_id()),
            "baseUrls": [str(u) for u in store.base_urls()],
            "busy": bool(store.is_busy()),
            "entries": entries,
        }

    @Slot()
    def refresh(self) -> None:
        store = self._ensure()
        if store is not None:
            store.refresh()

    @Slot(str)
    def install(self, name: str) -> None:
        store = self._ensure()
        if store is not None:
            store.install(name)

    @Slot(str)
    def uninstall(self, name: str) -> None:
        store = self._ensure()
        if store is not None:
            store.uninstall(name)

    @Slot(str, result=bool)
    def setSource(self, sid: str) -> bool:
        store = self._ensure()
        if store is None:
            return False
        return bool(store.set_source(sid))

    def shutdown(self) -> None:
        if self._store is not None:
            try:
                self._store.shutdown()
            except Exception:  # noqa: BLE001
                pass


# ============================================================ 更新

class UpdaterBridge(QObject):
    """更新链路 —— 复用主程序的 launch_updater（含 dev_guard 源码运行保护）。"""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    @Slot(result="QVariantMap")
    def state(self) -> dict[str, Any]:
        mod = _import_py("launch_updater")
        if mod is None:
            return {"available": False,
                    "reason": "找不到主程序的 launch_updater 模块"}
        guard = _import_py("dev_guard")
        hits: list[str] = []
        guard_on = False
        if guard is not None:
            try:
                guard_on = bool(guard.guard_enabled())
                if guard_on:
                    found = guard.scan_source_entry(mod._app_dir())
                    hits = [str(h[0]) for h in (found or [])]
            except Exception:  # noqa: BLE001
                pass
        launcher = bool(mod._find_file(mod.LAUNCHER_EXE)
                        or mod._find_file(mod.LAUNCHER_PY))
        return {"available": True, "launcherFound": launcher,
                "guardEnabled": guard_on, "sourceHits": hits}

    @Slot(result="QVariantMap")
    def checkNow(self) -> dict[str, Any]:
        mod = _import_py("launch_updater")
        if mod is None:
            return _err("找不到主程序的 launch_updater 模块")
        try:
            ok, msg = mod.launch_visible()
            return {"ok": bool(ok), "message": str(msg or "")}
        except Exception as exc:  # noqa: BLE001
            return _err(f"启动更新器失败：{exc}")
