import os
import json
import shutil
import sys
import time
import zipfile
import importlib.util
import traceback

from PySide6.QtCore import QTimer, QObject, Signal

import plugin_deps
from storage import read_json, write_json

# 插件包后缀（ZIP 压缩包）：.cbplugin 和 .cblplugin 都收，一碗水端平
PACKAGE_EXTS = ('.cblplugin', '.cbplugin')
# 兼容旧引用：默认后缀（取第一个）
PACKAGE_EXT = PACKAGE_EXTS[0]

# 包内 plugin.json 放根目录或唯一顶层子目录都可以，能自动找到
PACKAGE_MARKER = '.cblplugin.json'   # 记录安装来源，用来判断包有没有更新过


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

    # ---- 主岛紧急警报条（与副岛融合成一条） ----
    def add_island_banner(self, fn):
        """注册紧急警报条（地震等），比加长片段更强势。

        fn() 返回 {'text', 'ratio', 'color'?, 'min_width'?, 'priority'?,
        'on_click'?} 或 None：

        - 返回非 None 期间，主岛独占显示该长条：**顶掉课程文本、上课前倒计时
          与提醒条**（紧急事件优先于课表）
        - 副岛同时自动隐藏（两者在视觉上合成一条）
        - 不因上课 / PPT 全屏 / Office 前台而隐藏，被隐藏时自动拉回屏幕
        - ratio（0~1）驱动长条底部的进度填充（倒计时条随剩余时间收缩）
        """
        self._m.banner_funcs.append(fn)

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
    def add_settings_page(self, title, factory=None, icon="🧩",
                          icon_color=None, icon_bg=None, icon_path=None,
                          children=None):
        """注册一个插件设置页。factory(api) 需返回一个 QWidget。

        icon      ：emoji 字符，或设置窗口内置矢量图标名
                    （gear/palette/island/calendar/market/box/wrench/
                    plugin/info/book/pencil/list/people/sun/play/clock/back）
        icon_color：可选，图标颜色（如 "#0078d4"），不给则用主题默认色
        icon_bg   ：可选，图标背后的圆角色块颜色
        icon_path ：可选，自定义图标图片路径（png/ico，优先于 icon）
        children  ：可选，子页面列表（三级菜单），每项是一个 dict：
                    {"title": 标题, "factory": 同 factory,
                     "icon"/"icon_color"/"icon_bg"/"icon_path": 同上}
                    有 children 时 factory 可为 None（本页只作目录）。
        """
        self._m.settings_pages.append({
            'name': self._name,
            'title': str(title),
            'icon': icon or "🧩",
            'icon_color': icon_color,
            'icon_bg': icon_bg,
            'icon_path': icon_path,
            'children': list(children or ()),
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

    def notify(self, text, is_end=False, force=False):
        """弹出主岛提醒条。

        force=True：紧急预警（地震等），即便灵动岛因上课 / PPT 全屏被隐藏
        也会强制弹出并保持显示一段时间。
        """
        if self._m.on_notify is None:
            return
        try:
            self._m.on_notify(str(text), bool(is_end), bool(force))
        except TypeError:
            # 兼容只接受两个参数的老宿主实现
            try:
                self._m.on_notify(str(text), bool(is_end))
            except Exception as e:
                self.log(f'notify 失败: {e}')
        except Exception as e:
            self.log(f'notify 失败: {e}')


class _DepsHub(QObject):
    """主线程跳板：跨线程把回调送回主线程执行。

    依赖下载跑在工作线程，但「装完补加载插件」会创建 QTimer/QThread，
    必须在主线程做；信号→QObject 槽的队列连接由 Qt 负责搬运。
    """
    call_requested = Signal(object)

    def __init__(self):
        super().__init__()
        self.call_requested.connect(self._run)

    def _run(self, fn):
        try:
            fn()
        except Exception:
            pass


class PluginManager:
    def __init__(self, plugins_dir, on_refresh=None, on_notify=None,
                 settings=None):
        self.plugins_dir = plugins_dir
        self.on_refresh = on_refresh
        self.on_notify = on_notify
        self.settings = settings

        # ---- 第三方依赖库（plugins/packages/）----
        self.packages_dir = os.path.join(plugins_dir, 'packages')
        self.deps_db = plugin_deps.PackageDB(self.packages_dir)
        self.deps_progress = None          # 可选回调 fn(event dict)
        self._deps_hub = _DepsHub()        # 跨线程跳板（须有 QApplication）
        self._deps_abort = False           # 退出时中止依赖下载
        self._deps_thread = None           # 正在跑的下载线程
        self._deps_worker = None           # QObject 载体（跨线程信号）

        try:
            os.makedirs(self.packages_dir, exist_ok=True)
            if self.packages_dir not in sys.path:
                sys.path.insert(0, self.packages_dir)
        except Exception:
            pass
        self.refresh_dep_paths()

        self.island_text_funcs = []
        self.extra_funcs = []
        self.banner_funcs = []
        self.panel_funcs = []
        self.subisland_funcs = []
        self.subisland_click_funcs = []
        self.load_funcs = []
        self.start_funcs = []
        self.stop_funcs = []
        self.timers = []
        self.loaded = []
        self.settings_pages = []
        self.disabled_ids = set()      # 被禁用的插件目录名（插件市场维护）

        self.subisland_length = None
        self.subisland_weather = True
        self.subisland_control = None
        self.schedule_status_provider = None

    # ---------- 包后缀 ----------
    @staticmethod
    def _package_ext(filename):
        """返回文件名匹配到的插件包后缀（小写），不匹配就给 None。"""
        low = str(filename).lower()
        for ext in PACKAGE_EXTS:
            if low.endswith(ext):
                return ext
        return None

    # ---------- 载入 ----------
    def load_all(self):
        if not os.path.isdir(self.plugins_dir):
            return
        self._install_packages()          # 先安装 .cblplugin 包，再统一扫描目录
        for name in sorted(os.listdir(self.plugins_dir)):
            plugin_dir = os.path.join(self.plugins_dir, name)
            if os.path.isdir(plugin_dir):
                if name in self.disabled_ids:
                    continue              # 已禁用的插件不加载
                self._load_one_dir(name, plugin_dir)

        for fn in self.load_funcs:
            self._call(fn, 'on_load')

        for fn in self.start_funcs:
            self._call(fn, 'on_start')

    # ---------- 插件包安装（.cblplugin / .cbplugin） ----------
    def _install_packages(self):
        """把 plugins/*.cblplugin（ZIP 包）自动解压安装成插件目录。

        .cblplugin 和 .cbplugin 两种后缀都伺候。
        包没变化就跳过；包更新了（大小/修改时间变了）就覆盖重装，两种情况能区分。
        """
        try:
            names = sorted(os.listdir(self.plugins_dir))
        except Exception:
            return
        for fn in names:
            if self._package_ext(fn) is None:
                continue
            path = os.path.join(self.plugins_dir, fn)
            if not os.path.isfile(path):
                continue
            try:
                self._install_one_package(path, fn)
            except Exception as e:
                self.log('package', f'安装 {fn} 失败: {e}')

    def _install_one_package(self, path, filename):
        try:
            st = os.stat(path)
        except Exception:
            return
        try:
            zf = zipfile.ZipFile(path)
        except Exception as e:
            self.log('package', f'{filename} 不是有效的插件包（{e}）')
            return

        # 按实际匹配到的后缀截包名（两种后缀长度一样，但不写死）
        ext = self._package_ext(filename) or PACKAGE_EXT
        stem = filename[:-len(ext)]

        with zf:
            members = [n for n in zf.namelist() if not n.endswith('/')]
            root = self._package_root(members)
            if root is None:
                self.log('package', f'{filename} 内未找到 plugin.json，已跳过')
                return

            dir_name = (root.rstrip('/') if root
                        else self._dir_name_for(zf, filename, stem))
            target = os.path.join(self.plugins_dir, dir_name)
            marker = os.path.join(target, PACKAGE_MARKER)
            stamp = {'package': filename, 'size': int(st.st_size),
                     'mtime': int(st.st_mtime)}

            if os.path.isfile(marker):
                old = read_json(marker, default={}) or {}
                if (old.get('size') == stamp['size']
                        and old.get('mtime') == stamp['mtime']
                        and os.path.isfile(
                            os.path.join(target, 'plugin.json'))):
                    return            # 已安装且包未变化

            os.makedirs(target, exist_ok=True)
            ok = 0
            for n in zf.namelist():
                if n.endswith('/'):
                    continue
                rel = n[len(root):] if root else n
                dest = self._safe_join(target, rel)
                if dest is None:
                    self.log('package', f'{filename} 内含非法路径，已跳过: {n}')
                    continue
                parent = os.path.dirname(dest)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with zf.open(n) as fsrc, open(dest, 'wb') as fdst:
                    shutil.copyfileobj(fsrc, fdst)
                ok += 1

            if not os.path.isfile(os.path.join(target, 'plugin.json')):
                self.log('package', f'{filename} 解压后缺少 plugin.json')
                return
            stamp['extracted_at'] = time.time()
            stamp['files'] = ok
            write_json(marker, stamp)
            self.log('package',
                     f'{filename} 已安装到 plugins/{dir_name}/（{ok} 个文件）')

    @staticmethod
    def _package_root(members):
        """返回包内根前缀（'' 或 '子目录/'）；找不到 plugin.json 返回 None。"""
        if 'plugin.json' in members:
            return ''
        tops = {n.split('/', 1)[0] for n in members if '/' in n}
        for t in sorted(tops):
            if f'{t}/plugin.json' in members:
                return t + '/'
        return None

    @staticmethod
    def _safe_dir_name(name, allow_dot=False):
        """把任意名字洗成合法目录名。

        allow_dot=True 时保留点号——插件 id 可能带命名空间
        （class.<作者>.<名字>），洗掉点号就跟市场索引对不上了。
        首尾的点一律去掉，避免生成 "." / ".." 这种危险名字。
        """
        extra = ('_', '-', '.') if allow_dot else ('_', '-')
        s = '' if name is None else str(name)
        keep = ''.join(c for c in s if c.isalnum() or c in extra)
        keep = keep.strip('.')
        return keep or 'plugin'

    def _dir_name_for(self, zf, filename, stem):
        """决定插件包解压到 plugins/ 下用哪个目录名。

        顺序：
        1. 已经装过这个包（某个目录的 .cblplugin.json 里 package 字段就是
           这个文件名，或那个目录声明的名字与包内声明的名字有交集）
           → 沿用旧目录名，升级不重装；
        2. 包内 plugin.json 的 id → name（比文件名词干更可靠，也不怕用户
           随手改文件名）；带点号的名字保留点号；
        3. 兜底：文件名词干。

        这样做的好处是目录名稳定，并且能和插件市场的 package_name 对上，
        市场里不会再出现「明明装了却显示未安装」。
        """
        try:
            meta = json.loads(zf.read('plugin.json').decode('utf-8-sig'))
        except Exception:
            meta = None
        if not isinstance(meta, dict):
            meta = {}

        want = self._declared_dir_names(meta)

        # 1) 老目录沿用
        try:
            existing = sorted(os.listdir(self.plugins_dir))
        except Exception:
            existing = []
        for name in existing:
            d = os.path.join(self.plugins_dir, name)
            if not os.path.isdir(d):
                continue
            old = read_json(os.path.join(d, PACKAGE_MARKER), default={}) or {}
            if old.get('package') == filename:
                return name
            old_meta = read_json(os.path.join(d, 'plugin.json'), default=None)
            if want and isinstance(old_meta, dict):
                if set(self._declared_dir_names(old_meta)) & set(want):
                    return name

        # 2) 包内声明的 id / name
        if want:
            return want[0]

        # 3) 兜底
        return self._safe_dir_name(stem)

    @classmethod
    def _declared_dir_names(cls, meta):
        """包内 plugin.json 自己声明的目录名候选，id 优先、其次 name。

        保留点号，这样带命名空间的 id（class.<作者>.<名字>）能跟插件市场的
        package_name 对上。注意现网不少包只写 name 没写 id，所以 name 必须兜住。
        """
        out = []
        if not isinstance(meta, dict):
            return out
        for key in ('id', 'name'):
            val = meta.get(key)
            if not val:
                continue
            cand = cls._safe_dir_name(val, allow_dot=True)
            if cand != 'plugin' and cand not in out:
                out.append(cand)
        return out

    @staticmethod
    def _safe_join(base, rel):
        """防目录穿越：只允许解压到 base 内部。"""
        rel = str(rel).replace('\\', '/').lstrip('/')
        parts = [p for p in rel.split('/') if p not in ('', '.', '..')]
        if not parts:
            return None
        dest = os.path.join(base, *parts)
        base_abs = os.path.abspath(base)
        dest_abs = os.path.abspath(dest)
        if not (dest_abs == base_abs
                or dest_abs.startswith(base_abs + os.sep)):
            return None
        return dest

    @staticmethod
    def _resolve_entry(plugin_dir, entry):
        """把 plugin.json 里的 entry 解析成真实文件路径。

        兼容三种写法：
        - 文件名：``main.py``
        - 模块名：``main`` → 尝试 ``main.py`` / ``main/__init__.py``
        - 缺省 / 无效：回退到 ``main.py``
        返回第一个存在的候选路径；都不存在时返回按 entry 拼出的路径（供报错）。
        """
        entry = str(entry or 'main.py').strip() or 'main.py'
        cands = [entry]
        if not os.path.splitext(entry)[1]:
            cands.append(entry + '.py')
            cands.append(os.path.join(entry, '__init__.py'))
        cands.append('main.py')
        for cand in cands:
            path = os.path.join(plugin_dir, cand)
            if os.path.isfile(path):
                return path
        return os.path.join(plugin_dir, entry)

    def _load_one_dir(self, name, plugin_dir):
        meta_path = os.path.join(plugin_dir, 'plugin.json')
        try:
            meta = read_json(meta_path, default={})
            entry_path = self._resolve_entry(plugin_dir, meta.get('entry',
                                                                   'main.py'))
        except Exception as e:
            self.loaded.append((name, False, f"读元信息失败: {e}"))
            return

        if not os.path.exists(entry_path):
            self.loaded.append((name, False, "入口不存在"))
            return

        # ---- 第三方依赖：exec_module 之前的检查 ----
        # 同版本已就绪 → 直接放行；缺 / 版本不对 → 记 MISSING_DEP 并交给
        # 后台线程去下载，装齐后自动补加载（不阻塞启动）。
        if meta.get('requires'):
            if not self._deps_ready_for(meta['requires']):
                self.loaded.append((name, False,
                                    "MISSING_DEP: 依赖未就绪，正在后台安装"))
                self.schedule_deps_install(name, meta['requires'])
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
        self._deps_abort = True            # 正在下载的依赖包就此收手
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

    # ---------- 插件市场公开接口（仅追加，不影响既有加载逻辑） ----------
    def set_disabled_ids(self, ids):
        """设置被禁用的插件目录名集合（下次 load_all 时生效）。"""
        try:
            self.disabled_ids = {str(i) for i in (ids or ())}
        except TypeError:
            self.disabled_ids = set()

    def is_disabled(self, name):
        return name in self.disabled_ids

    def load_installed_plugin(self, name):
        """运行时加载一个**从未加载过**的插件目录（插件市场安装后调用）。

        只做加法：调用 _load_one_dir 后，单独执行本次新注册的
        on_load / on_start 回调。已在本次会话加载过的插件无法重新加载
        （Python 模块不能安全热卸载），需重启。返回 (是否成功, 消息)。
        """
        plugin_dir = os.path.join(self.plugins_dir, name)
        if not os.path.isdir(plugin_dir):
            return False, "插件目录不存在"
        if any(n == name and ok for n, ok, _msg in self.loaded):
            return False, "本会话已加载过，重启后生效"
        n_load = len(self.load_funcs)
        n_start = len(self.start_funcs)
        # 清掉同名失败记录（依赖没就绪 / 上次失败），重试成功后以新记录为准
        self.loaded = [t for t in self.loaded
                       if not (t[0] == name and not t[1])]
        before = len(self.loaded)
        self._load_one_dir(name, plugin_dir)
        if len(self.loaded) == before:
            return False, "加载失败"
        info = self.loaded[-1]
        if not info[1]:
            return False, info[2]
        for fn in self.load_funcs[n_load:]:
            self._call(fn, 'on_load', name)
        for fn in self.start_funcs[n_start:]:
            self._call(fn, 'on_start', name)
        if self.on_refresh is not None:
            try:
                self.on_refresh()
            except Exception as e:
                self.log(name, f"刷新失败: {e}")
        return True, "OK"

    # ---------- 第三方依赖库（plugins/packages/） ----------
    def packages_base_url(self):
        """清单地址候选（主地址 + 镜像）：按 packages_source 选源，
        packages_base_url 非空时只用它。可直接喂给 ensure_requirements。"""
        try:
            custom = self.settings.get('packages_base_url', '')
        except Exception:
            custom = ''
        try:
            source = self.settings.get('packages_source', '')
        except Exception:
            source = ''
        return plugin_deps.resolve_bases(source, custom)

    def refresh_dep_paths(self):
        """把每个依赖包目录也补进 sys.path。

        逐文件型依赖（如 requests）的导入根就在 packages/ 下，packages/ 已经
        在 sys.path；wheel 型依赖（如 pillow 的 PIL）解包后真正的顶层在
        packages/<包名>/ 里，需要再补这一层才能正常 import。
        """
        try:
            subs = os.listdir(self.packages_dir)
        except Exception:
            return
        for sub in subs:
            if sub.startswith('.'):
                continue
            path = os.path.join(self.packages_dir, sub)
            try:
                if os.path.isdir(path) and path not in sys.path:
                    sys.path.append(path)
            except Exception:
                continue

    def _deps_ready_for(self, requires):
        """声明的依赖是否都已「同版本」就绪（本地判断，不发网络请求）。

        注意：本地不知道服务器锁定的版本，只能检查“包目录在不在”。
        版本对不对要等清单拉下来才知道，由下载流程内部再核对。
        """
        names = plugin_deps.normalize_requires(requires)
        if not names:
            return True
        for n in names:
            if not os.path.isdir(os.path.join(self.packages_dir, n)):
                return False
        return True

    def _emit_deps(self, ev):
        """把进度事件转出去；任何异常都吞掉，绝不打断下载线程。"""
        cb = self.deps_progress
        if cb is None:
            return
        try:
            cb(ev)
        except Exception:
            pass

    def deps_busy(self):
        th = self._deps_thread
        if th is None:
            return False
        try:
            return th.isRunning()
        except RuntimeError:
            self._deps_thread = None
            return False

    def schedule_deps_install(self, plugin_name, requires):
        """后台线程安装依赖：进度走 deps_progress，装好自动补加载插件。

        同一时刻只跑一个任务；忙的时候把请求记入 _deps_pending，
        等当前任务收尾后自动接力。
        """
        names = plugin_deps.normalize_requires(requires)
        if not names:
            return False, "没有可安装的依赖"
        if self._deps_abort:
            return False, "程序正在退出"
        if self.deps_busy():
            pend = getattr(self, '_deps_pending', None)
            if pend is None:
                pend = self._deps_pending = {}
            pend[plugin_name] = names
            return True, "已排队，等当前下载完成"
        return self._start_deps_task(plugin_name, names)

    def _start_deps_task(self, plugin_name, names):
        try:
            from PySide6.QtCore import QThread

            class _DepThread(QThread):
                """依赖下载线程：run 里干活，信号跨线程回主线程。"""

                def __init__(self, manager, plugin, pkgs):
                    QThread.__init__(self)
                    self.m = manager
                    self.plugin = plugin
                    self.pkgs = list(pkgs)

                def run(self):
                    ok = True
                    msg = ''
                    try:
                        _ready, errors = plugin_deps.ensure_requirements(
                            self.m.deps_db, self.m.packages_dir,
                            self.m.packages_base_url(), self.plugin,
                            self.pkgs,
                            emit=lambda ev: self.m._deps_hub.call_requested.emit(
                                lambda ev=ev: self.m._on_deps_event(ev)),
                            should_abort=lambda: self.m._deps_abort)
                        if errors:
                            ok = False
                            msg = '；'.join(errors.values())
                    except Exception as e:
                        ok = False
                        msg = str(e) or e.__class__.__name__
                    self.m._deps_hub.call_requested.emit(
                        lambda: self.m._on_deps_finished(self.plugin,
                                                         ok, msg))
        except Exception as e:
            return False, f"依赖安装线程起不来: {e}"

        thread = _DepThread(self, plugin_name, names)
        # run() 返回后线程自然结束；结束时销毁对象（deleteLater 会排队
        # 回线程归属地的主线程执行，安全）
        thread.finished.connect(thread.deleteLater)
        self._deps_thread = thread
        thread.start()
        return True, "已在后台开始安装"

    def _on_deps_event(self, ev):
        if isinstance(ev, dict):
            self.log('deps', str(ev.get('text', '')))
        self._emit_deps(ev)

    def _on_deps_finished(self, plugin_name, ok, msg):
        self._deps_thread = None
        self._deps_worker = None
        if ok:
            self.log('deps', f'{plugin_name} 的依赖装好了')
            self.refresh_dep_paths()
            try:
                self.load_installed_plugin(plugin_name)
            except Exception as e:
                self.log('deps', f'补加载 {plugin_name} 失败: {e}')
        else:
            self.log('deps', f'{plugin_name} 的依赖安装失败: {msg}')
        self._emit_deps({'stage': 'failed' if not ok else 'done',
                         'plugin': plugin_name, 'package': '',
                         'text': ('依赖装好了，可以重新加载插件'
                                  if ok else f'依赖安装失败: {msg}')})
        # 接力排队中的下一个请求
        pend = getattr(self, '_deps_pending', None) or {}
        self._deps_pending = {}
        for name, pkgs in pend.items():
            self.schedule_deps_install(name, pkgs)

    def release_plugin_deps(self, plugin_name):
        """插件卸载时调用：从各依赖包 used_by 摘掉自己，空包顺带删除。

        返回被删除的依赖包名列表（可能为空）。
        """
        try:
            removed = self.deps_db.release(plugin_name)
        except Exception as e:
            self.log('deps', f'回收依赖失败: {e}')
            return []
        if removed:
            self.log('deps', f'{plugin_name} 卸载后回收依赖包: '
                             + '、'.join(removed))
        return removed

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

    def get_island_banner(self):
        """取当前应当显示的紧急警报条（priority 最大者独占）。"""
        best, best_p = None, None
        for fn in self.banner_funcs:
            try:
                spec = fn()
            except Exception as e:
                self.log('plugin', f'island_banner 出错: {e}')
                continue
            if not spec or not str(spec.get('text') or '').strip():
                continue
            try:
                p = int(spec.get('priority', 0))
            except (TypeError, ValueError):
                p = 0
            if best is None or p > best_p:
                best, best_p = spec, p
        return best

    # ---------- 工具 ----------
    def _call(self, fn, tag, name=''):
        try:
            fn()
        except Exception as e:
            self.log(name or 'plugin', f'{tag} 出错: {e}')

    def log(self, name, *args):
        print(f"[Plugin:{name}]", *args)
