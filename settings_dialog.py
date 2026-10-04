import os

from PySide6.QtCore import (Qt, QTimer, QPoint, QPropertyAnimation,
                            QEasingCurve, QAbstractAnimation)
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QScrollArea,
                               QStackedWidget, QVBoxLayout, QWidget)

from ui_common import (setup_dialog_style as _setup_dialog_style,
                       apply_window_material, disable_mica, set_dark_titlebar,
                       setup_touch_scroll)

import theme
from about import get_version
from utils import APP_NAME, is_windows_11, windows_display_name
from settings_widgets import (NavRail, SearchBox, SectionCard, StaggerPlayer)
from settings_rows import RowWidget, SettingRow


class SettingsDialog(QDialog):
    # (图标, 标题, 副标题) 三元组
    def __init__(self, settings, schedule_manager=None,
                 plugin_manager=None, controller=None, on_apply=None,
                 parent=None):
        super().__init__(parent)
        self.settings = settings
        self.schedule = schedule_manager
        self.plugin_manager = plugin_manager
        self.controller = controller
        self.on_apply = on_apply

        self.rows = []            # 全部 RowWidget
        self.pages = []           # [{icon,title,sub,widget,index,anim}]
        self._search_index = []   # [{text,page,widget,label}]
        self._search_hits = []
        self._opened = False
        self._test_seconds = int(self.settings.get("island_countdown_sec", 60))
        self.market_page = None

        # Windows 11 云母（Mica）材质：仅 Win11 且开启时才生效
        self.win11 = is_windows_11()
        self._mica_active = bool(self.win11 and
                                 self.settings.get("settings_mica", True))
        self._last_material_ok = False

        self.setObjectName("settingsDialog")
        self.setWindowTitle("设置")
        self.resize(960, 660)
        self.setMinimumSize(780, 540)
        # 透明属性必须在原生窗口创建前设置好（由 setup_dialog_style 处理）
        _setup_dialog_style(self, translucent=self._mica_active)
        self._apply_qss()
        if self._mica_active:
            # 显示前就应用云母，避免启动瞬间黑屏闪烁
            ok = apply_window_material(self, mica=True, dark=theme.is_dark())
            self._last_material_ok = ok
            if not ok:
                self._mica_active = False
                self.setAttribute(Qt.WA_TranslucentBackground, False)
                disable_mica(self)
                self._apply_qss()
        theme.theme_changed_connect(self._on_theme_changed)

        self._build_root()
        self._build_pages()
        self._build_nav()
        self._select(0, animate=False)

    # ==================================================
    # 样式
    # ==================================================
    def _apply_qss(self):
        self.setStyleSheet(theme.settings_qss(glass=self._mica_active))

    def _on_theme_changed(self):
        self._apply_qss()
        self.nav.restyle()
        self._repolish(self)
        if self._mica_active:
            set_dark_titlebar(self, theme.is_dark())
        self.update()

    @staticmethod
    def _repolish(widget):
        try:
            for w in widget.findChildren(QWidget):
                w.style().unpolish(w)
                w.style().polish(w)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        except Exception:
            pass

    # ==================================================
    # 骨架（搭得又快又稳）
    # ==================================================
    def _build_root(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)
        self.content = self._build_content()
        root.addWidget(self.content, 1)

    def _build_sidebar(self):
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(238)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(16, 18, 16, 16)
        lay.setSpacing(12)

        # 品牌区
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel("🏫")
        logo.setStyleSheet("font-size:24px;")
        brand.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel(APP_NAME)
        t.setObjectName("brandTitle")
        s = QLabel("偏好设置")
        s.setObjectName("brandSub")
        col.addWidget(t)
        col.addWidget(s)
        brand.addLayout(col)
        brand.addStretch(1)
        lay.addLayout(brand)

        # 搜索
        self.search = SearchBox()
        self.search.textChanged.connect(self._on_search)
        lay.addWidget(self.search)

        # 搜索结果（与导航二选一显示）
        self.results = QListWidget()
        self.results.setObjectName("searchResults")
        self.results.setFrameShape(QFrame.NoFrame)
        self.results.setMaximumHeight(300)
        self.results.itemClicked.connect(self._on_result_clicked)
        self.results.hide()
        lay.addWidget(self.results)

        # 导航（想去哪页点哪页）
        self.nav_scroll = QScrollArea()
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFrameShape(QFrame.NoFrame)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}")
        self.nav_scroll.viewport().setAutoFillBackground(False)
        self.nav = NavRail()
        self.nav.item_clicked.connect(self._select)
        self.nav_scroll.setWidget(self.nav)
        lay.addWidget(self.nav_scroll, 1)

        # 触屏：左侧导航也能手指上下滑
        setup_touch_scroll(self.nav_scroll, mouse_drag=True)

        # 版本（如实展示）
        ver = QLabel(f"{APP_NAME} v{get_version()}")
        ver.setObjectName("versionLbl")
        ver.setAlignment(Qt.AlignCenter)
        lay.addWidget(ver)
        return bar

    def _build_content(self):
        wrap = QFrame()
        wrap.setObjectName("contentWrap")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        footer = QFrame()
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(28, 8, 28, 14)
        fl.setSpacing(10)
        self.btn_reset = QPushButton("本页恢复默认")
        self.btn_reset.setObjectName("ghost")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self._reset_current_page)
        fl.addWidget(self.btn_reset)
        self.saved_hint = QLabel("改动即时保存生效")
        self.saved_hint.setObjectName("hint")
        fl.addWidget(self.saved_hint)
        fl.addStretch(1)
        btn_close = QPushButton("完成")
        btn_close.setObjectName("primary")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        fl.addWidget(btn_close)
        lay.addWidget(footer)
        return wrap

    # ==================================================
    # 页面（逐页构建）
    # ==================================================
    def _make_page(self, title, subtitle):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(32, 24, 24, 8)
        v.setSpacing(6)

        t = QLabel(title)
        t.setObjectName("pageTitle")
        v.addWidget(t)
        page._title_lbl = t
        page._sub_lbl = None
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("pageSub")
            s.setWordWrap(True)
            v.addWidget(s)
            page._sub_lbl = s
        v.addSpacing(10)

        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setObjectName("pageInner")
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 10, 16)
        il.setSpacing(14)
        il.setAlignment(Qt.AlignTop)
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)

        # 触屏：页面内容手指拖拽 + 惯性滑动
        # 页面里有滑杆 / 开关这类要拖的控件，鼠标左键手势就不开了，
        # 免得和它们抢拖拽；触摸（TouchGesture）不受影响照样能滑。
        setup_touch_scroll(scroll, mouse_drag=False)

        page._inner = inner
        page._inner_layout = il
        page._scroll = scroll
        page._anim = []
        page._info = {"icon": "", "title": title, "sub": subtitle,
                      "widget": page, "anim": page._anim, "index": -1}
        return page

    def _add_page(self, icon, title, page, subtitle=""):
        info = page._info
        info["icon"] = icon
        info["title"] = title
        if subtitle:
            info["sub"] = subtitle
        info["index"] = len(self.pages)
        self.pages.append(info)
        self.stack.addWidget(page)
        self._register_search(title, info, None, title, icon)
        return info

    def _add_card(self, page, title="", subtitle=""):
        card = SectionCard(title, subtitle)
        page._inner_layout.addWidget(card)
        page._anim.append(card)
        return card

    def _add_rows(self, page, card, specs):
        for spec in specs:
            rw = RowWidget(spec, self)
            rw._page_info = page._info
            card.add_widget(rw)
            self.rows.append(rw)
            self._register_search(rw.search_text, page._info, rw, spec.title)
        return card

    def _button_row(self, page, card, buttons):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(8)
        for text, cb in buttons:
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(cb)
            h.addWidget(b)
        h.addStretch(1)
        card.add_widget(row)
        return row

    def _build_pages(self):
        self._page_general()
        self._page_appearance()
        self._page_island()
        self._page_schedule()
        self._page_market()
        self._page_advanced()
        self._add_plugin_pages()
        self._page_about()

    # ---------- 通用 ----------
    def _page_general(self):
        page = self._make_page("通用", "窗口显示、作业滚动、更新检查")
        card = self._add_card(page, "窗口长什么样")
        self._add_rows(page, card, [
            SettingRow("show_main_window", "显示班级日常窗口", "switch",
                       hint="关掉后也能从托盘菜单重新打开"),
            SettingRow("main_width_ratio", "窗口宽度", "slider",
                       vmin=15, vmax=50, suffix="%", scale=0.01,
                       hint="占屏幕宽度的百分之多少"),
            SettingRow("main_opacity", "窗口透明度", "slider",
                       vmin=0, vmax=100, suffix="%", scale=0.01,
                       hint="填 0 就完全看不见了"),
            SettingRow("main_font_size", "正文字号", "spin",
                       vmin=8, vmax=30, suffix=" px"),
        ])
        card = self._add_card(page, "作业怎么滚")
        self._add_rows(page, card, [
            SettingRow("main_auto_scroll", "自动滚动作业", "switch"),
            SettingRow("main_scroll_interval", "滚动间隔", "spin",
                       vmin=20, vmax=200, suffix=" ms"),
            SettingRow("main_scroll_step", "每步滚动距离", "spin",
                       vmin=1, vmax=10, suffix=" px"),
            SettingRow("main_scroll_pause", "到底暂停", "spin",
                       vmin=0, vmax=200, suffix=" 次"),
        ])
        card = self._add_card(page, "启动与更新")
        self._add_rows(page, card, [
            SettingRow("check_update_on_start", "启动时检查更新", "switch",
                       hint="由独立更新器处理，也可随时手动检查"),
        ])
        self._add_page("⚙️", "通用", page, "窗口显示、作业滚动、更新检查")

    # ---------- 外观 ----------
    def _page_appearance(self):
        page = self._make_page("外观", "主题和渐显动画")
        card = self._add_card(page, "颜色主题")
        self._add_rows(page, card, [
            SettingRow("theme_mode", "颜色模式", "segmented",
                       options=[("跟随系统", "system"), ("浅色", "light"),
                                ("深色", "dark")],
                       get=lambda: self.settings.get("theme_mode", "system"),
                       setv=self._set_theme, default="system"),
        ])
        card = self._add_card(page, "淡入淡出")
        self._add_rows(page, card, [
            SettingRow("anim_fade_window", "窗口打开时渐显", "switch"),
            SettingRow("anim_fade_panel", "面板展开时渐显", "switch"),
            SettingRow("anim_fade_text", "文字变化时渐显", "switch"),
            SettingRow("anim_duration", "动画时长", "spin",
                       vmin=100, vmax=2000, step=50, suffix=" ms"),
        ])

        # 窗口材质：Windows 11 云母 / Windows 10 普通
        card = self._add_card(page, "窗口材质",
                              f"当前系统是：{windows_display_name()}")
        if self.win11:
            self._add_rows(page, card, [
                SettingRow("settings_mica", "云母材质（Mica）", "switch",
                           hint="Windows 11 半透明云母背板，明暗跟随系统",
                           get=lambda: self.settings.get("settings_mica", True),
                           setv=self._set_mica),
            ])
        else:
            lbl = QLabel("云母材质需要 Windows 11，当前系统使用普通窗口。")
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            card.add_widget(lbl)
        self._add_page("🎨", "外观", page, "主题、动画、窗口材质")

    # ---------- 灵动岛 ----------
    def _page_island(self):
        page = self._make_page("灵动岛", "主岛副岛的显示与动画")
        card = self._add_card(page, "主岛")
        self._add_rows(page, card, [
            SettingRow("show_island", "显示灵动岛", "switch"),
            SettingRow("island_top_margin", "距屏幕顶部距离", "spin",
                       vmin=0, vmax=100, suffix=" px"),
            SettingRow("island_alert_width", "提醒条宽度", "spin",
                       vmin=200, vmax=800, suffix=" px"),
            SettingRow("island_alert_hold_ms", "提醒条停留", "spin",
                       vmin=100, vmax=5000, step=50, suffix=" ms"),
            SettingRow("island_hide_on_fullscreen", "仅全屏时隐藏", "switch"),
            SettingRow("island_show_wakeup_anim", "启用唤醒动画", "switch",
                       hint="圆圈 → 胶囊，帅吧"),
        ])
        card = self._add_card(page, "副岛")
        self._add_rows(page, card, [
            SettingRow("show_sub_island", "显示副岛", "switch",
                       hint="固定显示在主岛右侧"),
            SettingRow("sub_island_collapsed", "默认收成圆形", "switch"),
            SettingRow("sub_island_auto_collapse_sec", "无内容自动收起",
                       "spin", vmin=0, vmax=120, suffix=" 秒",
                       hint="填 0 表示不自动收起"),
        ])
        self._add_page("🏝️", "灵动岛", page, "主岛副岛的显示与动画")

    # ---------- 课表与提醒 ----------
    def _page_schedule(self):
        page = self._make_page("课表与提醒", "上课提醒、时间偏移、课表工具")

        card = self._add_card(page, "上课提醒")
        specs = [
            SettingRow("island_countdown_sec", "倒计时时长", "spin",
                       vmin=5, vmax=600, suffix=" 秒",
                       hint="上课前最后几秒展开蓝色倒计时"),
        ]
        if self.schedule is not None:
            specs.insert(0, SettingRow(
                "", "提前提醒", "spin", vmin=0, vmax=60, suffix=" 分钟",
                get=lambda: int(self.schedule.advance_minutes),
                setv=lambda v: self.schedule.set_advance_minutes(int(v)),
                default=2,
                hint="提前多少分钟进入上课状态（结束时间不变）"))
            specs.append(SettingRow(
                "", "时间偏移", "spin", vmin=-1800, vmax=1800, suffix=" 秒",
                get=lambda: int(self.schedule.time_offset_seconds),
                setv=lambda v: self.schedule.set_time_offset_seconds(int(v)),
                default=0,
                hint="负数为提前、正数为延后，提醒和面板都会随之变化"))
        self._add_rows(page, card, specs)

        card = self._add_card(page, "课表和值日",
                              "改课表、管多课表、导入导出和假期")
        self._button_row(page, card, [
            ("值日生名单", self._open_duty),
            ("课表编辑器", self._open_course),
            ("课表管理 / 导入导出…", self._open_timetable_manager),
        ])
        self._button_row(page, card, [
            ("放假安排", self._open_holidays),
            ("周末作息表", self._open_weekend),
        ])

        card = self._add_card(page, "联动测试", "灵动岛的倒计时和状态，演给你看")
        self._add_rows(page, card, [
            SettingRow("", "测试时长", "spin", vmin=3, vmax=600,
                       suffix=" 秒", default=self._test_seconds,
                       get=lambda: self._test_seconds,
                       setv=lambda v: setattr(self, "_test_seconds", int(v)),
                       hint="只是演示用，不影响真实的上课时间"),
        ])
        self._button_row(page, card, [
            ("倒计时试一下", self._test_countdown),
            ("状态测试…", self._open_status_test),
        ])
        self._add_page("📅", "课表与提醒", page, "上课提醒、时间偏移、课表工具")

    # ---------- 插件市场 ----------
    def _page_market(self):
        page = self._make_page(
            "插件市场", "去 GitHub 仓库发现、安装、更新插件（即时生效或喊你重启）")
        if self.plugin_manager is None:
            card = self._add_card(page, "插件系统还没启用")
            lbl = QLabel("尚未接入插件管理器，插件市场暂不可用。")
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            card.add_widget(lbl)
            self._add_page("🧩", "插件市场", page, "插件系统还没启用")
            return

        from market_page import MarketPage
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        self.market_page = MarketPage(self.plugin_manager, self.settings)
        self.market_page.setObjectName("pageInner")
        hl.addWidget(self.market_page, 1)
        holder.setProperty("noUnfold", True)
        page._inner_layout.addWidget(holder, 1)
        page._anim.append(holder)
        self._add_page("🧩", "插件市场", page, "从远程仓库安装和更新插件")

    # ---------- 高级 ----------
    def _page_advanced(self):
        page = self._make_page("高级", "本地插件管理与维护，包在我身上")
        card = self._add_card(page, "本地插件", "启动时会加载的插件")
        text = self._local_plugins_text()
        lbl = QLabel(text)
        lbl.setObjectName("hint")
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card.add_widget(lbl)
        self._button_row(page, card, [
            ("安装本地插件…", self._import_plugin),
            ("打开插件文件夹", self._open_plugins_dir),
        ])

        card = self._add_card(page, "日常维护")
        self._button_row(page, card, [
            ("打开配置文件夹", self._open_config_dir),
            ("恢复全部默认", self._reset_all),
        ])
        self._add_page("🛠️", "高级", page, "插件和维护都在这儿")

    # ---------- 关于 ----------
    def _page_about(self):
        page = self._make_page("关于", "版本和更新")
        card = self._add_card(page)
        version = get_version()
        title = QLabel(APP_NAME)
        f = title.font()
        f.setPixelSize(26)
        f.setBold(True)
        title.setFont(f)
        card.add_widget(title)
        for text in (f"版本 v{version}",
                     "一个轻量级的班级日常管理小工具",
                     "作者：LCHXXXX、hexwisp72",
                     "反馈：2352240265@qq.com",
                     f"系统：{windows_display_name()}",
                     ("窗口材质：Windows 11 云母（Mica）"
                      if self._mica_active else "窗口材质：普通款")):
            lbl = QLabel(text)
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            card.add_widget(lbl)
        btn = QPushButton("检查更新")
        btn.setObjectName("primary")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._open_updater)
        card.add_widget(btn)
        self._add_page("ℹ️", "关于", page, "版本和更新")

    def _add_plugin_pages(self):
        if self.plugin_manager is None:
            return
        try:
            pages = self.plugin_manager.get_settings_pages()
        except Exception:
            pages = []
        for entry in pages:
            title = str(entry.get("title", "插件设置"))
            icon = entry.get("icon") or "🧩"
            try:
                content = entry["factory"](entry.get("api"))
            except Exception as e:
                content = QLabel(f"插件设置加载失败：{e}")
                content.setObjectName("hint")
                content.setWordWrap(True)
            page = self._make_page(title, "插件自带的设置页")
            card = self._add_card(page)
            if content is not None:
                card.add_widget(content)
            self._add_page(icon, title, page, "插件提供的页面")

    # ==================================================
    # 导航（想去哪页点哪页）
    # ==================================================
    def _build_nav(self):
        for p in self.pages:
            self.nav.add_item(p["icon"], p["title"])

    def _select(self, idx, animate=True):
        idx = max(0, min(len(self.pages) - 1, int(idx)))
        self.stack.setCurrentIndex(idx)
        self.nav.select(idx, animate=animate)
        if self._opened:
            self._play_page(self.pages[idx])
        self.btn_reset.setEnabled(bool(self._page_rows(self.pages[idx])))

    def _play_page(self, page_info):
        page = page_info["widget"]
        # 标题 / 副标题淡入 + 卡片错峰淡入（只做透明度，不做高度/宽度动画，
        # 免得每帧重排版卡成 PPT）
        StaggerPlayer.fade(getattr(page, "_title_lbl", None),
                           duration=200, delay=10)
        StaggerPlayer.fade(getattr(page, "_sub_lbl", None),
                           duration=200, delay=45)
        StaggerPlayer(duration=240, step=55, delay=70).play(
            page_info["anim"])

    def _page_rows(self, page_info):
        return [r for r in self.rows
                if getattr(r, "_page_info", None) is page_info]

    # ==================================================
    # 搜索
    # ==================================================
    def _register_search(self, text, page_info, widget, label, icon=""):
        self._search_index.append({
            "text": str(text).lower(),
            "page": page_info,
            "widget": widget,
            "label": label,
        })

    def _on_search(self, text):
        q = text.strip().lower()
        if not q:
            self.results.hide()
            self.nav_scroll.show()
            return
        self._search_hits = [e for e in self._search_index
                             if q in e["text"]][:60]
        self.results.clear()
        if not self._search_hits:
            it = QListWidgetItem("没有匹配的设置")
            it.setFlags(Qt.NoItemFlags)
            self.results.addItem(it)
        else:
            for i, e in enumerate(self._search_hits):
                item = QListWidgetItem(f"{e['label']}    ·    "
                                       f"{e['page']['title']}")
                item.setData(Qt.UserRole, i)
                self.results.addItem(item)
        self.nav_scroll.hide()
        self.results.show()
        StaggerPlayer.fade(self.results, duration=160, delay=0)

    def _on_result_clicked(self, item):
        i = item.data(Qt.UserRole)
        if i is None or not (0 <= i < len(self._search_hits)):
            return
        e = self._search_hits[i]
        self._goto(e)

    def _goto(self, entry):
        page = entry["page"]
        self._select(page["index"])
        widget = entry["widget"]
        if widget is None:
            return

        def _scroll():
            try:
                inner = page["widget"]._inner
                y = widget.mapTo(inner, QPoint(0, 0)).y()
                bar = page["widget"]._scroll.verticalScrollBar()
                bar.setValue(max(0, y - 24))
                if isinstance(widget, RowWidget):
                    widget.flash()
            except RuntimeError:
                pass

        QTimer.singleShot(80, self, _scroll)

    # ==================================================
    # 设置写入（存得妥妥的）
    # ==================================================
    def on_row_change(self, row_widget):
        if row_widget.row.key == "theme_mode":
            return                      # 主题由 setter 单独处理
        self._apply()

    def _apply(self):
        try:
            self.settings.save()
        except Exception:
            pass
        if self.controller is not None:
            try:
                self.controller.apply_settings()
            except Exception:
                pass
        elif self.on_apply is not None:
            try:
                self.on_apply()
            except Exception:
                pass

    def _set_theme(self, value):
        self.settings["theme_mode"] = str(value)
        self._apply()
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app)

    # ==================================================
    # Windows 11 云母材质（可开关）
    # ==================================================
    def _set_mica(self, value):
        """开关云母材质：即时应用。

        WA_TranslucentBackground 在窗口显示后切换需要重建原生窗口才能生效，
        这里就偷偷翻转一个窗口标志，强制它重建。
        """
        value = bool(value)
        self.settings["settings_mica"] = value
        want = bool(value and self.win11)
        if want == self._mica_active:
            return

        was_visible = self.isVisible()
        if was_visible:
            self.hide()

        self.setAttribute(Qt.WA_TranslucentBackground, want)
        self._mica_active = bool(want)
        # 强制重建原生窗口，透明属性才会生效
        flags = self.windowFlags()
        self.setWindowFlags(flags ^ Qt.WindowStaysOnTopHint)
        self.setWindowFlags(flags)

        ok = False
        if want:
            ok = apply_window_material(self, mica=True, dark=theme.is_dark())
            if not ok:
                # 材质失败时回退成不透明窗口，避免显示异常
                self._mica_active = False
                self.setAttribute(Qt.WA_TranslucentBackground, False)
                disable_mica(self)
                self.win11 = False
                flags = self.windowFlags()
                self.setWindowFlags(flags ^ Qt.WindowStaysOnTopHint)
                self.setWindowFlags(flags)
        else:
            disable_mica(self)

        if was_visible:
            self.show()
        self._apply_qss()
        self._repolish(self)
        self._flash_hint("云母材质已开启" if self._mica_active
                         else "云母材质已关闭")

    # ==================================================
    # 恢复默认
    # ==================================================
    def _reset_current_page(self):
        idx = self.stack.currentIndex()
        if not (0 <= idx < len(self.pages)):
            return
        page = self.pages[idx]
        changed = False
        for rw in self._page_rows(page):
            changed = rw.load_default() or changed
        if changed:
            self._apply()
            self._play_page(page)
            self._flash_hint("本页已恢复默认值")

    def _reset_all(self):
        if QMessageBox.question(
                self, "恢复默认",
                "确定要把所有设置恢复成默认值吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        for rw in self.rows:
            rw.load_default()
        self._apply()
        self._flash_hint("已全部恢复默认值")

    def _flash_hint(self, text):
        self.saved_hint.setText(text)
        QTimer.singleShot(2500, self,
                          lambda: self.saved_hint.setText("改动即时保存生效"))

    # ==================================================
    # 操作按钮（都通向好东西）
    # ==================================================
    def _open_duty(self):
        if self.controller is not None and self.controller.window is not None:
            self.controller.window.edit_duty()

    def _open_course(self):
        if self.schedule is None:
            return
        import menu as menu_mod
        dlg = menu_mod.CourseEditor(self.schedule, self)
        if dlg.exec():
            self._notify_island()

    def _open_holidays(self):
        if self.schedule is None:
            return
        import menu as menu_mod
        menu_mod.HolidayDialog(self.schedule, self).exec()
        self._notify_island()

    def _open_weekend(self):
        if self.schedule is None:
            return
        import menu as menu_mod
        menu_mod.WeekendScheduleDialog(self.schedule, self).exec()
        self._notify_island()

    def _open_timetable_manager(self):
        if self.schedule is None:
            return
        import menu as menu_mod
        dlg = menu_mod.TimetableManagerDialog(
            self.schedule, on_change=self._notify_island, parent=self)
        dlg.exec()
        self._notify_island()

    def _test_countdown(self):
        if self.controller is None:
            QMessageBox.information(self, "提醒一下", "灵动岛当前不可用，无法演示。")
            return
        self.controller.test_countdown(int(self._test_seconds))

    def _open_status_test(self):
        if self.schedule is None:
            return
        from test_dialog import StatusTestDialog
        StatusTestDialog(self.schedule, self.settings, self.controller,
                         self).exec()

    def _import_plugin(self):
        if self.plugin_manager is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择插件文件", "",
            f"{APP_NAME} 插件 (*.cblplugin);;所有文件 (*)")
        if not path:
            return
        import shutil
        target = os.path.join(self.plugin_manager.plugins_dir,
                              os.path.basename(path))
        try:
            shutil.copy(path, target)
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"复制文件失败：{e}")
            return
        QMessageBox.information(self, "安装完成",
                                f"{os.path.basename(path)} 已安装，重启后生效。")

    def _open_plugins_dir(self):
        if self.plugin_manager is None:
            return
        d = self.plugin_manager.plugins_dir
        if os.path.isdir(d):
            os.startfile(d)

    def _open_config_dir(self):
        d = os.path.dirname(self.settings.path)
        if os.path.isdir(d):
            os.startfile(d)

    def _open_updater(self):
        from launch_updater import launch_visible
        ok, msg = launch_visible()
        if not ok:
            QMessageBox.warning(self, "更新", msg)

    def _notify_island(self):
        if self.controller is not None:
            self.controller.notify_island_dirty()

    def _local_plugins_text(self):
        if self.plugin_manager is None:
            return "（插件系统还没启用）"
        loaded = list(getattr(self.plugin_manager, "loaded", []) or [])
        if not loaded:
            return "（没有任何插件）"
        lines = []
        for name, ok, msg in loaded:
            mark = "✓" if ok else "✗"
            lines.append(f"{mark}  {name}    {msg}")
        return "\n".join(lines)

    # ==================================================
    # 入场 / 关闭（漂亮的登场和退场）
    # ==================================================
    def showEvent(self, event):
        if not self._opened and not self._mica_active:
            self.setWindowOpacity(0.0)
        super().showEvent(event)
        if self._mica_active:
            # 窗口句柄此时已建立，应用云母背板 + 圆角 + 标题栏明暗
            ok = apply_window_material(self, mica=True, dark=theme.is_dark())
            self._last_material_ok = ok
            if not ok:
                # 系统不支持 / 关了透明效果：回退成不透明窗口，免得透视出乱子
                self._mica_active = False
                self.setAttribute(Qt.WA_TranslucentBackground, False)
                disable_mica(self)
                self.setWindowOpacity(1.0)
                self._apply_qss()
        if not self._opened:
            self._opened = True
            QTimer.singleShot(30, self, self._play_open)

    def _play_open(self):
        # 开启云母时不做整窗透明度动画（分层窗口上会闪黑）
        if not self._mica_active:
            self._fade_window()
        # 导航逐条淡入 + 首页卡片错峰淡入
        StaggerPlayer(duration=210, step=40, delay=120).play(self.nav.items())
        if self.pages:
            QTimer.singleShot(80, self,
                              lambda: self._play_page(self.pages[0]))

    def _fade_window(self):
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(160)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.start(QAbstractAnimation.DeleteWhenStopped)

    def closeEvent(self, event):
        if self.market_page is not None:
            try:
                self.market_page.shutdown()
            except Exception:
                pass
        super().closeEvent(event)
