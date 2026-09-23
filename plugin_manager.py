import os
import json
import importlib.util

from PySide6.QtCore import QTimer


class PluginAPI:
    def __init__(self, manager, plugin_name):
        self._m = manager
        self._name = plugin_name

    def add_island_text(self, fn):
        self._m.island_text_funcs.append(fn)

    def add_panel(self, fn):
        self._m.panel_funcs.append(fn)

    def set_interval(self, seconds, fn):
        timer = QTimer()
        timer.setInterval(int(seconds * 1000))
        timer.timeout.connect(fn)
        timer.start()
        self._m.timers.append(timer)

    def on_start(self, fn):
        self._m.start_funcs.append(fn)

    def request_refresh(self):
        if self._m.on_refresh:
            self._m.on_refresh()


class PluginManager:
    def __init__(self, plugins_dir, on_refresh=None):
        self.plugins_dir = plugins_dir
        self.on_refresh = on_refresh

        self.island_text_funcs = []
        self.panel_funcs = []
        self.start_funcs = []
        self.timers = []
        self.loaded = []

    def load_all(self):
        if not os.path.isdir(self.plugins_dir):
            return
        for name in sorted(os.listdir(self.plugins_dir)):
            plugin_dir = os.path.join(self.plugins_dir, name)
            if os.path.isdir(plugin_dir):
                self._load_one_dir(name, plugin_dir)
        for fn in self.start_funcs:
            try:
                fn()
            except Exception as e:
                print(f"[Plugin] on_start 出错: {e}")

    def _load_one_dir(self, name, plugin_dir):
        meta_path = os.path.join(plugin_dir, 'plugin.json')
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            entry_path = os.path.join(plugin_dir, meta.get('entry', 'main.py'))
        except Exception as e:
            self.loaded.append((name, False, f"读元信息失败: {e}"))
            return

        if not os.path.exists(entry_path):
            self.loaded.append((name, False, "入口不存在"))
            return

        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{name}", entry_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            self.loaded.append((name, False, f"加载失败: {e}"))
            return

        if not hasattr(module, 'register'):
            self.loaded.append((name, False, "无 register"))
            return

        api = PluginAPI(self, name)
        try:
            module.register(api)
        except Exception as e:
            self.loaded.append((name, False, f"register 出错: {e}"))
            return

        self.loaded.append((name, True, "OK"))

    def get_island_text(self):
        parts = []
        for fn in self.island_text_funcs:
            try:
                t = fn()
                if t:
                    parts.append(str(t))
            except Exception as e:
                print(f"[Plugin] island_text 出错: {e}")
        return "　".join(parts)

    def get_panel_specs(self):
        specs = []
        for fn in self.panel_funcs:
            try:
                spec = fn()
                if spec and spec.get('text'):
                    specs.append(spec)
            except Exception as e:
                print(f"[Plugin] panel 出错: {e}")
        return specs