"""把设置中心渲染成 png，用来肉眼核对界面。

    python tools/shot.py <页面标题> <输出.png> [宽 高]

两点经验：
  · **不要**用 QT_QPA_PLATFORM=offscreen —— software 后端不栅格化文字，
    抓出来只有色块和图标，看不到任何文案。默认的 windows 平台能正常出字。
  · 页面靠 `Paths.startPage()` 在首次 push 时直达，抓图前等 ~2.4s：
    首屏那次转场要等窗口可见后才收尾。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # settings_qml/
sys.path.insert(0, str(ROOT))

# 演示数据根：默认就用本项目的 data/，不碰主程序的真实配置
os.environ.setdefault("CDL_DATA_ROOT", str(ROOT / "data"))


def main() -> int:
    page = sys.argv[1] if len(sys.argv) > 1 else None
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else (ROOT / "_shots" / "shot.png")
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 1232
    height = int(sys.argv[4]) if len(sys.argv) > 4 else 762
    embedded = os.environ.get("CDL_SHOT_EMBEDDED") == "1"

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from app import paths
    from app.window import SettingsApp

    app = QApplication(sys.argv[:1])
    services = None
    if embedded:
        # 借用主程序的真实管理器（数据目录已被 bootstrap 改接到本项目 data/，
        # 不会碰主程序的 settings/）。插件页要显示「可设置」必须走这条路 ——
        # 演示模式没有 PluginManager，hasPageFor() 恒为 false。
        from app.bootstrap import bootstrap_services

        services = bootstrap_services()
        if services is None:
            print("没有找到主程序项目，退回演示模式")

    settings_app = SettingsApp((paths.QML_DIR / "Settings.qml").resolve(),
                               page=page, services=services)
    settings_app.show(width, height)
    root = settings_app.root

    def grab() -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        image = root.grabWindow()
        ok = not image.isNull() and image.save(str(out))
        print(f'{"OK  " if ok else "FAIL"} {out}  {image.width()}x{image.height()}')
        print("  高亮项：", repr(root.property("navHighlightedTitle")))
        print("  强调条：shown=", root.property("navMarkerShown"),
              "y=", root.property("navMarkerY"))
        print("  导航：push=", root.property("navPushInProgress"),
              "busy=", root.property("navBusy"),
              "depth=", root.property("navDepth"),
              "item=", root.property("navCurrentItem"))
        app.exit(0 if ok else 1)

    QTimer.singleShot(2400, grab)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
