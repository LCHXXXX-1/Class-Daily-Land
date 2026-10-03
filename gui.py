import os
import json

from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QMenu,
                               QApplication, QMessageBox,
                               QScrollArea, QFrame)
from PySide6.QtCore import (Qt, QTimer, QPropertyAnimation, QEasingCurve,
                            QEvent)
from PySide6.QtGui import QShortcut, QKeySequence

from StudentOnDuty import StudentOnDuty
from homework import HomeworkManager
from utils import set_window_icon
from ui_common import setup_touch_scroll
from storage import update_json
import theme
import menu as menu_mod

# 手指自己滑过主面板后，自动滚动让位多久（毫秒）
MANUAL_SCROLL_HOLD_MS = 4000


class ClassBoardApp(QWidget):
    def __init__(self, config_dir, config_file, schedule_manager, settings,
                 plugin_manager=None, controller=None):
        super().__init__()
        self.config_dir = config_dir
        self.config_file = config_file
        self.schedule_manager = schedule_manager
        self.settings = settings
        self.plugin_manager = plugin_manager
        self.controller = controller
        self._scroll_dir = 1
        self._scroll_pause = 0
        self._scroll_acc = 0.0
        self._opened_animated = False
        self._fade_anim = None
        self._target_opacity = float(self.settings.get("main_opacity", 1.0))

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        set_window_icon(self)
        theme.theme_changed_connect(self._apply_theme)

        self.duty_manager = StudentOnDuty()
        self.homework_manager = HomeworkManager()
        self.load_config()

        screen = QApplication.primaryScreen().geometry()
        self.screen_width = screen.width()
        self.screen_height = screen.height()

        self._build_ui()
        self._apply_theme()

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        QShortcut(QKeySequence("F1"), self, self._exit_app)

        # 退出信号监视（供 Launcher 在安装前通知主程序优雅退出）
        self._setup_quit_watcher()

        # 启动后延迟自动检查更新（Launcher_hide.exe，后台静默）
        QTimer.singleShot(2000, self._auto_check_update)

    # ================= 配置 =================
    def load_config(self):
        self.should = '40'
        self.actual = '0'
        self.font_size = int(self.settings.get("main_font_size", 14))
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.should = data.get('should', '40')
                self.actual = data.get('actual', '0')
            except Exception:
                pass
        else:
            self.save_config()

    def save_config(self):
        # 原子写（临时文件 + os.replace），避免崩溃损坏 config.json
        update_json(self.config_file, should=self.should, actual=self.actual)
        self.settings["main_font_size"] = self.font_size
        self.settings.save()

    # ================= UI =================
    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 8, 12, 8)
        self.main_layout.setSpacing(4)
        self.main_layout.setAlignment(Qt.AlignTop)

        self.title_label = QLabel("班级日常")
        self.main_layout.addWidget(self.title_label)

        self.duty_label = QLabel()
        self.main_layout.addWidget(self.duty_label)

        self.att_label = QLabel()
        self.main_layout.addWidget(self.att_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.homework_container = QWidget()
        self.homework_layout = QVBoxLayout(self.homework_container)
        self.homework_layout.setContentsMargins(0, 0, 0, 0)
        self.homework_layout.setSpacing(2)
        self.homework_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.homework_container)

        self.main_layout.addWidget(self.scroll)

        # 触屏：手指拖拽 + 惯性滑动（这儿没有滚轮，拖是唯一的滚动方式）
        setup_touch_scroll(self.scroll, mouse_drag=True)
        self.scroll.viewport().installEventFilter(self)

        self._auto_scroll_timer = QTimer(self)
        self._auto_scroll_timer.setInterval(
            int(self.settings.get("main_scroll_interval", 50)))
        self._auto_scroll_timer.timeout.connect(self._auto_scroll_tick)

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    # ================= 主题 =================
    def _apply_theme(self):
        """按当前主题刷新窗口背景与文字颜色（theme watcher 回调）。"""
        bg = theme.color("window_bg")
        self.setStyleSheet(f"ClassBoardApp {{ background-color: {bg}; }}")
        self.scroll.setStyleSheet(
            f"QScrollArea {{ background: {bg}; border: none; }}")
        self.homework_container.setStyleSheet(f"background: {bg};")
        self.update_display()

    # ================= 显示 =================
    def update_display(self):
        fs = self.font_size
        fg = theme.color("text")
        self.title_label.setStyleSheet(
            f"font-size: {fs + 4}px; font-weight: bold; color: {fg};")
        self.duty_label.setStyleSheet(f"font-size: {fs}px; color: {fg};")
        self.att_label.setStyleSheet(f"font-size: {fs}px; color: {fg};")

        self.duty_label.setText(f"今日值日生：{self.duty_manager.get_current_duty()}")
        self.att_label.setText(f"应到 {self.should} 人 · 实到 {self.actual} 人")

        self._clear_layout(self.homework_layout)

        grouped = self.homework_manager.get_grouped_homework()
        if not grouped:
            lbl = QLabel("暂无作业")
            lbl.setStyleSheet(f"font-size: {fs}px; color: {fg};")
            lbl.setWordWrap(True)
            self.homework_layout.addWidget(lbl)
        else:
            for subject, data in grouped.items():
                title = subject
                date = data.get('date', '')
                if date and date.strip():
                    title += f" ({date.strip()})"
                hdr = QLabel(title)
                hdr.setStyleSheet(
                    f"font-size: {fs}px; font-weight: bold; color: {fg};")
                hdr.setWordWrap(True)
                self.homework_layout.addWidget(hdr)

                for idx, content in enumerate(data['contents'], 1):
                    item = QLabel(f"  {idx}. {content}")
                    item.setWordWrap(True)
                    item.setStyleSheet(f"font-size: {fs}px; color: {fg};")
                    self.homework_layout.addWidget(item)

        self._adjust_window()

    def _adjust_window(self):
        ratio = float(self.settings.get("main_width_ratio", 0.25))
        width = int(self.screen_width * ratio)
        x = self.screen_width - width
        self.setFixedWidth(width)

        m = self.main_layout.contentsMargins()
        sp = self.main_layout.spacing()

        header_h = (m.top() + m.bottom()
                    + self.title_label.sizeHint().height()
                    + self.duty_label.sizeHint().height()
                    + self.att_label.sizeHint().height()
                    + sp * 3)

        avail = width - m.left() - m.right()
        if avail < 50:
            avail = 50

        raw_content_h = self._calc_content_height(avail)
        max_h = self.screen_height - 50
        content_max = max(40, max_h - header_h)
        content_h = min(raw_content_h, content_max)
        needs_scroll = raw_content_h > content_max + 4

        total_h = header_h + content_h
        self.scroll.setFixedHeight(content_h)
        self.setFixedHeight(total_h)
        self.setGeometry(x, 0, width, total_h)
        QTimer.singleShot(0, lambda: self._apply_scroll(needs_scroll))

    def _apply_scroll(self, needs_scroll):
        if not self.settings.get("main_auto_scroll", True):
            self._auto_scroll_timer.stop()
            self._scroll_dir = 1
            self._scroll_pause = 0
            self._scroll_acc = 0.0
            self.scroll.verticalScrollBar().setValue(0)
            return
        bar = self.scroll.verticalScrollBar()
        if needs_scroll and bar.maximum() > 0:
            if not self._auto_scroll_timer.isActive():
                self._scroll_dir = 1
                self._scroll_pause = 0
                self._scroll_acc = 0.0
                bar.setValue(0)
                self._auto_scroll_timer.setInterval(
                    int(self.settings.get("main_scroll_interval", 50)))
                self._auto_scroll_timer.start()
        else:
            self._auto_scroll_timer.stop()
            self._scroll_dir = 1
            self._scroll_pause = 0
            self._scroll_acc = 0.0
            bar.setValue(0)

    def _calc_content_height(self, avail_width):
        n = self.homework_layout.count()
        if n == 0:
            return 40
        total = 0
        for i in range(n):
            w = self.homework_layout.itemAt(i).widget()
            if w is None:
                continue
            if w.hasHeightForWidth():
                total += w.heightForWidth(avail_width)
            else:
                total += w.sizeHint().height()
            if i < n - 1:
                total += self.homework_layout.spacing()
        return max(total, 20)

    def _auto_scroll_tick(self):
        bar = self.scroll.verticalScrollBar()
        if bar.maximum() <= 0:
            self._auto_scroll_timer.stop()
            return
        if self._scroll_pause > 0:
            self._scroll_pause -= 1
            return
        try:
            step = float(self.settings.get("main_scroll_step", 1))
        except (TypeError, ValueError):
            step = 1.0
        pause = int(self.settings.get("main_scroll_pause", 60))
        # 浮点累积：低速滚动时不再整像素顿感
        self._scroll_acc += step
        iv = int(self._scroll_acc)
        if iv < 1:
            return
        self._scroll_acc -= iv
        if self._scroll_dir == 1:
            if bar.value() + iv >= bar.maximum():
                bar.setValue(bar.maximum())
                self._scroll_pause = pause
                self._scroll_dir = -1
            else:
                bar.setValue(bar.value() + iv)
        else:
            if bar.value() - iv <= 0:
                bar.setValue(0)
                self._scroll_pause = pause
                self._scroll_dir = 1
            else:
                bar.setValue(bar.value() - iv)

    # ================= 触屏 / 滚轮：手动滑动优先 =================
    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport() and event.type() in (
                QEvent.Wheel, QEvent.MouseButtonPress, QEvent.TouchBegin):
            self._pause_auto_scroll()
        return super().eventFilter(obj, event)

    def _pause_auto_scroll(self):
        """用户自己滑过之后，自动滚动先停几秒，别和手指抢画面。"""
        timer = self._auto_scroll_timer
        if timer is None or not timer.isActive():
            return
        ticks = int(MANUAL_SCROLL_HOLD_MS / max(1, timer.interval()))
        self._scroll_pause = max(self._scroll_pause, max(1, ticks))

    # ================= 打开动画 =================
    def showEvent(self, event):
        super().showEvent(event)
        screen = QApplication.primaryScreen().geometry()
        if (screen.width() != self.screen_width
                or screen.height() != self.screen_height):
            self.screen_width = screen.width()
            self.screen_height = screen.height()
            self._adjust_window()
        if not self._opened_animated:
            self._opened_animated = True
            if self.settings.get("anim_fade_window", True):
                QTimer.singleShot(0, self._play_open_anim)

    def _play_open_anim(self):
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(int(self.settings.get("anim_duration", 320)))
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(self._target_opacity)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.start()

    def apply_opacity(self, value):
        try:
            self._target_opacity = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            self._target_opacity = 1.0
        self.setWindowOpacity(self._target_opacity)

    # ================= 右键菜单 =================
    def _show_menu(self, pos):
        m = QMenu(self)
        m.addAction("上一位值日生", self.previous_duty)
        m.addAction("下一位值日生", self.next_duty)
        m.addSeparator()
        m.addAction("出勤人数", self.modify_attendance)
        m.addSeparator()
        m.addAction("编辑作业", self.edit_homework)
        m.addSeparator()
        m.addAction("课表管理", self.manage_timetables)
        m.addAction("临时调课", self.temp_adjust)
        m.addSeparator()
        m.addAction("假期与调休", self.open_holidays)
        m.addAction("周末作息", self.open_weekend)
        m.addSeparator()
        m.addAction("设置", self.open_settings)
        m.addSeparator()
        m.addAction("随机点名", self.open_randoms)
        m.addSeparator()
        m.addAction("退出", self._exit_app)
        m.exec(self.mapToGlobal(pos))

    # ================= 业务 =================
    def previous_duty(self):
        self.duty_manager.previous_duty()
        self.update_display()

    def next_duty(self):
        self.duty_manager.next_duty()
        self.update_display()

    def edit_duty(self):
        menu_mod.DutyEditor(self.duty_manager, self, self).exec()

    def modify_attendance(self):
        menu_mod.AttendanceDialog(self, self).exec()

    def edit_homework(self):
        menu_mod.HomeworkEditor(self.homework_manager, self, self).exec()

    def edit_schedule(self):
        dlg = menu_mod.CourseEditor(self.schedule_manager, self)
        if dlg.exec():
            self._notify_island()

    def manage_timetables(self):
        dlg = menu_mod.TimetableManagerDialog(
            self.schedule_manager, on_change=self._notify_island, parent=self)
        dlg.exec()
        self._notify_island()

    def temp_adjust(self):
        dlg = menu_mod.TempAdjustDialog(self.schedule_manager, self)
        if dlg.exec():
            self._notify_island()

    def open_holidays(self):
        dlg = menu_mod.HolidayDialog(self.schedule_manager, self)
        dlg.exec()
        self._notify_island()

    def open_weekend(self):
        dlg = menu_mod.WeekendScheduleDialog(self.schedule_manager, self)
        dlg.exec()
        self._notify_island()

    def open_settings(self):
        # 设置界面 V4（1:1 Win11 设置：二级导航 + 内嵌课表/作业编辑）
        # 回退旧版：改回 settings_dialog_v3 / v2 / settings_dialog
        # 单例：已打开则激活已有窗口，避免从托盘/右键菜单重复打开无数个
        existing = getattr(self, "_settings_dlg", None)
        if existing is not None:
            try:
                existing.showNormal()
                existing.raise_()
                existing.activateWindow()
                return
            except RuntimeError:
                self._settings_dlg = None
        from settings_dialog_v4 import SettingsDialog
        # 副岛（或主岛）→ 设置窗口的形变过渡起点
        morph_rect = None
        try:
            sub = getattr(self.controller, "sub_island", None)
            island = getattr(self.controller, "island", None)
            if sub is not None and sub.isVisible():
                morph_rect = sub.frameGeometry()
            elif island is not None and island.isVisible():
                morph_rect = island.frameGeometry()
        except Exception:
            morph_rect = None
        dlg = SettingsDialog(
            self.settings,
            schedule_manager=self.schedule_manager,
            plugin_manager=self.plugin_manager,
            controller=self.controller,
            parent=self,
            morph_from=morph_rect,
        )
        self._settings_dlg = dlg
        dlg.exec()
        self._settings_dlg = None
        dlg.deleteLater()

    def apply_main_settings(self):
        self.font_size = int(self.settings.get("main_font_size", 14))
        self.apply_opacity(self.settings.get("main_opacity", 1.0))
        self.update_display()
        if self.settings.get("main_auto_scroll", True):
            self._auto_scroll_timer.setInterval(
                int(self.settings.get("main_scroll_interval", 50)))

    def _notify_island(self):
        if self.controller is not None:
            self.controller.notify_island_dirty()

    def open_randoms(self):
        import randoms
        randoms.main(self)

    def open_status_test(self):
        from test_dialog import StatusTestDialog
        dlg = StatusTestDialog(self.schedule_manager, self.settings,
                               self.controller, self)
        dlg.exec()

    def _exit_app(self):
        QApplication.quit()

    # ================= 更新（全部委托给 Launcher） =================
    def _auto_check_update(self):
        """启动时后台静默检查更新（Launcher_hide.exe，无 UI）。"""
        if not self.settings.get("check_update_on_start", True):
            return
        try:
            from launch_updater import launch_hidden
        except Exception:
            return
        launch_hidden()

    def open_updater(self):
        """用户主动检查更新（Launcher.exe，会显示窗口）。"""
        try:
            from launch_updater import launch_visible
        except Exception as e:
            QMessageBox.warning(self, "更新", f"更新模块不可用：{e}")
            return
        ok, msg = launch_visible()
        if not ok:
            QMessageBox.warning(self, "更新", msg)

    # ================= 退出信号监视 =================
    def _setup_quit_watcher(self):
        try:
            from launch_updater import clear_quit_flag, get_quit_flag_path
        except Exception:
            return
        clear_quit_flag()
        self._quit_flag_path = get_quit_flag_path()
        self._quit_timer = QTimer(self)
        self._quit_timer.timeout.connect(self._check_quit_flag)
        self._quit_timer.start(500)

    def _check_quit_flag(self):
        p = getattr(self, "_quit_flag_path", None)
        if not p:
            return
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
            try:
                self._quit_timer.stop()
            except Exception:
                pass
            QApplication.quit()