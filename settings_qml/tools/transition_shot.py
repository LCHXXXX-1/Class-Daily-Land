"""抓设置中心「横向转场」的中间帧，用来肉眼确认动画方向。

    python settings_qml/tools/transition_shot.py [输出目录]

为什么需要它：转场是纯动画，编译自检只能证明「代码没写错」，
证明不了「看起来是不是用户要的那个方向」—— 旧页往左退、新页从右推进。
所以这里在切页之后按固定间隔连拍，把中间帧摊开看。

做法：gotoTitle 先停在父页 → 等转场彻底结束（静止基线帧）→
      再 gotoTitle 子页，从那一刻起每35ms 抓一张。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_TMP = tempfile.TemporaryDirectory(prefix="cdl-transition-")
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

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import paths  # noqa: E402
from app.window import SettingsApp  # noqa: E402

# 连拍参数：帧数 × 间隔 ≈ 覆盖 260ms 位移 + 淡入尾巴
FRAMES = 8
INTERVAL_MS = 35


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "_transition")
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        try:
            old.unlink()
        except OSError:
            pass

    app = QApplication(sys.argv)
    qml_path = (paths.APP_ROOT / "qml/Settings.qml").resolve()

    sa = SettingsApp(qml_path)
    sa.show(1180, 800)

    shots: list[QTimer] = []

    def snap(tag: str, index: int) -> None:
        image = sa.root.grabWindow()
        if image.isNull() or image.width() == 0:
            print(f"  !! {tag}-{index} 抓到空图")
            return
        target = out_dir / f"{tag}-{index:02d}.png"
        ok = image.save(str(target))
        print(f"  {'OK ' if ok else 'FAIL'} {target.name}  {image.width()}x{image.height()}")

    def run_burst() -> None:
        print("连拍开始（旧页应该在往左退、新页从右推进）")
        sa.goto("插件管理")
        for i in range(FRAMES):
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda n=i: snap("burst", n))
            shots.append(timer)
            timer.start(INTERVAL_MS * (i + 1))
        QTimer.singleShot(INTERVAL_MS * (FRAMES + 1) + 900, app.quit)

    def baseline() -> None:
        print("抓静止基线（父页「插件」）")
        snap("base", 0)
        QTimer.singleShot(120, run_burst)

    def start() -> None:
        sa.goto("插件")
        QTimer.singleShot(1200, baseline)

    QTimer.singleShot(1600, start)
    rc = app.exec()
    _TMP.cleanup()
    print(f"\n输出目录：{out_dir}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())