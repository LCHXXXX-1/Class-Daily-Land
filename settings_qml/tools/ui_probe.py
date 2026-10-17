"""界面行为探针：导航强调条 + 转场方向。

    python tools/ui_probe.py

要验的是「旧页滑走、新页原地出现」这套：
  · 新页（currentItem）转场期间**不动**
  · 旧页（栈里 get(0)）按方向滑走：forward 往左、back 往右、down 往上
  · 强调条跟着高亮项走
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
from app.window import SettingsApp  # noqa: E402

app = QApplication(sys.argv[:1])
settings_app = SettingsApp((paths.QML_DIR / "Settings.qml").resolve())
settings_app.show(1232, 762)
root = settings_app.root

results: dict[str, bool] = {}
in_frames: list[tuple[float, float]] = []
out_frames: list[tuple[float, float]] = []
step: dict[str, float] = {}


def q(name: str):
    return root.property(name)


def vec(v) -> tuple[float, float]:
    pt = v.toVariant() if hasattr(v, "toVariant") else v
    try:
        return (float(pt.x()), float(pt.y()))
    except Exception:
        return (float(pt[0]), float(pt[1]))


sampler = QTimer()
sampler.setInterval(20)


def tick() -> None:
    in_frames.append(vec(root.property("navContentOffset")))
    out_frames.append((float(q("navExitX")), float(q("navExitY"))))


sampler.timeout.connect(tick)


def switch(title: str, then, wait: int = 820) -> None:
    in_frames.clear()
    out_frames.clear()
    sampler.start()
    settings_app.goto(title)
    QTimer.singleShot(wait, lambda: (sampler.stop(), then()))


def span(frames):
    if not frames:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [f[0] for f in frames]
    ys = [f[1] for f in frames]
    return (min(xs), max(xs), min(ys), max(ys))


def s1() -> None:
    switch("通用", s2)


def s2() -> None:
    step["y1"] = q("navMarkerY")
    results["marker_shown"] = bool(q("navMarkerShown"))
    print(f"[通用] marker y={step['y1']}")
    switch("关于", s3)


def s3() -> None:
    y2 = q("navMarkerY")
    print(f"[关于] marker y={y2}")
    results["marker_moves"] = abs(y2 - step["y1"]) > 20

    ix0, ix1, iy0, iy1 = span(in_frames)
    ox0, ox1, oy0, oy1 = span(out_frames)
    print("转场状态:", root.property("navTransitionState"),
          "slideIn=", root.property("navCurSlideIn"),
          "slideOut=", root.property("navCurSlideOut"))
    print(f"纵向切页：新页 x={ix0:.0f}~{ix1:.0f} y={iy0:.0f}~{iy1:.0f}")
    print(f"          旧页 x={ox0:.0f}~{ox1:.0f} y={oy0:.0f}~{oy1:.0f}")
    # 「关于」在下面 → down：新页从上往下落（y 从负到 0），旧页往上走
    results["enter_from_top"] = (iy0 - iy1) < -40 and abs(ix1 - ix0) < 2
    results["exit_up"] = (oy0 - oy1) < -40 and abs(ox1 - ox0) < 2
    switch("课表与提醒", s4)


def s4() -> None:
    switch("课表管理", s5)


def s5() -> None:
    ix0, ix1, iy0, iy1 = span(in_frames)
    ox0, ox1, oy0, oy1 = span(out_frames)
    print(f"进子页：新页 x={ix0:.0f}~{ix1:.0f} | 旧页 x={ox0:.0f}~{ox1:.0f}")
    results["enter_from_right"] = (ix1 - ix0) > 40
    results["exit_left"] = (ox0 - ox1) < -40
    switch("课表与提醒", s6)


def s6() -> None:
    ix0, ix1, iy0, iy1 = span(in_frames)
    ox0, ox1, oy0, oy1 = span(out_frames)
    print(f"返回父页：新页 x={ix0:.0f}~{ix1:.0f} | 旧页 x={ox0:.0f}~{ox1:.0f}")
    results["enter_from_left"] = (ix0 - ix1) < -40
    results["exit_right"] = (ox1 - ox0) > 40
    finish()


def finish() -> None:
    print("\n结果:", {k: bool(v) for k, v in results.items()})
    ok = all(results.values())
    print("PASS" if ok else "FAIL")
    app.exit(0 if ok else 1)


QTimer.singleShot(2600, s1)
QTimer.singleShot(30000, lambda: app.exit(9))
app.exec()
os._exit(0)
