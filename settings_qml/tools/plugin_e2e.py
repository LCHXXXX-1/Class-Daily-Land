"""端到端验证「插件设置」页：插件注册 → 桥列出 → 点名字打开原生设置页。

单独跑这个文件，不要用 selftest（它没有 QApplication 事件循环）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "settings_qml"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

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

    print("[1] load_all()")
    pm.load_all()
    for name, ok, message in getattr(pm, "loaded", []):
        print(f"    {'OK  ' if ok else 'FAIL'} {name} {'' if ok else message}")

    print("[2] 插件注册的设置页")
    pages = list(pm.get_settings_pages())
    print(f"    共 {len(pages)} 条")
    for e in pages:
        print(f"    - {e.get('name')} / {e.get('title')} / "
              f"factory={callable(e.get('factory'))}")

    print("[3] 桥列出的目录（QML 看到的就是这份）")
    bridge = PluginPages(plugin_manager=pm)
    rows = bridge.list()
    print(f"    count()={bridge.count()}")
    for r in rows:
        print(f"    - [{r['index']}] {r['title']} ({r['plugin']}) "
              f"icon={r['icon']} hasPage={r['hasPage']} "
              f"children={len(r['children'])}")

    ok = True
    if bridge.count() == 0:
        print("\n✗ 桥列出 0 条 —— QML 列表会是空的，点名字也不会有反应")
        ok = False

    print("[4] 点击名字 → open() 打开原生设置页")
    for r in rows:
        if not r["hasPage"]:
            continue
        # 不真弹模态（会阻塞），只验证 factory 能造出 QWidget
        entries = list(pm.get_settings_pages())
        factory = entries[r["index"]].get("factory")
        try:
            w = factory(None)
        except TypeError:
            w = factory()
        print(f"    factory({r['title']}) -> {type(w).__name__}")
        if w is None:
            print("    ✗ factory 返回 None")
            ok = False
        else:
            w.deleteLater()

    print("\n" + ("全部通过" if ok else "有问题，见上面 ✗"))
    QTimer.singleShot(0, app.quit)
    app.exec()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())