"""探针：插件设置页真的显示在设置窗口的**内容区**里吗（不是弹出来一个对话框）。

判断依据（不靠抓屏 —— 原生页是独立窗口，QQuickWindow.grabWindow 抓不到它）：
  1. 原生页的矩形 == 设置窗口位置 + QML 报上来的场景矩形（逐像素对）；
  2. 挪一下设置窗口，它要跟着挪，且仍然满足第 1 条；
  3. 页面本身有内容（用 QWidget.grab() 让控件自己渲染一张，不是空白）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CDL_DATA_ROOT", str(ROOT / "data"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import paths  # noqa: E402
from app.bootstrap import bootstrap_services  # noqa: E402
from app.window import SettingsApp  # noqa: E402

TARGET = sys.argv[1] if len(sys.argv) > 1 else "disaster"
OUT = ROOT / "_shots" / "plugin-page.png"

app = QApplication(sys.argv[:1])
services = bootstrap_services()
if services is None:
    raise SystemExit("没有主程序项目，跑不了嵌入检查")

settings_app = SettingsApp((paths.QML_DIR / "Settings.qml").resolve(), page=None,
                           services=services)
host = settings_app.plugin_host
root = settings_app.root

print(f"prepare({TARGET}) ->", host.prepare(TARGET),
      "title=", host.title, "err=", host.error)
settings_app.show(1232, 762, modal=False)
settings_app.goto("插件设置")

state: dict = {}


def snapshot(tag: str) -> bool:
    widget = host._host  # noqa: SLF001 - 探针就是要看内部件
    if widget is None:
        print(f"{tag} FAIL 没有原生页")
        return False
    rg = root.geometry()
    g = widget.geometry()
    scene = host.lastArea
    want_x, want_y = int(rg.x() + scene[0]), int(rg.y() + scene[1])
    relx, rely = g.x() - rg.x(), g.y() - rg.y()
    print(f"{tag} 窗口={rg.getRect()} 场景={[round(v) for v in scene]}")
    print(f"{tag} 原生页={g.getRect()} 相对窗口=({relx},{rely})")
    right_pos = abs(g.x() - want_x) <= 2 and abs(g.y() - want_y) <= 2
    inside = (0 < relx < rg.width() and 0 < rely < rg.height()
              and relx + g.width() <= rg.width() + 2
              and rely + g.height() <= rg.height() + 2)
    sized = g.width() > 200 and g.height() > 200
    print(f"{tag} 位置吻合={right_pos} 落在窗口内={inside} 尺寸合理={sized}")
    return right_pos and inside and sized


def step1() -> None:
    state["ok1"] = snapshot("[初始]")
    rg = root.geometry()
    root.setPosition(rg.x() + 160, rg.y() + 120)
    QTimer.singleShot(900, step2)


def step2() -> None:
    state["ok2"] = snapshot("[移动后]")
    widget = host._host  # noqa: SLF001
    shot = widget.grab() if widget is not None else None
    if shot is not None and not shot.isNull():
        OUT.parent.mkdir(parents=True, exist_ok=True)
        shot.save(str(OUT))
        img = shot.toImage()
        # 空页只有 1~2 种颜色；有表单控件会有几十种（边框、文字、下拉箭头）
        colors = set()
        for y in range(4, img.height() - 4, 3):
            for x in range(4, img.width() - 4, 3):
                colors.add(img.pixel(x, y))
                if len(colors) > 40:
                    break
        print(f"页面自渲染 {img.width()}x{img.height()} 采样色数={len(colors)} -> {OUT}")
        state["ok3"] = len(colors) > 12
    else:
        state["ok3"] = False

    good = all(state.get(k) for k in ("ok1", "ok2", "ok3"))
    print("PASS" if good else "FAIL", state)
    app.exit(0 if good else 1)


QTimer.singleShot(2800, step1)
app.exec()

# RinUI 的 nativeEventFilter 在解释器收尾时会去碰已析构的窗口，直接绕开
os._exit(0)
