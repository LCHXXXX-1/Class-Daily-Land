"""Python ↔ QML 的桥。

暴露给 QML 的上下文属性（在 window.py 里挂上，且**必须持住引用**）：

    Paths      路径助手（绝对 file:// URL）
    Config     设置读写（`Config.data.xxx` 读、`Config.set("xxx", v)` 写）
    ConfigMeta 单个设置的取值范围 / 类型（QML 控件据此自动配 from/to/step）
    AppInfo    版本、系统、宿主、配置目录（关于页用）
    Folders    打开配置 / 插件 / 作业目录
    Plugins    扫 plugins/ 目录得到的插件清单
    Homework   作业条目（JSON 持久化）

每个桥都有两种工作模式：

* **演示模式**（默认）：自己读写 data/ 下的 JSON —— 独立 `run.py` 用这套，
  自检也跑这套；
* **嵌入模式**：构造时注入 ClassDailyLand-Py 的真实管理器
  （SettingsManager / ScheduleManager / StudentOnDuty / HomeworkManager /
  PluginManager），读写全部穿透到主程序正在用的同一份对象 ——
  改完设置主窗 / 灵动岛立刻能感知，数据也落在同一个 settings/ 目录。

设计上刻意不引入双向绑定：控件在构造时读一次 `Config`，用户操作时写回
（跟 Class Widgets 2 的 `Configs.data.*` + `Configs.set(...)` 同一个模型）。
这样 QML 侧不需要任何监听逻辑，也不会出现「写回 → 通知 → 再写回」的回环。
"""
from __future__ import annotations

import platform
import sys
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from . import __version__, paths, schema
from .qmlcompat import py as _py
from .store import read_json, write_json_atomic

SETTINGS_FILE = paths.CONFIG_DIR / "settings.json"

# 「提前提醒 / 时间偏移」不在 settings.json 里，挂在课表服务上 ——
# 与 web_settings._SCHEDULE_KEYS 同一套映射（键名是两端共用的契约）。
SCHEDULE_KEYS = {
    "schedule_advance_minutes": "advance_minutes",
    "schedule_time_offset_seconds": "time_offset_seconds",
}


# ============================================================== 设置

class Config(QObject):
    """设置读写。原子写 + 逐字段夹取；值没变就不落盘。

    嵌入模式下委托给注入的 SettingsManager（键空间以它的 data 为准：
    只有主程序认识的键才可写，schema 只负责类型校验与范围夹取）。
    """

    changed = Signal(str)      # 某一个键变了
    reloaded = Signal()        # 整份重读（恢复默认之后）

    def __init__(
        self,
        parent: QObject | None = None,
        settings: Any = None,
        schedule: Any = None,
        on_setting_changed: Any = None,
        on_theme_changed: Any = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings          # 嵌入模式：SettingsManager
        self._schedule = schedule          # 嵌入模式：ScheduleManager
        self._on_setting_changed = on_setting_changed
        self._on_theme_changed = on_theme_changed
        self._data: dict[str, Any] = schema.defaults()
        self._unknown: dict[str, Any] = {}   # 磁盘上有、schema 里没有的键：原样保留，不悄悄丢掉
        if settings is None:
            self._load()

    # ------------------------------------------------------------ 读

    def _load(self) -> None:
        raw = read_json(SETTINGS_FILE, {})
        if not isinstance(raw, dict):
            raw = {}
        clamped: list[str] = []
        for key, field in schema.BY_KEY.items():
            if key not in raw:
                continue
            # 类型不符 / 越界：夹回合法值并记下来，稍后回写
            if field.is_out_of_range(raw[key]):
                clamped.append(key)
            self._data[key] = field.coerce(raw[key])
        for key, value in raw.items():
            if key not in schema.BY_KEY:
                self._unknown[key] = value
        if clamped:
            # 源项目的教训：越界值静默生效会让两处显示对不上（时间偏移差了 4 小时 24 分）。
            # 这里发现越界就地归位并回写，配置自愈。
            self._save()
            print(f"[Config] 越界值已归位：{', '.join(clamped)}")

    def _get_data(self) -> dict[str, Any]:
        if self._settings is not None:
            merged = dict(schema.defaults())
            merged.update(self._settings.data)
            if self._schedule is not None:
                schedule_data = getattr(self._schedule, "data", None) or {}
                for key, source_key in SCHEDULE_KEYS.items():
                    merged[key] = int(schedule_data.get(source_key, merged[key]))
            return merged
        return self._data

    data = Property("QVariantMap", _get_data, notify=reloaded)

    @Slot(str, "QVariant", result="QVariant")
    def get(self, key: str, fallback: Any = None) -> Any:
        if self._settings is not None:
            if key in SCHEDULE_KEYS:
                source_key = SCHEDULE_KEYS[key]
                field = schema.BY_KEY.get(key)
                default = field.default if field else fallback
                schedule_data = getattr(self._schedule, "data", None) or {}
                return schedule_data.get(source_key, default)
            if key in self._settings.data:
                return self._settings.data[key]
            field = schema.BY_KEY.get(key)
            return field.default if field else fallback
        if key in self._data:
            return self._data[key]
        field = schema.BY_KEY.get(key)
        return field.default if field else fallback

    @Slot(str, result=bool)
    def isManaged(self, key: str) -> bool:
        """这一项在当前模式下是不是真实生效。

        演示模式恒 True；嵌入模式只认主程序认识的键（settings.json 的键 +
        挂在课表服务上的两个）。QML 侧用它把「演示专属但不落盘」的开关
        如实地禁用掉，而不是让用户改一个不会保存的值。
        """
        if self._settings is None:
            return True
        if key in SCHEDULE_KEYS:
            return self._schedule is not None
        return key in self._settings.data

    @Slot(str, result="QVariantMap")
    def meta(self, key: str) -> dict[str, Any]:
        """给 QML 控件用的取值范围。控件不必把 min/max 再抄一遍。"""
        field = schema.BY_KEY.get(key)
        if field is None:
            return {}
        return {
            "key": field.key,
            "kind": field.kind,
            "default": field.default,
            "low": field.low,
            "high": field.high,
            # ★ 没有 step 就如实给 null（外加 hasStep=false），别塞 1：
            #   塞 1 的后果是 SliderSetting 的 stepOf() 以为「schema 给了步长」，
            #   1 × scale(=100) = 100 > 整个行程(35) → 每格都吸附到端点，
            #   滑块永远停在最小值（也就是「拉不动」）。
            "step": field.step,
            "hasStep": field.step is not None,
            "hasRange": field.low is not None or field.high is not None,
        }

    @Slot(str, result=bool)
    def isKeyLocked(self, key: str) -> bool:
        """与 Class Widgets 2 的 `Configs.isKeyLocked(key)` 同名同形。

        本应用暂时没有「插件托管某个设置」的机制，所以恒为 False；
        留着是为了把插件锁做进来时，QML 侧的 `enabled: !Config.isKeyLocked(k)` 不用改。
        """
        return False

    # ------------------------------------------------------------ 写

    @Slot(str, "QVariant", result=bool)
    def set(self, key: str, value: Any) -> bool:  # noqa: A003 - 与 QML 侧 API 对齐
        field = schema.BY_KEY.get(key)
        if field is None:
            print(f"[Config] 未知设置项，已忽略：{key}")
            return False
        coerced = field.coerce(value)

        if self._settings is not None:
            return self._set_managed(key, coerced, field)
        return self._set_demo(key, coerced)

    def _set_managed(self, key: str, coerced: Any, field: Any) -> bool:
        """嵌入模式写回：课表键走课表服务，其余走 SettingsManager。"""
        if key in SCHEDULE_KEYS:
            if self._schedule is None:
                return False
            source_key = SCHEDULE_KEYS[key]
            # 夹取已在 field.coerce 做过（0–60 / ±1800，与源项目一致）
            if self._schedule.data.get(source_key) == coerced:
                return False
            self._schedule.data[source_key] = coerced
            self._save_manager(self._schedule)
            self.changed.emit(key)
            self._notify(key)
            return True

        if key not in self._settings.data:
            # 主程序没有这一项（QML 演示专属键）：拒绝，不污染共用配置
            print(f"[Config] 嵌入模式下没有这项设置，已忽略：{key}")
            return False
        if self._settings.data.get(key) == coerced:
            return False
        self._settings.set(key, coerced)
        self._save_manager(self._settings)
        self.changed.emit(key)
        self._notify(key)
        return True

    def _set_demo(self, key: str, coerced: Any) -> bool:
        if self._data.get(key) == coerced:
            return False        # 值没变就别落盘（源项目「这一项真的变了吗」的教训）
        self._data[key] = coerced
        self._save()
        self.changed.emit(key)
        return True

    def _notify(self, key: str) -> None:
        """嵌入模式下让主程序跟上新设置（主题单独一路，其余走 apply）。

        延迟一拍：QML 信号处理里直接改主题 / 重建主窗容易撞上还在跑的调用栈，
        web_settings 的弹窗回调也是这么处理 QDialog.exec() 阻塞的。
        """
        from PySide6.QtCore import QTimer  # noqa: PLC0415

        if key == "theme_mode" and self._on_theme_changed is not None:
            QTimer.singleShot(0, self._on_theme_changed)
        if self._on_setting_changed is not None:
            QTimer.singleShot(0, self._on_setting_changed)

    @staticmethod
    def _save_manager(manager: Any) -> None:
        try:
            manager.save()
        except Exception as exc:  # noqa: BLE001 - 落盘失败不该打断界面
            print(f"[Config] 保存失败：{exc}")

    @Slot(result=bool)
    def reset(self) -> bool:
        if self._settings is not None:
            for key in list(self._settings.data):
                field = schema.BY_KEY.get(key)
                if field is not None:
                    self._settings.set(key, field.default)
            self._save_manager(self._settings)
            if self._schedule is not None:
                self._schedule.data["advance_minutes"] = 2
                self._schedule.data["time_offset_seconds"] = 0
                self._save_manager(self._schedule)
            self.reloaded.emit()
            self._notify("theme_mode")   # 默认主题也回去了，让主程序跟上
            return True
        self._data = schema.defaults()
        self._save()
        self.reloaded.emit()
        return True

    @Slot(result=str)
    def filePath(self) -> str:
        if self._settings is not None:
            return str(self._settings.path)
        return str(SETTINGS_FILE)

    def _save(self) -> None:
        write_json_atomic(SETTINGS_FILE, {**self._unknown, **self._data})


# ============================================================== 应用信息

def _windows_display_name() -> str:
    if sys.platform != "win32":
        return platform.platform()
    release, version, _csd, _ptype = platform.win32_ver()
    try:
        build = int(version.split(".")[-1])
    except (ValueError, IndexError):
        build = 0
    if build >= 22000:
        return f"Windows 11 {release} (Build {build})"
    if build:
        return f"Windows 10 {release} (Build {build})"
    return f"Windows {release}"


def _supports_mica() -> bool:
    """Win11 22H2（Build 22621）起才有系统云母；Win10 静默降级。"""
    if sys.platform != "win32":
        return False
    try:
        build = int(platform.version().split(".")[-1])
    except (ValueError, IndexError):
        return False
    return build >= 22621


class AppInfo(QObject):
    """关于页要的那些信息。嵌入模式下版本 / 目录来自主程序。"""

    def __init__(
        self,
        parent: QObject | None = None,
        version: str = "",
        config_path: Any = None,
        plugins_path: Any = None,
    ) -> None:
        super().__init__(parent)
        self._version = version or __version__
        self._config_path = config_path
        self._plugins_path = plugins_path

    @Slot(result=str)
    def version(self) -> str:
        return self._version

    @Slot(result=str)
    def system(self) -> str:
        return _windows_display_name()

    @Slot(result=str)
    def host(self) -> str:
        import PySide6  # noqa: PLC0415 - 只在问的时候才导入

        stack = "Qt Quick (QML) + RinUI"
        if self._config_path is not None:
            stack += "（嵌入主程序）"
        return f"Python {platform.python_version()} + PySide6 {PySide6.__version__} + QML"

    @Slot(result=str)
    def uiStack(self) -> str:
        return "Qt Quick (QML) + RinUI"

    @Slot(result=bool)
    def micaAvailable(self) -> bool:
        return _supports_mica()

    @Slot(result=str)
    def configPath(self) -> str:
        if self._config_path is not None:
            return str(self._config_path)
        return str(paths.CONFIG_DIR)

    @Slot(result=str)
    def pluginsPath(self) -> str:
        if self._plugins_path is not None:
            return str(self._plugins_path)
        return str(paths.PLUGINS_DIR)

    @Slot(result=str)
    def platform(self) -> str:
        return sys.platform

    @Slot(result=bool)
    def motionEnabled(self) -> bool:
        """系统「动画效果」是否开着（Qt 6.5+ 有关闭后durationScale 为 0）。

        QML 侧读不到 QStyleHints，只能由 Python 查一次。
        RinUI 的 theme/appearance 里没有这个开关，所以别去那儿找。
        """
        try:
            from PySide6.QtGui import QGuiApplication  # noqa: PLC0415

            app = QGuiApplication.instance()
            if app is None:
                return True
            scale = app.styleHints().animationDurationScale()
            return float(scale) > 0.0
        except Exception:  # noqa: BLE001 - 拿不到就当作「有动画」，UI 不该因此坏掉
            return True


# ============================================================== 目录 / 插件 / 作业

class Folders(QObject):
    """在文件管理器里打开目录。嵌入模式下打开主程序的真实目录。"""

    def __init__(
        self,
        parent: QObject | None = None,
        config_dir: Any = None,
        plugins_dir: Any = None,
        data_dir: Any = None,
    ) -> None:
        super().__init__(parent)
        self._config_dir = config_dir
        self._plugins_dir = plugins_dir
        self._data_dir = data_dir

    @Slot(str)
    def open(self, target: str) -> None:
        import os  # noqa: PLC0415

        mapping = {
            "config": self._config_dir if self._config_dir is not None else paths.CONFIG_DIR,
            "plugins": self._plugins_dir if self._plugins_dir is not None else paths.PLUGINS_DIR,
            "data": self._data_dir if self._data_dir is not None else paths.DATA_ROOT,
        }
        target_path = mapping.get(target)
        if target_path is None:
            return
        try:
            from pathlib import Path  # noqa: PLC0415

            Path(target_path).mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001 - 目录建不出来也试着打开一下
            pass
        if sys.platform == "win32":
            os.startfile(str(target_path))  # noqa: S606
        else:
            from PySide6.QtGui import QDesktopServices  # noqa: PLC0415

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_path)))


class Plugins(QObject):
    """列出已安装插件。

    嵌入模式下从 PluginManager 拿加载结果（ok / failure 来自真实加载状态，
    enabled 来自 disabled_plugins），形状与 web_settings._plugins 对齐。
    """

    def __init__(self, parent: QObject | None = None, plugin_manager: Any = None,
                 settings: Any = None) -> None:
        super().__init__(parent)
        self._pm = plugin_manager
        self._settings = settings

    @Slot(result="QVariantList")
    def list(self) -> list[dict[str, Any]]:  # noqa: A003 - 与 QML 侧 API 对齐
        if self._pm is not None:
            return self._list_managed()
        return self._list_demo()

    def _list_managed(self) -> list[dict[str, Any]]:
        import json  # noqa: PLC0415

        root = self._pm.plugins_dir
        disabled = set((self._settings.get("disabled_plugins") or []) if self._settings else [])
        loaded: dict[str, tuple[bool, str]] = {}
        for item in getattr(self._pm, "loaded", []) or []:
            try:
                name, ok, message = item
            except (TypeError, ValueError):
                continue
            loaded[name] = (bool(ok), str(message or ""))

        result: list[dict[str, Any]] = []
        # 内置功能（原插件、现已编进主程序）排在最前面，带 builtin=True
        try:
            result.extend(self._pm.builtin_list() or [])
        except Exception:  # noqa: BLE001 - 老版本没有这个方法就当没有内置功能
            pass
        root_path = paths.Path(root)
        if not root_path.is_dir():
            return []
        for folder in sorted(root_path.iterdir()):
            if not folder.is_dir() or folder.name == "packages":
                continue
            meta = None
            manifest = folder / "plugin.json"
            if manifest.is_file():
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8-sig"))
                    meta = data if isinstance(data, dict) else None
                except Exception:  # noqa: BLE001
                    meta = None
            ok, message = loaded.get(folder.name, (False, ""))
            if not ok and not message:
                message = "未加载（可能缺少 plugin.json 或入口文件）"
            result.append({
                "id": folder.name,
                # 优先 display_name（中文名），没有才退回 name —— 和 _list_demo 一致，
                # 否则插件管理页会显示成 "disaster-alert" 这种目录名。
                "name": str((meta.get("display_name") if meta else None)
                            or (meta.get("name") if meta else None)
                            or folder.name),
                "version": str(meta.get("version") or "") if meta else "",
                "author": str((meta.get("author_name") or meta.get("author") or "")) if meta else "",
                "desc": str(meta.get("description") or "") if meta else "",
                "ok": bool(ok),
                "enabled": folder.name not in disabled,
                "loaded": bool(ok),
                "failure": "" if ok else message,
            })
        return result

    def _list_demo(self) -> list[dict[str, Any]]:
        if not paths.PLUGINS_DIR.is_dir():
            return []
        result: list[dict[str, Any]] = []
        for folder in sorted(paths.PLUGINS_DIR.iterdir()):
            if not folder.is_dir():
                continue
            # packages 是第三方依赖的落盘目录，不是插件本体
            # （_list_managed 里也跳过它，两边必须一致）
            if folder.name == "packages":
                continue
            meta = read_json(folder / "plugin.json", None)
            if not isinstance(meta, dict):
                result.append({
                    "id": folder.name,
                    "name": folder.name,
                    "version": "",
                    "author": "",
                    "desc": "缺少 plugin.json 或入口文件",
                    "ok": False,
                })
                continue
            result.append({
                "id": str(meta.get("id") or folder.name),
                "name": str(meta.get("display_name") or meta.get("name") or folder.name),
                "version": str(meta.get("version") or ""),
                "author": str(meta.get("author_name") or meta.get("author") or ""),
                "desc": str(meta.get("description") or ""),
                "ok": True,
            })
        return result


class Homework(QObject):
    """作业条目：演示模式 JSON 持久化；嵌入模式委托 HomeworkManager。

    形状对齐原生 `menu.HomeworkEditor`：一条作业 = 科目 + 提交日期 + 内容，
    列表按科目分组，支持 添加 / 修改 / 删除 / 整组清除。
    """

    itemsChanged = Signal()

    def __init__(self, parent: QObject | None = None, homework: Any = None,
                 on_changed: Any = None) -> None:
        super().__init__(parent)
        self._homework = homework
        self._on_changed = on_changed      # 宿主回调：("homework") → 主窗口重排
        if homework is None:
            raw = read_json(paths.HOMEWORK_FILE, [])
            self._items: list[dict[str, Any]] = raw if isinstance(raw, list) else []

    @Slot(result="QVariantList")
    def items(self) -> list[dict[str, Any]]:
        if self._homework is not None:
            return list(self._homework.get_all_homework())
        return self._items

    @Slot(str, str, str, result=bool)
    def add(self, subject: str, content: str, date: str) -> bool:
        subject = subject.strip() or "未分类"
        content = content.strip()
        if not content:
            return False
        if self._homework is not None:
            # 演示模式把空科目归一成「未分类」；这里同样处理，页面体验一致
            ok = bool(self._homework.add_homework(subject, content, date.strip()))
            if ok:
                self._after_change()
            return ok
        self._items.append({"subject": subject, "content": content, "date": date.strip()})
        self._commit()
        return True

    @Slot(int, str, str, str, result=bool)
    def update(self, index: int, subject: str, content: str, date: str) -> bool:
        """修改一条（原生「修改作业」按钮）。"""
        subject = subject.strip() or "未分类"
        content = content.strip()
        if not content:
            return False
        if self._homework is not None:
            ok = bool(self._homework.update_homework(index, subject, content,
                                                     date.strip()))
            if ok:
                self._after_change()
            return ok
        if not (0 <= index < len(self._items)):
            return False
        self._items[index] = {"subject": subject, "content": content,
                              "date": date.strip()}
        self._commit()
        return True

    @Slot(int, result=bool)
    def remove(self, index: int) -> bool:
        if self._homework is not None:
            ok = bool(self._homework.remove_homework(index))
            if ok:
                self._after_change()
            return ok
        if not (0 <= index < len(self._items)):
            return False
        self._items.pop(index)
        self._commit()
        return True

    @Slot(str, result=int)
    def clearSubject(self, subject: str) -> int:
        name = subject.strip() or "未分类"
        if self._homework is not None:
            targets = [i for i, it in enumerate(self._homework.get_all_homework())
                       if (str(it.get("subject") or "").strip() or "未分类") == name]
            # 倒序删，避免删除过程中索引前移（与 web_settings 的做法一致）
            for index in sorted(targets, reverse=True):
                self._homework.remove_homework(index)
            if targets:
                self._after_change()
            return len(targets)
        before = len(self._items)
        self._items = [i for i in self._items if (i.get("subject") or "未分类") != name]
        removed = before - len(self._items)
        if removed:
            self._commit()
        return removed

    def _after_change(self) -> None:
        """嵌入模式：管理器自己已经存过盘，这里只负责让主界面跟上。

        原生 HomeworkEditor 每次增删改都调 `self.app.update_display()`；
        少了这一步，设置里加完作业，主窗口还写着「暂无作业」。
        """
        self.itemsChanged.emit()
        if self._on_changed is not None:
            try:
                self._on_changed("homework")
            except Exception:  # noqa: BLE001 - 宿主刷新失败不该让保存报错
                pass

    def _commit(self) -> None:
        write_json_atomic(paths.HOMEWORK_FILE, self._items)
        self.itemsChanged.emit()


class ListStore(QObject):
    """通用列表存储：值日生名单 / 假期 / 调休共用一套。

    演示模式直接读写 JSON；嵌入模式分别委托：
      duty     → StudentOnDuty（settings/name.json，字符串名单）
      holidays → ScheduleManager.list_holidays / add_holiday / remove_holiday
      makeup   → ScheduleManager.list_makeups / add_makeup / remove_makeup
    条目形状与 web_settings 的返回值一致：假期 {start,end,name}、
    调休 {date,asWeekday}（snake_case 的 as_weekday 出境前转驼峰）。
    """

    changed = Signal(str)

    FILES = {
        "duty": paths.NAME_FILE,
        "holidays": paths.CONFIG_DIR / "holidays.json",
        "makeup": paths.CONFIG_DIR / "makeup.json",
    }

    def __init__(self, parent: QObject | None = None, duty: Any = None,
                 schedule: Any = None) -> None:
        super().__init__(parent)
        self._duty = duty
        self._schedule = schedule
        self._cache: dict[str, list[Any]] = {}

    def _load(self, name: str) -> list[Any]:
        if name == "duty" and self._duty is not None:
            return [str(n) for n in getattr(self._duty, "duty_list", [])]
        if name in ("holidays", "makeup") and self._schedule is not None:
            if name == "holidays":
                return [{
                    "start": str(h.get("start", "")),
                    "end": str(h.get("end", "")),
                    "name": str(h.get("name", "")),
                } for h in self._schedule.list_holidays()]
            return [{
                "date": str(m.get("date", "")),
                "asWeekday": int(m.get("as_weekday", 0)),
            } for m in self._schedule.list_makeups()]
        if name not in self._cache:
            raw = read_json(self.FILES[name], [])
            self._cache[name] = raw if isinstance(raw, list) else []
        return self._cache[name]

    def _save(self, name: str) -> None:
        if self._duty is None and self._schedule is None:
            write_json_atomic(self.FILES[name], self._cache[name])
        self.changed.emit(name)

    @Slot(str, result="QVariantList")
    def items(self, name: str) -> list[Any]:
        return self._load(name) if name in self.FILES else []

    @Slot(str, "QVariant", result=bool)
    def add(self, name: str, item: Any) -> bool:
        # QML 传的是 JS 字符串 / JS 对象 → 收到 QJSValue，先转成Python 原生结构，
        # 否则下面 isinstance(item, dict) 一律不成立（详见 qmlcompat.py）。
        item = _py(item)
        if name == "duty" and self._duty is not None:
            text = str(item).strip()
            if not text:
                return False
            self._duty.add_duty(text)
            self.changed.emit(name)
            return True
        if name == "holidays" and self._schedule is not None:
            if not isinstance(item, dict):
                return False
            start = str(item.get("start", "")).strip()
            end = str(item.get("end", "")).strip()
            if not start or not end:
                return False
            self._schedule.add_holiday(start, end, str(item.get("name") or ""))
            self.changed.emit(name)
            return True
        if name == "makeup" and self._schedule is not None:
            if not isinstance(item, dict):
                return False
            date = str(item.get("date", "")).strip()
            if not date:
                return False
            try:
                weekday = max(0, min(6, int(item.get("asWeekday", 0))))
            except (TypeError, ValueError):
                weekday = 0
            self._schedule.add_makeup(date, weekday)
            self.changed.emit(name)
            return True
        if name not in self.FILES:
            return False
        data = self._load(name)
        if isinstance(item, str):
            text = item.strip()
            if not text:
                return False
            data.append(text)
        elif isinstance(item, dict):
            data.append(dict(item))
        else:
            return False
        self._save(name)
        return True

    @Slot(str, int, result=bool)
    def remove(self, name: str, index: int) -> bool:
        if name == "duty" and self._duty is not None:
            duty_list = getattr(self._duty, "duty_list", [])
            if not (0 <= index < len(duty_list)):
                return False
            self._duty.remove_duty(index)
            self.changed.emit(name)
            return True
        if name == "holidays" and self._schedule is not None:
            return bool(self._schedule.remove_holiday(index))
        if name == "makeup" and self._schedule is not None:
            return bool(self._schedule.remove_makeup(index))
        if name not in self.FILES:
            return False
        data = self._load(name)
        if not (0 <= index < len(data)):
            return False
        if self._duty is None and self._schedule is None:
            data.pop(index)
        self._save(name)
        return True

    @Slot(str, result=int)
    def count(self, name: str) -> int:
        return len(self._load(name)) if name in self.FILES else 0


class ScheduleInfo(QObject):
    """课表**只读预览**。

    演示模式直接读 data/settings/schedule.json；嵌入模式委托 ScheduleManager
    （active_name / periods 是它的 property，这里包成 Slot）。
    真正的课表编辑器（新建 / 复制 / 导入导出 / 临时调课）还没搬过来，
    这一页先把「当前用了哪套课表、有哪些节次」如实显示出来 ——
    宁可明说没做，也不要看起来像做完了。
    """

    SCHEDULE_FILE = paths.CONFIG_DIR / "schedule.json"
    DEFAULT_PERIODS = [
        ("第1节", "08:00", "08:45"),
        ("第2节", "08:55", "09:40"),
        ("第3节", "10:00", "10:45"),
        ("第4节", "10:55", "11:40"),
        ("第5节", "14:00", "14:45"),
        ("第6节", "14:55", "15:40"),
        ("第7节", "16:00", "16:45"),
        ("第8节", "16:55", "17:40"),
    ]

    def __init__(self, parent: QObject | None = None, schedule: Any = None) -> None:
        super().__init__(parent)
        self._schedule = schedule

    def _doc(self) -> dict[str, Any]:
        raw = read_json(self.SCHEDULE_FILE, {})
        return raw if isinstance(raw, dict) else {}

    @Slot(result="QVariantList")
    def periods(self) -> list[dict[str, str]]:
        if self._schedule is not None:
            return [
                {
                    "name": str(p.get("name") or f"第{i + 1}节"),
                    "start": str(p.get("start") or ""),
                    "end": str(p.get("end") or ""),
                }
                for i, p in enumerate(self._schedule.periods)
                if isinstance(p, dict)
            ]
        doc = self._doc()
        timetables = doc.get("timetables")
        if isinstance(timetables, dict) and timetables:
            active = doc.get("active") or next(iter(timetables))
            table = timetables.get(active) or {}
            periods = table.get("periods") if isinstance(table, dict) else None
            if isinstance(periods, list) and periods:
                return [
                    {
                        "name": str(p.get("name") or f"第{i + 1}节"),
                        "start": str(p.get("start") or ""),
                        "end": str(p.get("end") or ""),
                    }
                    for i, p in enumerate(periods)
                    if isinstance(p, dict)
                ]
        return [{"name": n, "start": s, "end": e} for n, s, e in self.DEFAULT_PERIODS]

    @Slot(result=str)
    def activeName(self) -> str:
        if self._schedule is not None:
            return str(self._schedule.active_name)
        doc = self._doc()
        timetables = doc.get("timetables")
        if isinstance(timetables, dict) and timetables:
            return str(doc.get("active") or next(iter(timetables)))
        return "默认课表（内置示例）"

    @Slot(result=bool)
    def isFromFile(self) -> bool:
        if self._schedule is not None:
            import os  # noqa: PLC0415

            return os.path.exists(str(self._schedule.path))
        return self.SCHEDULE_FILE.exists()
