"""web_settings 的 RPC 桥自检（无需界面、无需联网）。

用途：改了 ``web_settings.py`` 或 ``ui/`` 之后，先跑一遍确认桥没坏：

    python web_settings_selftest.py

它用一个假的 dialog 上下文（临时目录里的 settings.json + 一个假插件目录）
把 ``settings.*`` / ``plugins.*`` / ``packages.status`` / 错误路径 / 
「先回包后弹窗」的顺序逐条走一遍。退出码非 0 表示有失败项。

.NET 侧的对应实现（``WebUiBridge.cs``）返回值形状必须与本模块一致，
所以这里是两边契约的可执行说明。
"""

import json
import os
import sys
import tempfile

from PySide6.QtCore import QCoreApplication, QObject

import web_settings
from settings_manager import DEFAULTS, SettingsManager

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    suffix = ("  ← " + str(detail)) if (detail != "" and not ok) else ""
    print(("  OK  " if ok else "  FAIL") + " " + name + suffix)


class FakeSchedule:
    """课表服务的最小替身：设置项 + 假期 / 调休 / 周末。"""

    def __init__(self):
        self.data = {
            "advance_minutes": 2,
            "time_offset_seconds": 0,
            "holidays": [{"start": "2026-10-01", "end": "2026-10-07", "name": "国庆"}],
            "makeup_days": [{"date": "2026-10-11", "as_weekday": 4}],
            "weekend": {
                "morning_split": "12:00",
                "afternoon_periods": [{"name": "午1", "start": "13:30", "end": "14:15"}],
                "courses": ["自习"],
            },
        }
        self.saves = 0

    def save(self):
        self.saves += 1

    # ---------- 假期 / 调休 ----------
    def list_holidays(self):
        return list(self.data.get("holidays", []))

    def add_holiday(self, start, end, name=""):
        self.data.setdefault("holidays", []).append(
            {"start": start, "end": end or start, "name": name})
        self.save()

    def remove_holiday(self, index):
        items = self.data.get("holidays", [])
        if 0 <= index < len(items):
            del items[index]
            self.save()
            return True
        return False

    def list_makeups(self):
        return list(self.data.get("makeup_days", []))

    def add_makeup(self, date, as_weekday):
        self.data.setdefault("makeup_days", []).append(
            {"date": date, "as_weekday": max(0, min(6, int(as_weekday)))})
        self.save()

    def remove_makeup(self, index):
        items = self.data.get("makeup_days", [])
        if 0 <= index < len(items):
            del items[index]
            self.save()
            return True
        return False

    # ---------- 周末作息 ----------
    def get_weekend(self):
        return dict(self.data.get("weekend", {}))

    def set_weekend(self, morning_split, afternoon_periods, courses):
        self.data["weekend"] = {
            "morning_split": morning_split or "12:00",
            "afternoon_periods": list(afternoon_periods),
            "courses": list(courses),
        }
        self.save()


class FakeDuty:
    def __init__(self):
        self.duty_list = ["张三", "李四"]
        self.current_index = 0

    def get_current_duty(self):
        return self.duty_list[self.current_index] if self.duty_list else "（暂无值日生）"

    def add_duty(self, name):
        self.duty_list.append(name)

    def add_duties(self, names):
        for name in names:
            if name.strip():
                self.duty_list.append(name.strip())

    def remove_duty(self, index):
        if 0 <= index < len(self.duty_list):
            del self.duty_list[index]
            return True
        return False


class FakeHomework:
    def __init__(self):
        self.items = [
            {"subject": "语文", "content": "背诵", "date": "10-12"},
            {"subject": "语文", "content": "作文", "date": ""},
            {"subject": "", "content": "未分类的", "date": ""},
        ]
        self.saves = 0

    def get_all_homework(self):
        return self.items[:]

    def add_homework(self, subject, content, date=None):
        if subject.strip() and content.strip():
            self.items.append({"subject": subject.strip(),
                               "content": content.strip(), "date": date or ""})
            self.saves += 1
            return True
        return False

    def update_homework(self, index, subject, content, date):
        if 0 <= index < len(self.items):
            self.items[index] = {"subject": subject.strip(),
                                 "content": content.strip(), "date": date}
            self.saves += 1
            return True
        return False

    def remove_homework(self, index):
        if 0 <= index < len(self.items):
            del self.items[index]
            self.saves += 1
            return True
        return False

    def save_homework(self):
        self.saves += 1


class FakePlugins:
    def __init__(self, root):
        self.plugins_dir = root
        self.loaded = [("class.demo.clock", True, "")]


class FakeStore:
    """依赖包商店的最小替身。source_id / sources 是市场页要用到的。"""

    def __init__(self, root):
        self.packages_dir = root
        self.catalog = []

    @staticmethod
    def sources():
        return [("官方服务器", "official"), ("GitHub", "github"), ("Gitee", "gitee")]

    def source_id(self):
        return "github"

    def set_source(self, sid):
        return sid in ("official", "github", "gitee")

    def installed(self):
        return {"requests": {"version": "2.32.3", "manual": False}}

    def used_by_map(self):
        return {"requests": ["class.demo.clock"]}


class FakeDialog(QObject):
    """撑起 _Bridge 需要的上下文（真身是 WebSettingsDialog）。"""

    def __init__(self, settings, schedule, plugins_root):
        super().__init__()
        self.settings = settings
        self.schedule_manager = schedule
        self.plugin_manager = FakePlugins(plugins_root)
        self.controller = None
        self.app = None
        # 二级对话框要用（对应 gui.py 里从主窗传进来的两个管理器）
        self.duty_manager = FakeDuty()
        self.homework_manager = FakeHomework()


class Harness:
    def __init__(self):
        self.messages = []

    def attach(self, bridge):
        bridge.reply.connect(self.messages.append)

    def call(self, method, params=None):
        before = len(self.messages)
        self.bridge.invoke(json.dumps(
            {"id": before + 1, "method": method, "params": params or {}}))
        new = self.messages[before:]
        # 宿主推的事件（带 event 字段、没有 id）会混在回包前面，别拿错
        for message in reversed(new):
            parsed = json.loads(message)
            if not parsed.get("event"):
                return parsed
        return None    # None = 异步，等信号

    def events(self, name=None):
        """取出宿主推给页面的事件（单程、带 event 字段）。"""
        result = []
        for message in self.messages:
            parsed = json.loads(message)
            if parsed.get("event") and (name is None or parsed["event"] == name):
                result.append(parsed)
        return result


def main():
    QCoreApplication.instance() or QCoreApplication([])   # QTimer 需要一个事件循环

    tmp = tempfile.mkdtemp(prefix="cdl-selftest-")
    plugins_root = os.path.join(tmp, "plugins")
    demo = os.path.join(plugins_root, "class.demo.clock")
    os.makedirs(demo)
    with open(os.path.join(demo, "plugin.json"), "w", encoding="utf-8") as handle:
        json.dump({"name": "时钟", "version": "1.2.0",
                   "description": "显示时间", "requires": ["requests"]}, handle)

    settings = SettingsManager(tmp)
    schedule = FakeSchedule()

    bridge = web_settings._Bridge(FakeDialog(settings, schedule, plugins_root))
    harness = Harness()
    harness.attach(bridge)
    harness.bridge = bridge

    print("[1] app.getVersion")
    info = harness.call("app.getVersion")["result"]
    check("host = qtwebengine", info["host"] == "qtwebengine", info.get("host"))
    check("system 认得出 Windows 11", "Windows 11" in info["system"], info.get("system"))
    check("给出插件目录", info["pluginsPath"].endswith("plugins"), info.get("pluginsPath"))

    print("[2] settings.getAll")
    data = harness.call("settings.getAll")["result"]
    check("含全部默认键", all(k in data for k in DEFAULTS))
    check("并入 schedule_advance_minutes", data.get("schedule_advance_minutes") == 2,
          data.get("schedule_advance_minutes"))
    check("并入 schedule_time_offset_seconds", data.get("schedule_time_offset_seconds") == 0)

    print("[3] settings.patch")
    harness.call("settings.patch", {"theme_mode": "dark", "main_font_size": 18,
                                    "schedule_advance_minutes": 5})
    check("theme_mode 写入", settings.get("theme_mode") == "dark", settings.get("theme_mode"))
    check("main_font_size 写入", settings.get("main_font_size") == 18)
    check("课表服务侧写入", schedule.data["advance_minutes"] == 5, schedule.data)
    check("课表服务已保存", schedule.saves == 1, schedule.saves)

    print("[4] 类型不符 / 未知键被忽略")
    harness.call("settings.patch", {"main_font_size": "不是数字"})
    check("main_font_size 保持 18", settings.get("main_font_size") == 18,
          settings.get("main_font_size"))
    harness.call("settings.patch", {"不存在的键": 1})
    check("没有多出未知键", "不存在的键" not in settings.data)

    print("[5] plugins.list")
    plugins = harness.call("plugins.list")["result"]["plugins"]
    check("列出 1 个插件", len(plugins) == 1, len(plugins))
    if plugins:
        item = plugins[0]
        check("读到插件名", item["name"] == "时钟", item.get("name"))
        check("读到版本", item["version"] == "1.2.0")
        check("读到依赖", item["requires"] == ["requests"])
        check("标记为已加载", item["loaded"] is True)
        check("默认启用", item["enabled"] is True)

    print("[6] plugins.setEnabled")
    harness.call("plugins.setEnabled", {"id": "class.demo.clock", "enabled": False})
    check("写进 disabled_plugins",
          settings.get("disabled_plugins") == ["class.demo.clock"],
          settings.get("disabled_plugins"))
    again = harness.call("plugins.list")["result"]["plugins"]
    check("列表里变为未启用", again[0]["enabled"] is False)
    harness.call("plugins.setEnabled", {"id": "class.demo.clock", "enabled": True})
    check("再启用后清空", settings.get("disabled_plugins") == [],
          settings.get("disabled_plugins"))

    print("[7] settings.reset")
    harness.call("settings.patch", {"main_font_size": 22})
    harness.call("settings.reset")
    check("回到默认字号", settings.get("main_font_size") == DEFAULTS["main_font_size"])
    check("课表侧回到默认",
          schedule.data["advance_minutes"] == 2
          and schedule.data["time_offset_seconds"] == 0, schedule.data)

    print("[8] packages.status（不联网）")
    bridge._store = FakeStore(os.path.join(plugins_root, "packages"))
    packages = harness.call("packages.status")["result"]
    check("列出已装包", [e["name"] for e in packages["entries"]] == ["requests"],
          packages["entries"])
    check("标出使用它的插件",
          packages["entries"][0]["usedBy"] == ["class.demo.clock"],
          packages["entries"][0])
    check("标为已安装", packages["entries"][0]["installed"] is True,
          packages["entries"][0])
    check("给出下载源选项（页面据此画下拉）",
          [o["value"] for o in packages["sourceOptions"]] == ["official", "github", "gitee"],
          packages["sourceOptions"])
    check("带上下载源标签", packages["sourceLabel"] == "GitHub", packages["sourceLabel"])

    print("[9] 错误路径")
    err = harness.call("app.openFolder", {"id": "不存在的目录"})
    check("未知文件夹 → error 回包", "error" in err and err.get("result") is None, err)
    err2 = harness.call("根本没有这个方法")
    check("未知方法 → error 回包", "error" in err2, err2)

    print("[10] dialog.open 先回包、后弹窗")
    order = []
    bridge.reply.connect(lambda _s: order.append("reply"))
    bridge._call_app = lambda _name: order.append("action")

    result = harness.call("dialog.open", {"id": "timetable"})
    check("立即回 opened=true", bool(result) and result["result"] == {"opened": True}, result)
    check("此刻动作还没跑（已交给定时器）", order == ["reply"], order)

    QCoreApplication.processEvents()          # 跑一轮事件循环，动作才执行
    check("动作随后才执行", order == ["reply", "action"], order)

    print("[11] update.check 先回包")
    up = harness.call("update.check")["result"]
    check("带回 message 交给页面显示", bool(up.get("message")), up)

    # ---------------- 二级对话框（本轮新迁的四个） ----------------

    print("[12] 二级对话框：假期 / 调休 / 周末")
    data = harness.call("schedule.holidays.get")["result"]
    check("列出假期", data["holidays"][0]["name"] == "国庆", data)
    check("调休出境字段是驼峰 asWeekday",
          data["makeupDays"][0]["asWeekday"] == 4, data["makeupDays"])

    harness.call("schedule.holidays.add",
                 {"start": "2027-01-01", "end": "2027-01-03", "name": "元旦"})
    data = harness.call("schedule.holidays.get")["result"]
    check("假期加上了",
          len(data["holidays"]) == 2 and data["holidays"][1]["name"] == "元旦",
          data["holidays"])

    harness.call("schedule.holidays.remove", {"index": 1})
    check("假期删掉了",
          len(harness.call("schedule.holidays.get")["result"]["holidays"]) == 1)

    harness.call("schedule.makeup.add", {"date": "2027-01-09", "asWeekday": 9})
    data = harness.call("schedule.holidays.get")["result"]
    check("补周几被夹到 0..6", data["makeupDays"][-1]["asWeekday"] == 6, data["makeupDays"])

    err = harness.call("schedule.holidays.remove", {"index": 99})
    check("删不存在的假期 → error 回包", "error" in err, err)

    weekend = harness.call("schedule.weekend.get")["result"]
    check("周末出境字段是驼峰",
          weekend["morningSplit"] == "12:00"
          and weekend["afternoonPeriods"][0]["name"] == "午1", weekend)

    harness.call("schedule.weekend.set",
                 {"morningSplit": "", "afternoonPeriods": [], "courses": ["a", "b"]})
    weekend = harness.call("schedule.weekend.get")["result"]
    check("分界点留空回落 12:00", weekend["morningSplit"] == "12:00", weekend)
    check("下午节次与课程写进去了",
          weekend["afternoonPeriods"] == [] and weekend["courses"] == ["a", "b"], weekend)

    print("[13] 二级对话框：值日生名单")
    duty = harness.call("duty.get")["result"]
    check("列出名单与当前值日生",
          duty["list"] == ["张三", "李四"] and duty["current"] == "张三", duty)

    harness.call("duty.add", {"name": "王五"})
    check("逐个添加", harness.call("duty.get")["result"]["list"][-1] == "王五")

    err = harness.call("duty.add", {"name": "   "})
    check("空姓名 → error「姓名不能为空」",
          "error" in err and "姓名不能为空" in err["error"], err)

    harness.call("duty.addMany", {"names": ["赵六", "", " 钱七 "]})
    check("批量添加会去掉空白项",
          harness.call("duty.get")["result"]["list"][-2:] == ["赵六", "钱七"],
          harness.call("duty.get")["result"]["list"])

    harness.call("duty.remove", {"index": 0})
    check("删掉第一条", harness.call("duty.get")["result"]["list"][0] == "李四")

    print("[14] 二级对话框：作业编辑器")
    homework = harness.call("homework.get")["result"]
    check("条目索引连续", [it["index"] for it in homework["items"]] == [0, 1, 2],
          homework["items"])
    check("按科目分组、空科目归一为「未分类」",
          [g["subject"] for g in homework["groups"]] == ["语文", "未分类"],
          homework["groups"])
    check("组内条目带真实索引",
          [e["index"] for e in homework["groups"][0]["entries"]] == [0, 1],
          homework["groups"][0])

    err = harness.call("homework.add", {"subject": "", "content": "x"})
    check("科目为空 → error", "error" in err, err)

    harness.call("homework.add", {"subject": "数学", "content": "P32", "date": "10-13"})
    check("加上一条", harness.call("homework.get")["result"]["count"] == 4)

    harness.call("homework.update",
                 {"index": 0, "subject": "语文", "content": "改成这个", "date": "10-12"})
    check("改单条",
          harness.call("homework.get")["result"]["items"][0]["content"] == "改成这个")

    harness.call("homework.clearSubject", {"subject": "语文"})
    homework = harness.call("homework.get")["result"]
    check("整组清除", [g["subject"] for g in homework["groups"]] == ["未分类", "数学"],
          homework["groups"])

    err = harness.call("homework.remove", {"index": 99})
    check("删不存在的条目 → error 回包", "error" in err, err)

    # ---------------- 插件市场的形状与异步契约 ----------------

    print("[15] 插件市场：返回形状与「异步操作回 pending」的契约")
    status = harness.call("market.status")["result"]
    check("市场状态带来源选项（页面据此画下拉）",
          [o["value"] for o in status["sourceOptions"]] == ["official", "github", "gitee"],
          status.get("sourceOptions"))
    check("带 lastSync / busy（页面状态行要用）",
          "lastSync" in status and "busy" in status, sorted(status))
    check("条目出境字段是驼峰", "updateAvailable" in (status["entries"][0] if status["entries"] else {"updateAvailable": True}),
          status["entries"][:1])

    # Python 侧安装是异步的（丢给 QThread）：RPC 必须先回 pending，
    # 真结论由 task_done 信号推给页面。假装成功是错的。
    result = harness.call("market.install", {"id": "class.demo.clock"})
    check("安装回 pending 而不假装完成",
          bool(result) and result.get("result", {}).get("pending") is True, result)
    check("同时把结论当事件推给页面（market.done）",
          any(e["event"] == "market.done" for e in harness.events()),
          [e["event"] for e in harness.events()])

    switched = harness.call("market.setSource", {"source": "gitee"})["result"]
    check("切源会落盘并回报",
          switched.get("source") == "gitee" and settings.get("market_source") == "gitee",
          switched)

    err = harness.call("market.install", {})
    check("market.install 缺 id → error 回包", "error" in err, err)

    err = harness.call("market.setSource", {"source": "不存在的源"})
    check("不认识的索引来源 → error 回包", "error" in err, err)

    err = harness.call("packages.setSource", {"source": "不存在的源"})
    check("不认识的下载源 → error 回包", "error" in err, err)

    print()
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    for name in FAIL:
        print("  失败：" + name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
