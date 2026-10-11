"""周末课表桥的端到端验证：读 → 存 → 真的生效于 courses_for。

关键断言：存完之后 get_status() 在周末必须能看到课，而不只是 JSON 变了。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "settings_qml"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import paths as py_paths  # noqa: E402
from schedule import ScheduleManager  # noqa: E402

from app.extra import TimetableStore  # noqa: E402

BACKUP = ROOT / "settings" / "schedule.json.bak_wk"


def main() -> int:
    app = QApplication(sys.argv)
    src = Path(py_paths.CONFIG_DIR) / "schedule.json"
    BACKUP.write_bytes(src.read_bytes())

    mgr = ScheduleManager(py_paths.CONFIG_DIR)
    store = TimetableStore(schedule=mgr)
    ok = True

    def check(label, cond, extra=""):
        nonlocal ok
        print(f"    {'✓' if cond else '✗'} {label} {extra}")
        if not cond:
            ok = False

    try:
        print("[1] 读取现状")
        w = store.weekend()
        print(f"    {w}")
        check("available", w["available"] is True)

        print("[2] 保存周末课程 + 上下午分界 + 下午节次")
        res = store.saveWeekend(
            "11:30",
            [{"name": "下午1", "start": "14:00", "end": "14:45"},
             {"name": "下午2", "start": "15:00", "end": "15:45"}],
            ["数学", "英语", "体育", "", "自习"])
        print(f"    {res}")
        check("保存成功", res.get("ok") is True)

        print("[3] 回读")
        w2 = store.weekend()
        print(f"    {w2}")
        check("分界 = 11:30", w2["morningSplit"] == "11:30")
        check("下午节次 2 个", len(w2["afternoonPeriods"]) == 2)
        check("课程去掉空串", w2["courses"] == ["数学", "英语", "体育", "自习"],
              str(w2["courses"]))

        print("[4] 真正生效于 courses_for / get_status（周六周日）")
        # 2026-10-10 周六 / 2026-10-11 周日
        for d, label in ((datetime(2026, 10, 10, 9, 0), "周六"),
                         (datetime(2026, 10, 11, 15, 10), "周日")):
            courses = mgr.get_today_courses(d)
            st = mgr.get_status(d)
            print(f"    {label}: courses={courses} status={st}")
            check(f"{label} 能读到课程", len(courses) > 0)
            check(f"{label} status 不是 none", st.get("status") != "none",
                  f"→ {st.get('status')}")

        print("[5] 拒绝非法输入")
        for label, args in (
            ("时间格式错", ("11:30", [{"name": "x", "start": "25:00",
                                       "end": "14:00"}], [])),
            ("结束早于开始", ("11:30", [{"name": "x", "start": "15:00",
                                        "end": "14:00"}], [])),
            ("分界格式错", ("abc", [], [])),
        ):
            r = store.saveWeekend(*args)
            check(f"{label} 被拒", r.get("ok") is not True, f"→ {r.get('error')}")

    finally:
        src.write_bytes(BACKUP.read_bytes())
        BACKUP.unlink(missing_ok=True)
        print("\n[还原] schedule.json 已恢复")

    print("\n" + ("全部通过" if ok else "有问题，见上面 ✗"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())