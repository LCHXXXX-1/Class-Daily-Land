"""插件系统：加载、生命周期、以及完整的 PluginAPI。"""
import os
import json
import importlib.util
import traceback

from PySide6.QtCore import QTimer

from storage import read_json, write_json


class PluginAPI:
    """暴露给插件的接口。"""

    def __init__(self, manager, plugin_name, plugin_dir):
        self._m = manager
        self._name = plugin_name
        self._dir = plugin_dir
        self._timers = []

    # ---- 生命周期 ----
    def on_load(self, fn):
        self._m.load_funcs.append(fn)

    def on_start(self, fn):
        self._m.start_funcs.append(fn)

    def on_stop(self, fn):
        self._m.stop_funcs.append((self._name, fn))

    # ---- 灵动岛（主岛）文本 ----
    def add_island_text(self, fn):
        self._m.island_text_funcs.append(fn)

    # ---- 主岛加长片段 ----
    def add_island_extra(self, fn):
        """注册主岛右侧的加长片段。fn() 返回 {width, draw, on_click?, priority?} 或 None。"""
        self._m.extra_funcs.append(fn)

    # ---- 下拉面板 ----
    def add_panel(self, fn):
        self._m.panel_funcs.append(fn)

    # ---- 副岛 ----
    def add_subisland(self, fn):
        self._m.subisland_funcs.append(fn)

    def set_subisland_length(self, px):
        try:
            self._m.subisland_length = int(px)
        except (TypeError, ValueError):
            return
        self.request_refresh()

    def set_subisland_collapsed(self, collapsed):
        if self._m.subisland_control is not None:
            try:
                self._m.subisland_control(bool(collapsed))
            except Exception as e:
                self.log(f'控制副岛失败: {e}')

    def collapse_subisland(self):
        self.set_subisland_collapsed(True)

    def expand_subisland(self):
        self.set_subisland_collapsed(False)

    def on_subisland_click(self, fn):
        self._m.subisland_click_funcs.append(fn)

    def subisland_show_weather(self, enabled):
        self._m.subisland_weather = bool(enabled)
        self.request_refresh()

    # ---- 设置页 ----
    def add_settings_page(self, title, factory, icon="🧩"):
        """注册一个插件设置页。factory(api) 需返回一个 QWidget。"""
        self._m.settings_pages.append({
            'name': self._name,
            'title': str(title),
            'icon': icon or "🧩",
            'factory': factory,
            'api': self,
        })

    # ---- 定时器 ----
    def set_interval(self, seconds, fn, start=True):
        timer = QTimer()
        timer.setInterval(max(1, int(seconds * 1000)))
        timer.timeout.connect(fn)
        self._timers.append(timer)
        self._m.timers.append(timer)
        if start:
            timer.start()
        return timer

    def set_timeout(self, seconds, fn):
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(fn)
        self._timers.append(timer)
        self._m.timers.append(timer)
        timer.start(max(1, int(seconds * 1000)))
        return timer

    # ---- 配置 ----
    def get_data_dir(self):
        os.makedirs(self._dir, exist_ok=True)
        return self._dir

    def get_config(self, default=None):
        path = os.path.join(self._dir, 'data.json')
        data = read_json(path, default=default)
        return data if data is not None else default

    def set_config(self, data):
        os.makedirs(self._dir, exist_ok=True)
        write_json(os.path.join(self._dir, 'data.json'), data)
        self.request_refresh()

    # ---- 课表状态 ----
    def get_schedule_status(self):
        fn = self._m.schedule_status_provider
        if fn is None:
            return None
        try:
            return fn()
        except Exception as e:
            self.log(f'获取课表状态失败: {e}')
            return None

    def is_in_class(self):
        st = self.get_schedule_status()
        return bool(st and st.get('status') == 'ongoing')

    # ---- 日志 / 交互 ----
    def log(self, *args):
        self._m.log(self._name, *args)

    def request_refresh(self):
        if self._m.on_refresh is not None:
            self._m.on_refresh()

    def notify(self, text, is_end=False):
        if self._m.on_notify is not None:
            try:
                self._m.on_notify(str(text), bool(is_end))
            except Exception as e:
                self.log(f'notify 失败: {e}')


class PluginManager:
    def __init__(self, plugins_dir, on_refresh=None, on_notify=None):
        self.plugins_dir = plugins_dir
        self.on_refresh = on_refresh
        self.on_notify = on_notify

        self.island_text_funcs = []
        self.extra_funcs = []
        self.panel_funcs = []
        self.subisland_funcs = []
        self.subisland_click_funcs = []
        self.load_funcs = []
        self.start_funcs = []
        self.stop_funcs = []
        self.timers = []
        self.loaded = []
        self.settings_pages = []

        self.subisland_length = None
        self.subisland_weather = True
        self.subisland_control = None
        self.schedule_status_provider = None

    # ---------- 载入 ----------
    def load_all(self):
        if not os.path.isdir(self.plugins_dir):
            return
        for name in sorted(os.listdir(self.plugins_dir)):
            plugin_dir = os.path.join(self.plugins_dir, name)
            if os.path.isdir(plugin_dir):
                self._load_one_dir(name, plugin_dir)

        for fn in self.load_funcs:
            self._call(fn, 'on_load')

        for fn in self.start_funcs:
            self._call(fn, 'on_start')

    def _load_one_dir(self, name, plugin_dir):
        meta_path = os.path.join(plugin_dir, 'plugin.json')
        try:
            meta = read_json(meta_path, default={})
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
            self.log(name, traceback.format_exc())
            return

        if not hasattr(module, 'register'):
            self.loaded.append((name, False, "无 register"))
            return

        api = PluginAPI(self, name, plugin_dir)
        try:
            module.register(api)
        except Exception as e:
            self.loaded.append((name, False, f"register 出错: {e}"))
            self.log(name, traceback.format_exc())
            return

        self.loaded.append((name, True, "OK"))

    # ---------- 生命周期 ----------
    def stop_all(self):
        for timer in self.timers:
            try:
                timer.stop()
            except Exception:
                pass
        self.timers = []
        for name, fn in self.stop_funcs:
            self._call(fn, 'on_stop', name)

    def set_subisland_control(self, fn):
        self.subisland_control = fn

    def set_schedule_status_provider(self, fn):
        self.schedule_status_provider = fn

    def get_settings_pages(self):
        return list(self.settings_pages)

    # ---------- 数据聚合 ----------
    def get_island_text(self):
        parts = []
        for fn in self.island_text_funcs:
            try:
                t = fn()
                if t:
                    parts.append(str(t))
            except Exception as e:
                self.log('plugin', f'island_text 出错: {e}')
        return "　".join(parts)

    def get_panel_specs(self):
        specs = []
        for fn in self.panel_funcs:
            try:
                spec = fn()
                if spec and spec.get('text'):
                    specs.append(spec)
            except Exception as e:
                self.log('plugin', f'panel 出错: {e}')
        return specs

    def get_subisland_spec(self):
        best, best_p = None, None
        for fn in self.subisland_funcs:
            try:
                spec = fn()
            except Exception as e:
                self.log('plugin', f'subisland 出错: {e}')
                continue
            if not spec or not (spec.get('text') or spec.get('draw')):
                continue
            try:
                p = int(spec.get('priority', 0))
            except (TypeError, ValueError):
                p = 0
            if best is None or p > best_p:
                best, best_p = spec, p
        if best is None:
            return None
        if not best.get('length') and self.subisland_length:
            best['length'] = self.subisland_length
        return best

    def get_island_extra(self):
        best, best_p = None, None
        for fn in self.extra_funcs:
            try:
                spec = fn()
            except Exception as e:
                self.log('plugin', f'island_extra 出错: {e}')
                continue
            if not spec:
                continue
            try:
                p = int(spec.get('priority', 0))
            except (TypeError, ValueError):
                p = 0
            if best is None or p > best_p:
                best, best_p = spec, p
        return best

    def handle_subisland_click(self):
        for fn in self.subisland_click_funcs:
            try:
                fn()
            except Exception as e:
                self.log('plugin', f'subisland_click 出错: {e}')

    # ---------- 工具 ----------
    def _call(self, fn, tag, name=''):
        try:
            fn()
        except Exception as e:
            self.log(name or 'plugin', f'{tag} 出错: {e}')

    def log(self, name, *args):
        print(f"[Plugin:{name}]", *args)
