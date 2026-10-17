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
from app.pluginhome import PluginHost  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)

    plugins_dir = str(ROOT / "plugins")
    py_paths.PLUGINS_DIR = plugins_dir
    pm = PluginManager(plugins_dir, settings=SettingsManager(py_paths.CONFIG_DIR))

    print("[1] register_builtins() + load_all()")
    pm.register_builtins()
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
        print(f"    - {r['title']} ({r['plugin']}) "
              f"icon={r['icon']} hasPage={r['hasPage']} "
              f"children={len(r['children'])}")

    ok = True
    if bridge.count() == 0:
        print("\n✗ 桥列出 0 条 —— QML 列表会是空的，点名字也不会有反应")
        print("   （plugins/ 目录现在空着是正常的：两个功能已内置，注册后应该出现在列表里）")
        ok = False

    print("[4] 点击名字 → PluginHost.prepare() 建出可内嵌的原生页")
    host = PluginHost(plugin_manager=pm, pages=bridge)
    for r in rows:
        if not r["hasPage"]:
            continue
        good = host.prepare(r["plugin"])
        widget = host._host  # noqa: SLF001 - 探针看内部件
        size = widget.size() if widget is not None else None
        print(f"    prepare({r['plugin']}) -> {good} "
              f"title={host.title!r} widget={type(widget).__name__} "
              f"size={size.width()}x{size.height() if size else 0}")
        if not good or widget is None:
            ok = False
        host.release()

    print("\n" + ("全部通过" if ok else "有问题，见上面 ✗"))
    QTimer.singleShot(0, app.quit)
    app.exec()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())