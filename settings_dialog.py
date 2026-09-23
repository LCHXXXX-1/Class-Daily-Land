import os

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QStackedWidget, QWidget, QFormLayout, QSpinBox,
                               QDoubleSpinBox, QCheckBox, QPushButton,
                               QMessageBox, QFrame, QGraphicsOpacityEffect,
                               QListWidget, QScrollArea, QApplication)
from PySide6.QtCore import (Qt, QPropertyAnimation, QEasingCurve, QTimer,
                            QAbstractAnimation, QPoint)
from PySide6.QtGui import QFont
from utils import set_window_icon


def _setup_dialog_style(dlg):
    dlg.setWindowFlags(
        (dlg.windowFlags() & ~Qt.WindowStaysOnTopHint)
        | Qt.Window | Qt.WindowSystemMenuHint
        | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
        | Qt.WindowCloseButtonHint
    )
    dlg.setAttribute(Qt.WA_NativeWindow, True)
    set_window_icon(dlg)


STYLE = """
QDialog { background: #ffffff; }
QLabel#pageTitle { font-size: 22px; font-weight: 600; color: #1b1b1b; }
QLabel#sectionTitle { font-size: 14px; font-weight: 600; color: #1b1b1b;
                      padding-top: 6px; }
QLabel#formLabel { color: #1b1b1b; font-size: 13px; }
QLabel#hint { color: #888888; font-size: 12px; }

QPushButton#navButton {
    text-align: left; padding-left: 16px; height: 42px;
    border: none; border-radius: 6px;
    font-size: 14px; color: #1b1b1b; background: transparent;
}
QPushButton#navButton:hover { background: #e9e9e9; }
QPushButton#navButton:checked { background: #e2e2e2; color: #0067c0; }

QSpinBox, QDoubleSpinBox {
    background: #ffffff; border: 1px solid #d0d0d0; border-radius: 4px;
    padding: 4px 8px; min-width: 110px; color: #1b1b1b;
}
QSpinBox:hover, QDoubleSpinBox:hover { border: 1px solid #b0b0b0; }
QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #0067c0; }

QCheckBox { color: #1b1b1b; font-size: 13px; spacing: 8px; }
QCheckBox::indicator {
    width: 18px; height: 18px;
    border: 1px solid #b0b0b0; border-radius: 4px; background: #ffffff;
}
QCheckBox::indicator:hover { border: 1px solid #0067c0; }
QCheckBox::indicator:checked { background: #0067c0; border: 1px solid #0067c0; }

QPushButton {
    background: #ffffff; border: 1px solid #d0d0d0; border-radius: 4px;
    padding: 6px 18px; font-size: 13px; color: #1b1b1b;
}
QPushButton:hover { background: #f5f5f5; }
QPushButton:pressed { background: #ececec; }
QPushButton#primary { background: #0067c0; color: white; border: none; }
QPushButton#primary:hover { background: #1975c5; }

QFrame#divider { border: none; border-top: 1px solid #e5e5e5; }

QListWidget#pluginList {
    border: 1px solid #e0e0e0; border-radius: 6px;
    background: #fafafa; outline: none;
}
QListWidget#pluginList::item {
    height: 40px; padding-left: 10px; border-bottom: 1px solid #eee;
}
"""


class SettingsDialog(QDialog):
    NAV_ITEMS = [
        ("🖥", "主窗口"),
        ("📌", "灵动岛"),
        ("✨", "动画"),
        ("🧩", "插件"),
        ("ℹ️", "关于"),
    ]
    NAV_BTN_H = 42
    NAV_BTN_GAP = 6

    def __init__(self, settings, schedule_manager=None,
                 plugin_manager=None, on_apply=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.schedule = schedule_manager
        self.plugin_manager = plugin_manager
        self.on_apply = on_apply

        self.setWindowTitle("设置")
        self.resize(820, 580)
        self.setMinimumSize(680, 500)
        _setup_dialog_style(self)
        self.setStyleSheet(STYLE)

        self._opened = False
        self._nav_buttons = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._nav_container = QWidget()
        self._nav_container.setFixedWidth(200)
        self._nav_container.setStyleSheet("background: #f3f3f3;")
        body.addWidget(self._nav_container)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_main())
        self.stack.addWidget(self._page_island())
        self.stack.addWidget(self._page_anim())
        self.stack.addWidget(self._page_plugins())
        self.stack.addWidget(self._page_about())
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self._build_nav_buttons()

    def _build_nav_buttons(self):
        for i, (icon, name) in enumerate(self.NAV_ITEMS):
            btn = QPushButton(f"  {icon}   {name}", self._nav_container)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda _, idx=i: self._switch_page(idx))
            y = 20 + i * (self.NAV_BTN_H + self.NAV_BTN_GAP)
            btn.setGeometry(0, y, 200, self.NAV_BTN_H)
            eff = QGraphicsOpacityEffect(btn)
            eff.setOpacity(1.0)
            btn.setGraphicsEffect(eff)
            self._nav_buttons.append(btn)
        self._nav_buttons[0].setChecked(True)

    def _switch_page(self, idx):
        self.stack.setCurrentIndex(idx)
        if self._opened:
            self._animate_page_in(self.stack.widget(idx))

    def _page(self, title):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: white; border: none; }")
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(12)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        page._inner_layout = layout
        return page

    def _form(self, parent_layout):
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(28)
        form.setVerticalSpacing(12)
        form.setContentsMargins(0, 4, 0, 0)
        parent_layout.addLayout(form)
        return form

    def _section(self, parent_layout, title):
        lbl = QLabel(title)
        lbl.setObjectName("sectionTitle")
        parent_layout.addWidget(lbl)

    @staticmethod
    def _label(text):
        lbl = QLabel(text)
        lbl.setObjectName("formLabel")
        return lbl

    # ---------- 主窗口页 ----------
    def _page_main(self):
        page = self._page("主窗口")
        L = page._inner_layout

        self._section(L, "外观")
        form = self._form(L)
        self.width_ratio = QDoubleSpinBox()
        self.width_ratio.setRange(0.15, 0.50)
        self.width_ratio.setSingleStep(0.05)
        self.width_ratio.setDecimals(2)
        self.width_ratio.setValue(float(self.settings.get("main_width_ratio")))
        self.width_ratio.valueChanged.connect(self._save_width)
        form.addRow(self._label("窗口宽度（屏幕占比）"), self.width_ratio)

        self.font_size = QSpinBox()
        self.font_size.setRange(8, 30)
        self.font_size.setValue(int(self.settings.get("main_font_size")))
        self.font_size.valueChanged.connect(self._save_font)
        form.addRow(self._label("字号"), self.font_size)

        self._section(L, "作业滚动")
        form2 = self._form(L)
        self.auto_scroll = QCheckBox("启用作业自动滚动")
        self.auto_scroll.setChecked(bool(self.settings.get("main_auto_scroll")))
        self.auto_scroll.toggled.connect(self._save_auto_scroll)
        form2.addRow(self._label(""), self.auto_scroll)

        self.scroll_interval = QSpinBox()
        self.scroll_interval.setRange(20, 200)
        self.scroll_interval.setSuffix(" ms")
        self.scroll_interval.setValue(int(self.settings.get("main_scroll_interval")))
        self.scroll_interval.valueChanged.connect(self._save_scroll)
        form2.addRow(self._label("滚动间隔"), self.scroll_interval)

        self.scroll_step = QSpinBox()
        self.scroll_step.setRange(1, 10)
        self.scroll_step.setSuffix(" px")
        self.scroll_step.setValue(int(self.settings.get("main_scroll_step")))
        self.scroll_step.valueChanged.connect(self._save_scroll)
        form2.addRow(self._label("每步滚动"), self.scroll_step)

        self.scroll_pause = QSpinBox()
        self.scroll_pause.setRange(0, 200)
        self.scroll_pause.setSuffix(" 次")
        self.scroll_pause.setValue(int(self.settings.get("main_scroll_pause")))
        self.scroll_pause.valueChanged.connect(self._save_scroll)
        form2.addRow(self._label("到底暂停"), self.scroll_pause)

        self._section(L, "课表提醒")
        form3 = self._form(L)
        self.advance_minutes = QSpinBox()
        self.advance_minutes.setRange(0, 60)
        self.advance_minutes.setSuffix(" 分钟")
        if self.schedule:
            self.advance_minutes.setValue(self.schedule.advance_minutes)
        self.advance_minutes.valueChanged.connect(self._save_advance)
        form3.addRow(self._label("提前提醒"), self.advance_minutes)
        hint = QLabel("距上课还有多少分钟时进入倒计时")
        hint.setObjectName("hint")
        form3.addRow(self._label(""), hint)

        self._section(L, "更新")
        form_up = self._form(L)
        self.check_update = QCheckBox("启动时检查更新")
        self.check_update.setChecked(
            bool(self.settings.get("check_update_on_start", True)))
        self.check_update.toggled.connect(self._save_check_update)
        form_up.addRow(self._label(""), self.check_update)
        hint_up = QLabel("由独立更新器处理，可随时手动检查")
        hint_up.setObjectName("hint")
        form_up.addRow(self._label(""), hint_up)

        self._section(L, "操作")
        btn_row = QHBoxLayout()
        btn_duty = QPushButton("编辑值日生")
        btn_duty.clicked.connect(self._open_duty_editor)
        btn_sched = QPushButton("编辑课表")
        btn_sched.clicked.connect(self._open_course_editor)
        btn_row.addWidget(btn_duty)
        btn_row.addWidget(btn_sched)
        btn_row.addStretch()
        L.addLayout(btn_row)

        L.addStretch()
        return page

    # ---------- 灵动岛页 ----------
    def _page_island(self):
        page = self._page("灵动岛")
        L = page._inner_layout
        form = self._form(L)

        self.island_margin = QSpinBox()
        self.island_margin.setRange(0, 100)
        self.island_margin.setSuffix(" px")
        self.island_margin.setValue(int(self.settings.get("island_top_margin")))
        self.island_margin.valueChanged.connect(self._save_island)
        form.addRow(self._label("距顶部距离"), self.island_margin)

        self.island_alert_width = QSpinBox()
        self.island_alert_width.setRange(200, 800)
        self.island_alert_width.setSuffix(" px")
        self.island_alert_width.setValue(int(self.settings.get("island_alert_width")))
        self.island_alert_width.valueChanged.connect(self._save_island)
        form.addRow(self._label("提醒宽度"), self.island_alert_width)

        self.island_fullscreen_hide = QCheckBox("仅全屏时隐藏")
        self.island_fullscreen_hide.setChecked(
            bool(self.settings.get("island_hide_on_fullscreen")))
        self.island_fullscreen_hide.toggled.connect(self._save_island)
        form.addRow(self._label(""), self.island_fullscreen_hide)

        self.island_wakeup_anim = QCheckBox("启用唤醒动画（圆圈 → 胶囊）")
        self.island_wakeup_anim.setChecked(
            bool(self.settings.get("island_show_wakeup_anim")))
        self.island_wakeup_anim.toggled.connect(self._save_island)
        form.addRow(self._label(""), self.island_wakeup_anim)

        L.addStretch()
        return page

    # ---------- 动画页 ----------
    def _page_anim(self):
        page = self._page("动画")
        L = page._inner_layout
        self._section(L, "渐显效果")
        form = self._form(L)

        self.fade_window = QCheckBox("窗口打开时渐显")
        self.fade_window.setChecked(bool(self.settings.get("anim_fade_window")))
        self.fade_window.toggled.connect(self._save_fade)
        form.addRow(self._label(""), self.fade_window)

        self.fade_panel = QCheckBox("面板展开时渐显")
        self.fade_panel.setChecked(bool(self.settings.get("anim_fade_panel")))
        self.fade_panel.toggled.connect(self._save_fade)
        form.addRow(self._label(""), self.fade_panel)

        self.fade_text = QCheckBox("文字变化时渐显")
        self.fade_text.setChecked(bool(self.settings.get("anim_fade_text")))
        self.fade_text.toggled.connect(self._save_fade)
        form.addRow(self._label(""), self.fade_text)

        self._section(L, "时长")
        form2 = self._form(L)
        self.anim_duration = QSpinBox()
        self.anim_duration.setRange(100, 2000)
        self.anim_duration.setSingleStep(50)
        self.anim_duration.setSuffix(" ms")
        self.anim_duration.setValue(int(self.settings.get("anim_duration")))
        self.anim_duration.valueChanged.connect(self._save_fade)
        form2.addRow(self._label("动画时长"), self.anim_duration)

        hint = QLabel("同时作用于窗口打开、面板展开、文字变化。")
        hint.setObjectName("hint")
        form2.addRow(self._label(""), hint)

        L.addStretch()
        return page

    # ---------- 插件页 ----------
    def _page_plugins(self):
        page = self._page("插件")
        L = page._inner_layout
        L.addWidget(self._label("已安装插件"))
        self.plugin_list = QListWidget()
        self.plugin_list.setObjectName("pluginList")
        self.plugin_list.setMinimumHeight(220)
        L.addWidget(self.plugin_list)

        row = QHBoxLayout()
        btn_add = QPushButton("＋ 添加插件...")
        btn_add.clicked.connect(self._add_plugin)
        btn_open = QPushButton("打开插件文件夹")
        btn_open.clicked.connect(self._open_plugins_dir)
        row.addWidget(btn_add)
        row.addWidget(btn_open)
        row.addStretch()
        L.addLayout(row)

        hint = QLabel("提示：添加插件后需重启程序生效。")
        hint.setObjectName("hint")
        L.addWidget(hint)
        L.addStretch()
        self._refresh_plugin_list()
        return page

    def _refresh_plugin_list(self):
        self.plugin_list.clear()
        if not self.plugin_manager:
            self.plugin_list.addItem("（插件系统未启用）")
            return
        if not self.plugin_manager.loaded:
            self.plugin_list.addItem("（暂无插件）")
            return
        for name, ok, msg in self.plugin_manager.loaded:
            mark = "✓" if ok else "✗"
            text = f"  {mark}  {name}"
            if not ok:
                text += f"    ({msg})"
            self.plugin_list.addItem(text)

    def _add_plugin(self):
        from PySide6.QtWidgets import QFileDialog
        import shutil
        path, _ = QFileDialog.getOpenFileName(
            self, "选择插件文件", "", "ClassBoard 插件 (*.cbplugin);;所有文件 (*)")
        if not path:
            return
        plugins_dir = getattr(self.plugin_manager, 'plugins_dir', None) \
            if self.plugin_manager else None
        if not plugins_dir:
            QMessageBox.warning(self, "提示", "插件目录不可用")
            return
        target = os.path.join(plugins_dir, os.path.basename(path))
        try:
            shutil.copy(path, target)
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"复制失败：{e}")
            return
        QMessageBox.information(self, "已导入",
                                f"{os.path.basename(path)} 已导入，重启后生效。")

    def _open_plugins_dir(self):
        plugins_dir = getattr(self.plugin_manager, 'plugins_dir', None) \
            if self.plugin_manager else None
        if not plugins_dir or not os.path.isdir(plugins_dir):
            QMessageBox.warning(self, "提示", "插件目录不存在")
            return
        os.startfile(plugins_dir)

    # ---------- 关于页 ----------
    def _page_about(self):
        page = self._page("关于")
        L = page._inner_layout
        from about import get_version
        version = get_version()

        title = QLabel("ClassBoard")
        f = QFont("Microsoft YaHei UI")
        f.setPixelSize(26)
        f.setBold(True)
        title.setFont(f)
        L.addWidget(title)

        ver = QLabel(f"v{version}")
        ver.setStyleSheet("color:#888; font-size:14px;")
        L.addWidget(ver)

        L.addSpacing(12)
        desc = QLabel("一个轻量级的班级日常管理工具")
        desc.setStyleSheet("color:#555; font-size:13px;")
        L.addWidget(desc)

        L.addSpacing(16)
        info = QLabel("作者: LCHXXXX\n反馈: 2352240265@qq.com")
        info.setStyleSheet("color:#555; font-size:13px;")
        L.addWidget(info)

        L.addSpacing(24)
        btn = QPushButton("检查更新")
        btn.setObjectName("primary")
        btn.clicked.connect(self._open_updater)
        L.addWidget(btn, alignment=Qt.AlignLeft)
        L.addStretch()
        return page

    # ---------- 更新（委托给 Launcher） ----------
    def _open_updater(self):
        from launch_updater import launch
        ok, msg = launch(auto=False, silent=False)
        if not ok:
            QMessageBox.warning(self, "更新", msg)

    # ---------- 即时保存 ----------
    def _apply(self):
        self.settings.save()
        if self.on_apply:
            self.on_apply()

    def _save_width(self, v):
        self.settings["main_width_ratio"] = float(v)
        self._apply()

    def _save_font(self, v):
        self.settings["main_font_size"] = int(v)
        self._apply()

    def _save_auto_scroll(self, v):
        self.settings["main_auto_scroll"] = bool(v)
        self._apply()

    def _save_scroll(self, *_):
        self.settings["main_scroll_interval"] = int(self.scroll_interval.value())
        self.settings["main_scroll_step"] = int(self.scroll_step.value())
        self.settings["main_scroll_pause"] = int(self.scroll_pause.value())
        self._apply()

    def _save_advance(self, v):
        if self.schedule:
            self.schedule.set_advance_minutes(int(v))

    def _save_check_update(self, v):
        self.settings["check_update_on_start"] = bool(v)
        self._apply()

    def _save_island(self, *_):
        self.settings["island_top_margin"] = int(self.island_margin.value())
        self.settings["island_alert_width"] = int(self.island_alert_width.value())
        self.settings["island_hide_on_fullscreen"] = bool(
            self.island_fullscreen_hide.isChecked())
        self.settings["island_show_wakeup_anim"] = bool(
            self.island_wakeup_anim.isChecked())
        self._apply()

    def _save_fade(self, *_):
        self.settings["anim_fade_window"] = bool(self.fade_window.isChecked())
        self.settings["anim_fade_panel"] = bool(self.fade_panel.isChecked())
        self.settings["anim_fade_text"] = bool(self.fade_text.isChecked())
        self.settings["anim_duration"] = int(self.anim_duration.value())
        self._apply()

    def _open_duty_editor(self):
        from gui import ClassBoardApp
        for w in QApplication.topLevelWidgets():
            if isinstance(w, ClassBoardApp):
                w.edit_duty()
                return

    def _open_course_editor(self):
        if not self.schedule:
            return
        import menu as menu_mod
        dlg = menu_mod.CourseEditor(self.schedule, self)
        if dlg.exec():
            self._notify_island()

    def _notify_island(self):
        for w in QApplication.topLevelWidgets():
            if w.__class__.__name__ == 'DynamicIsland':
                w._last_key = None
                w.update()
                break

    # ---------- 打开动画 ----------
    def showEvent(self, event):
        super().showEvent(event)
        if not self._opened:
            self._opened = True
            QTimer.singleShot(40, self._play_open_anims)

    def _play_open_anims(self):
        self._animate_sidebar_in()
        self._animate_page_in(self.stack.currentWidget(), first=True)

    def _animate_sidebar_in(self):
        for i, btn in enumerate(self._nav_buttons):
            base_y = 20 + i * (self.NAV_BTN_H + self.NAV_BTN_GAP)
            eff = btn.graphicsEffect()
            eff.setOpacity(0.0)
            btn.move(-60, base_y)
            QTimer.singleShot(i * 70, lambda b=btn, y=base_y, e=eff:
                              self._slide_btn(b, y, e))

    def _slide_btn(self, btn, y, eff):
        a_pos = QPropertyAnimation(btn, b"pos", btn)
        a_pos.setDuration(200)
        a_pos.setStartValue(QPoint(-60, y))
        a_pos.setEndValue(QPoint(0, y))
        a_pos.setEasingCurve(QEasingCurve.OutCubic)
        a_pos.start(QAbstractAnimation.DeleteWhenStopped)

        a_op = QPropertyAnimation(eff, b"opacity", btn)
        a_op.setDuration(200)
        a_op.setStartValue(0.0)
        a_op.setEndValue(1.0)
        a_op.start(QAbstractAnimation.DeleteWhenStopped)

    def _animate_page_in(self, page, first=False):
        if page is None:
            return
        inner = getattr(page, '_inner_layout', None)
        if inner is None:
            return
        widgets = []
        for i in range(inner.count()):
            item = inner.itemAt(i)
            w = item.widget()
            if w is not None and not isinstance(w, QLabel):
                widgets.append(w)
        if not widgets:
            return
        delay_base = 100 if first else 200
        for i, w in enumerate(reversed(widgets)):
            eff = w.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(w)
                w.setGraphicsEffect(eff)
            eff.setOpacity(0.0)
            QTimer.singleShot(delay_base + i * 40,
                              lambda ww=w, e=eff: self._fade_in(ww, e))

    def _fade_in(self, widget, eff):
        a = QPropertyAnimation(eff, b"opacity", widget)
        a.setDuration(220)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.start(QAbstractAnimation.DeleteWhenStopped)