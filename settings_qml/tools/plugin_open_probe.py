"""验证 PluginPages.open() 真实调用链：factory 传参、对话框能否构造。

不真的 exec()（会阻塞），而是把 _present 换成只构造不弹，
这样能看清到底卡在哪一步。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "settings_qml"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import paths as py_paths  # noqa: E402
from plugin_manager import PluginManager  # noqa: E402
from settings_manager import SettingsManager  # noqa: E402

from app.pluginpages import PluginPages  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    plugins_dir = str(ROOT / "plugins")
    py_paths.PLUGINS_DIR = plugins_dir
    pm = PluginManager(plugins_dir, settings=SettingsManager(py_paths.CONFIG_DIR))
    pm.load_all()

    bridge = PluginPages(plugin_manager=pm)
    bridge.openFailed.connect(lambda t, m: print(f"    [openFailed] {t} -> {m}"))

    print("[1] 手动调 open()（exec 会阻塞，先把_present 降级为只构造）")
    calls = []
    orig = bridge._present

    def spy(title, content, plugin_name):
        calls.append((title, plugin_name, type(content).__name__))
        print(f"    _present 被调用: title={title!r} plugin={plugin_name!r} "
              f"content={type(content).__name__}")
        content.deleteLater()

    bridge._present = spy
    for i in range(bridge.count()):
        print(f"  open({i}) ->", bridge.open(i))

    print("[2] 结论")
    if calls:
        print(f"    ✓ {len(calls)} 个插件页成功构造并进入展示流程")
    else:
        print("    ✗ 一个都没构造成功 —— open 提前 return 了")

    print("[3] 恢复真实 _present，构造一次完整对话框但不 exec")
    bridge._present = orig
    dlg_box = {}
    real_exec = None

    from PySide6.QtWidgets import QDialog

    orig_exec = QDialog.exec

    def fake_exec(self):
        dlg_box["title"] = self.windowTitle()
        dlg_box["size"] = (self.width(), self.height())
        return 0

    QDialog.exec = fake_exec
    for i in range(bridge.count()):
        print(f"  open({i}) ->", bridge.open(i))
    QDialog.exec = orig_exec
    print("    对话框:", dlg_box)

    QTimer.singleShot(0, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())