"""自检：不需要人眼看界面就能查出来的那几类问题。

    python tools/selftest.py

四组检查：
  [1] Python 侧 —— schema 默认值类型自洽 / Config 往返 / 越界夹取 / 未知键保留 / 原子写
  [2] QML 静态 —— 图标名是否在 RinUI 的 Fluent 图标索引里、settingKey 是否都在 schema 里、
                 page: 指向的文件是否存在、每个页面是否都被 Settings.qml 引用
  [3] QML 编译 —— 用 QQmlComponent 逐个编译页面，抓语法错与「属性不存在」这类硬错
  [4] 撞名       —— 上下文属性名不能和 QML 组件（文件名）同名

[2] 的图标检查很值：RinUI 的 Icon 是 `String.fromCharCode(Utils.fontIconIndex[name])`，
名字写错不会报错，只会**静默渲染成一个空/乱码字符** —— 只有静态比对索引才抓得到。
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QML_DIR = ROOT / "qml"
SETTINGS_QML = QML_DIR / "Settings.qml"

failures: list[str] = []


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def bad(msg: str) -> None:
    print(f"  ✗ {msg}")
    failures.append(msg)


# ============================================================================
#  [2] / [3] 需要 Qt，[1] 需要 app 包 —— 都要求先把数据根指到临时目录
# ============================================================================

_TMP = tempfile.TemporaryDirectory(prefix="cdl-selftest-")
os.environ["CDL_DATA_ROOT"] = _TMP.name
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", str(os.environ.get("WINDIR", r"C:\Windows")) + r"\Fonts")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

sys.path.insert(0, str(ROOT))

from app import schema                       # noqa: E402
from app.bridge import Config                # noqa: E402


# ============================================================================
#  [1] Python 侧
# ============================================================================

def check_python() -> None:
    print("[1] Python 侧：schema 与 Config")

    problems = schema.missing_defaults()
    if problems:
        bad("schema 默认值与 kind 不自洽：" + "; ".join(problems))
    else:
        ok(f"{len(schema.FIELDS)} 个设置项的默认值都自洽")

    cfg = Config()

    # 全默认值都在
    _sentinel = object()
    missing = [f.key for f in schema.FIELDS if cfg.get(f.key, _sentinel) is _sentinel]
    if missing:
        bad("读不到这些键：" + ", ".join(missing))
    else:
        ok("每个键都能读到值")

    # 往返
    cfg.set("main_font_size", 18)
    if cfg.get("main_font_size") != 18:
        bad("写入后读不到 main_font_size=18")
    else:
        ok("写入 → 读回一致")

    # 越界夹取（源项目在这里吃过亏：越界值静默生效，两处显示差了 4 小时 24 分）
    cfg.set("schedule_time_offset_seconds", 999999)
    if cfg.get("schedule_time_offset_seconds") != 1800:
        bad(f"越界值没夹取到 1800，实际 {cfg.get('schedule_time_offset_seconds')}")
    else:
        ok("越界整数夹取到上界（1800）")

    cfg.set("schedule_time_offset_seconds", -999999)
    if cfg.get("schedule_time_offset_seconds") != -1800:
        bad("越界值没夹取到下界")
    else:
        ok("越界整数夹取到下界（-1800）")

    # 类型不符 → 回落，不让一个坏值带崩整份配置
    cfg.set("main_font_size", "这不是数字")
    if cfg.get("main_font_size") != schema.BY_KEY["main_font_size"].default:
        bad(f"类型不符应回落默认值，实际 {cfg.get('main_font_size')}")
    else:
        ok("类型不符回落默认值")

    # 未知键忽略
    if cfg.set("no_such_key", 1) is not False:
        bad("未知键应当被拒绝")
    else:
        ok("未知键被拒绝（不会写进配置）")

    # 值没变就不落盘
    cfg.set("anim_duration", 320)
    if cfg.set("anim_duration", 320) is not False:
        bad("值没变时不该重复落盘")
    else:
        ok("值没变不落盘")

    # 磁碟上的未知键要保留（跟 .NET / 旧 Python 版互读时不能悄悄吃掉对方的字段）
    cfg.set("main_font_size", 16)
    cfg._unknown["some_other_app_key"] = "keep-me"  # noqa: SLF001 - 自检刻意探内部
    cfg._save()                                     # noqa: SLF001
    cfg2 = Config()
    if cfg2._unknown.get("some_other_app_key") != "keep-me":  # noqa: SLF001
        bad("未知键没被保留，写回时会丢掉别的应用写的字段")
    else:
        ok("磁盘上的未知键原样保留")

    # meta() 给 QML 用的范围
    meta = cfg.meta("main_font_size")
    if meta.get("low") != 8 or meta.get("high") != 30:
        bad(f"meta() 范围不对：{meta}")
    else:
        ok("meta() 返回正确的取值范围")


# ============================================================================
#  [1b] 嵌入模式：桥对象穿透到真实管理器
# ============================================================================

class _FakeSettings:
    """模仿 settings_manager.SettingsManager 的最小面。"""

    def __init__(self, data: dict) -> None:
        self.data = data
        self.path = os.path.join(_TMP.name, "settings.json")
        self.saved = 0

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        self.saved += 1


class _FakeSchedule:
    def __init__(self) -> None:
        self.data = {"advance_minutes": 2, "time_offset_seconds": 0,
                     "holidays": [], "makeup_days": []}
        self.path = os.path.join(_TMP.name, "schedule.json")

    def save(self):
        pass

    def list_holidays(self):
        return self.data["holidays"]

    def add_holiday(self, start, end, name=""):
        self.data["holidays"].append({"start": start, "end": end, "name": name})
        return True

    def remove_holiday(self, index):
        if 0 <= index < len(self.data["holidays"]):
            self.data["holidays"].pop(index)
            return True
        return False

    def list_makeups(self):
        return self.data["makeup_days"]

    def add_makeup(self, date, as_weekday):
        self.data["makeup_days"].append({"date": date, "as_weekday": as_weekday})
        return True

    def remove_makeup(self, index):
        if 0 <= index < len(self.data["makeup_days"]):
            self.data["makeup_days"].pop(index)
            return True
        return False


class _FakeDuty:
    def __init__(self) -> None:
        self.duty_list = ["张三", "李四"]

    def add_duty(self, name):
        self.duty_list.append(name)


class _FakeHomework:
    def __init__(self) -> None:
        self.homework_list = [{"subject": "数学", "content": "习题1", "date": ""}]

    def get_all_homework(self):
        return self.homework_list[:]

    def add_homework(self, subject, content, date=None):
        if not (subject.strip() and content.strip()):
            return False
        self.homework_list.append({"subject": subject, "content": content, "date": date})
        return True

    def remove_homework(self, index):
        if 0 <= index < len(self.homework_list):
            self.homework_list.pop(index)
            return True
        return False


def check_embedded() -> None:
    print("[1b] 嵌入模式：Config / ListStore / Homework 穿透到真实管理器")

    from app.bridge import Config, Homework, ListStore

    settings = _FakeSettings({
        "theme_mode": "system", "main_font_size": 14,
        "disabled_plugins": [], "market_source": "official",
    })
    schedule = _FakeSchedule()

    cfg = Config(settings=settings, schedule=schedule)

    # 读：data 属性合并 manager + 课表服务
    data = cfg.data
    if data.get("theme_mode") != "system" or data.get("schedule_advance_minutes") != 2:
        bad(f"data 合并不对：theme_mode={data.get('theme_mode')} "
            f"advance={data.get('schedule_advance_minutes')}")
    else:
        ok("data 属性合并 SettingsManager 与课表服务的键")

    # 写：普通键落到 manager
    cfg.set("main_font_size", 20)
    if settings.data.get("main_font_size") != 20:
        bad(f"嵌入模式写普通键没落到 manager：{settings.data.get('main_font_size')}")
    else:
        ok("普通键写回 SettingsManager")

    # 写：课表键走课表服务，且夹取保留（±1800）
    cfg.set("schedule_time_offset_seconds", 999999)
    if schedule.data.get("time_offset_seconds") != 1800:
        bad(f"课表键没夹取到 1800：{schedule.data.get('time_offset_seconds')}")
    else:
        ok("课表键穿透到 ScheduleManager 并夹取（±1800）")

    # 写：QML 演示专属键在嵌入模式下被拒绝
    if cfg.set("plugins_auto_check_update", True) is not False:
        bad("演示专属键不该被写进共用配置")
    else:
        ok("演示专属键被拒绝（不污染 settings.json）")
    if cfg.isManaged("plugins_auto_check_update"):
        bad("isManaged 对演示专属键应为 False")
    else:
        ok("isManaged 如实标注演示专属键")

    # 值没变不落盘
    before = settings.saved
    cfg.set("main_font_size", 20)
    if settings.saved != before:
        bad("值没变时嵌入模式重复落盘")
    else:
        ok("值没变不落盘")

    # ListStore：值日生 / 假期穿透
    store = ListStore(duty=_FakeDuty(), schedule=schedule)
    store.add("duty", " 王五 ")
    store.add("holidays", {"start": "2026-10-01", "end": "2026-10-07", "name": "国庆"})
    store.add("holidays", {"start": "", "end": "2026-10-07"})
    duty_names = store.items("duty")
    holidays = store.items("holidays")
    if duty_names != ["张三", "李四", "王五"]:
        bad(f"值日生穿透不对：{duty_names}")
    elif len(holidays) != 1 or holidays[0].get("name") != "国庆":
        bad(f"假期穿透不对（空日期该被拒）：{holidays}")
    else:
        ok("ListStore 值日生 / 假期穿透到真实管理器（含空值拒绝）")

    # Homework：穿透 + 空科目归一化
    hw = Homework(homework=_FakeHomework())
    hw.add("", "英语卷子一张", "")
    items = hw.items()
    if len(items) != 2 or items[1].get("subject") != "未分类":
        bad(f"作业穿透 / 归一化不对：{items}")
    else:
        ok("Homework 穿透到 HomeworkManager（空科目归一为未分类）")


# ============================================================================
#  [1c] bootstrap + 完整版新桥（找到 ClassDailyLand-Py 才跑，否则跳过）
# ============================================================================

def check_full_stack() -> None:
    print("[1c] bootstrap + 课表编辑 / 状态测试 / 市场 / 依赖包 / 更新")

    from app.bootstrap import bootstrap_services

    services = bootstrap_services()
    if services is None:
        print("  - 没找到 ClassDailyLand-Py，跳过完整版检查（页面会如实显示不可用）")
        return

    from app.extra import (MarketStore, PackageBridge, StatusTester,
                           TimetableStore, UpdaterBridge)

    schedule_mod = sys.modules.get("schedule")
    problems: list[str] = []

    # ---- 课表编辑：新建 → 改 → 导出 → 导入 → 删，全部落临时数据目录 ----
    store = TimetableStore(schedule=services.schedule)
    if not store.isAvailable():
        problems.append("TimetableStore 应可用")
    else:
        made = store.create("自检课表", services.schedule.active_name)
        if not made.get("ok"):
            problems.append(f"新建课表失败：{made}")
        else:
            detail = store.detail("自检课表")
            periods = detail.get("periods") or []
            periods.append({"name": "第9节", "start": "19:00", "end": "19:40"})
            saved = store.update("自检课表", periods, detail.get("timetable") or {})
            if not saved.get("ok"):
                problems.append(f"update 失败：{saved}")
            elif len((store.detail("自检课表").get("periods") or [])) != len(periods):
                problems.append("update 后节次数不对")
            else:
                ok("课表 新建 → 编辑 → 保存 落盘一致")
            # 越界时间该被 normalize 拦下（与主程序同一套校验）
            bad_periods = periods + [{"name": "坏节", "start": "25:00", "end": "26:00"}]
            rejected = store.update("自检课表", bad_periods,
                                    detail.get("timetable") or {})
            if rejected.get("ok"):
                problems.append("非法时间（25:00）没被 normalize_timetable 拦下")
            else:
                ok("非法节次被主程序同源校验拒绝")
            # 导出 + 导入往返
            import tempfile as _tf
            with _tf.TemporaryDirectory() as _td:
                exported = store.export("自检课表", "json", _td)
                if not exported.get("ok"):
                    problems.append(f"导出失败：{exported}")
                else:
                    preview = store.previewFile(exported["path"])
                    if not preview.get("timetables"):
                        problems.append(f"导出的文件解析不出课表：{preview}")
                    else:
                        ok("导出的 JSON 用主程序解析器读回成功")
            if not store.switch(services.schedule.active_name):
                problems.append("切回原课表失败")
        gone = store.delete("自检课表")
        if not gone.get("ok"):
            problems.append(f"删除测试课表失败：{gone}")

    # ---- 状态测试：compute 形状 ----
    tester = StatusTester(schedule=services.schedule, settings=services.settings)
    st = tester.compute("2026-10-12T08:30:00", 0, 2, 60)
    if "state" not in st or "text" not in st or not isinstance(st.get("detail"), list):
        problems.append(f"compute 返回形状不对：{st}")
    else:
        ok(f"状态试算正常（{st['state']}：{st['text']}）")

    # ---- 市场 / 依赖包：可用性来自真实模块 ----
    market = MarketStore(settings=services.settings, plugin_manager=services.plugin_manager)
    pkgs = PackageBridge(settings=services.settings, plugin_manager=services.plugin_manager)
    if not market.isAvailable():
        problems.append("MarketStore 应可用（bootstrap 找到了主程序）")
    else:
        status = market.status()
        if not status.get("available"):
            problems.append(f"market.status 不可用：{status}")
        else:
            ok(f"插件市场 status 正常（{status['count']} 个条目，来源 {status['source']}）")
    if not pkgs.isAvailable():
        problems.append("PackageBridge 应可用")
    else:
        ps = pkgs.status()
        if not ps.get("available") or not isinstance(ps.get("entries"), list):
            problems.append(f"packages.status 形状不对：{ps}")
        else:
            ok(f"依赖包 status 正常（{len(ps['entries'])} 个条目，源 {ps['source']}）")

    # ---- 更新：state 至少能报 launcher 是否存在 ----
    up = UpdaterBridge().state()
    if not up.get("available"):
        problems.append(f"Updater 不可用：{up}")
    else:
        ok(f"更新链路 state 正常（launcher={'有' if up.get('launcherFound') else '无'}，"
           f"源码命中 {len(up.get('sourceHits') or [])} 个）")

    for problem in problems:
        bad(problem)
    if not problems:
        ok("完整版五个桥全部工作")


# ============================================================================
#  [2] QML 静态检查
# ============================================================================

def qml_files() -> list[Path]:
    return sorted(QML_DIR.rglob("*.qml"))


def icon_index() -> set[str]:
    import RinUI  # noqa: PLC0415

    index_file = Path(RinUI.__file__).parent / "assets" / "fonts" / "FluentSystemIcons-Index.js"
    text = index_file.read_text(encoding="utf-8")
    return set(re.findall(r'"(ic_fluent_[a-z0-9_]+)"', text))


def check_qml_static() -> None:
    print("[2] QML 静态：图标名 / settingKey / page 路径")

    files = qml_files()
    ok(f"找到 {len(files)} 个 QML 文件")

    known_icons = icon_index()

    # ---- 图标名 ----
    used_icons: dict[str, list[str]] = {}
    for path in files:
        for name in re.findall(r"ic_fluent_[a-z0-9_]+", path.read_text(encoding="utf-8")):
            used_icons.setdefault(name, []).append(path.name)
    unknown = {n: f for n, f in used_icons.items() if n not in known_icons}
    if unknown:
        for name, where in sorted(unknown.items()):
            bad(f"图标名不在 RinUI 索引里：{name}（{', '.join(sorted(set(where)))}）")
    else:
        ok(f"用到的 {len(used_icons)} 个图标名都在索引里（共 {len(known_icons)} 个）")

    # ---- settingKey ----
    used_keys: dict[str, list[str]] = {}
    for path in files:
        for key in re.findall(r'settingKey:\s*"([a-z0-9_]+)"', path.read_text(encoding="utf-8")):
            used_keys.setdefault(key, []).append(path.name)
        # 页面里直接写 Config.set("x", ...) / Config.get("x", ...) 的也要查
        for key in re.findall(r'Config\.(?:set|get)\(\s*"([a-z0-9_]+)"', path.read_text(encoding="utf-8")):
            used_keys.setdefault(key, []).append(path.name)
    missing_keys = {k: v for k, v in used_keys.items() if k not in schema.BY_KEY}
    if missing_keys:
        for key, where in sorted(missing_keys.items()):
            bad(f"settingKey 不在 schema 里：{key}（{', '.join(sorted(set(where)))}）")
    else:
        ok(f"用到的 {len(used_keys)} 个 settingKey 都在 schema 里")

    # ---- page: 路径存在 ----
    pages_used: set[str] = set()
    for path in files:
        for target in re.findall(r'page:\s*Paths\.qml\("([^"]+)"\)', path.read_text(encoding="utf-8")):
            pages_used.add(target)
            if not (QML_DIR / target).exists():
                bad(f"{path.name} 引用了不存在的页面：{target}")
    if pages_used and not any("不存在" in f for f in failures):
        ok(f"引用的 {len(pages_used)} 个页面文件都存在")

    # ---- 每个页面都被引用（避免留下死文件）----
    unreferenced = [
        p.name for p in (QML_DIR / "pages").glob("*.qml")
        if f"pages/{p.name}" not in pages_used
    ]
    if unreferenced:
        bad("这些页面没有被 Settings.qml 引用：" + ", ".join(sorted(unreferenced)))
    else:
        ok("pages/ 下每个页面都被导航引用")


# ============================================================================
#  [3] QML 编译
# ============================================================================

def check_qml_compile() -> None:
    print("[3] QML 编译：逐个页面过一遍 QQmlComponent")

    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtWidgets import QApplication
    import RinUI
    from RinUI.core.config import RINUI_PATH

    app = QApplication.instance() or QApplication([])  # noqa: F841

    engine = QQmlEngine()
    engine.addImportPath(str(RINUI_PATH))

    broken = 0
    for path in qml_files():
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
        if component.isError():
            broken += 1
            for err in component.errors():
                bad(f"{path.relative_to(ROOT)}: {err.toString()}")
    if broken == 0:
        ok(f"{len(qml_files())} 个 QML 文件全部编译通过")


# ============================================================================

def check_name_collisions() -> None:
    """上下文属性名 ↔ QML 组件名不能撞。

    撞了的表现极具迷惑性：QML 解析标识符时本地类型优先，于是页面里的
    `Homework.items()` 变成「组件自己」，拿到 undefined，列表永远空的、**零报错**。
    （Homework / Plugins / Schedule 三个页面都这么中过招。）
    """
    print("[4] 上下文属性名 ↔ QML 组件名")

    from app.window import CONTEXT_PROPERTIES

    component_names = {p.stem for p in qml_files()}
    clashes = [name for name, _ in CONTEXT_PROPERTIES if name in component_names]
    if clashes:
        for name in clashes:
            bad(f"上下文属性 {name} 与同名 QML 组件冲突（页面里会解析成组件而不是这个对象）")
    else:
        ok(f"{len(CONTEXT_PROPERTIES)} 个上下文属性名都不与任何 QML 组件撞名")

    # 顺带确认页面里引用的桥对象名都真的注册了
    known = {name for name, _ in CONTEXT_PROPERTIES}
    for path in qml_files():
        text = path.read_text(encoding="utf-8")
        for used in re.findall(r"([A-Z][A-Za-z]+)\.(?:items|list|periods|activeName|isFromFile|add|remove|clearSubject|open|get|set|meta)\(", text):
            if used not in known and used not in {"Math", "Number", "String", "Object", "JSON"}:
                bad(f"{path.name} 用了未注册的桥对象：{used}")


def main() -> int:
    print(f"项目根：{ROOT}")
    print(f"数据根：{os.environ['CDL_DATA_ROOT']}（临时目录）\n")
    check_python()
    print()
    check_embedded()
    print()
    check_full_stack()
    print()
    check_qml_static()
    print()
    check_qml_compile()
    print()
    check_name_collisions()
    print()
    if failures:
        print(f"自检失败 {len(failures)} 项")
        return 1
    print("自检通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
