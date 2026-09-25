"""副灵动岛：显示在主岛右侧，可收成圆形。

内容来源：插件内容（text/icon 或自定义 draw）> 占位。
"""
import sys
import time

from PySide6.QtWidgets import QWidget, QMenu
from PySide6.QtCore import (Qt, QTimer, QRect, QPropertyAnimation,
                            QEasingCurve)
from PySide6.QtGui import QPainter, QColor, QPainterPath, QFont

if sys.platform == 'win32':
    import ctypes
    _SWP_NOSIZE, _SWP_NOMOVE = 0x0001, 0x0002
    _SWP_NOACTIVATE, _SWP_SHOWWINDOW = 0x0010, 0x0040

    def _set_topmost(hwnd):
        try:
            ctypes.windll.user32.SetWindowPos(
                ctypes.c_void_p(int(hwnd)), ctypes.c_void_p(-1),
                0, 0, 0, 0,
                _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE | _SWP_SHOWWINDOW)
        except Exception:
            pass
else:
    def _set_topmost(hwnd):
        return


class SubIsland(QWidget):
    HEIGHT = 40
    COLLAPSED = 40
    GAP = 8
    DEFAULT_LEN = 158
    MIN_LEN = 44
    MAX_LEN = 380
    ACTIVE_STATES = ('compact', 'countdown', 'alert')
    ANIM_MS = 180
    PIN_INTERVAL_MS = 1000

    def __init__(self, settings, plugin_manager=None, controller=None):
        super().__init__()
        self.settings = settings
        self.plugin_manager = plugin_manager
        self.controller = controller

        self.enabled = bool(settings.get('show_sub_island', True))
        self.collapsed = bool(settings.get('sub_island_collapsed', False))
        self._collapsed_setting = self.collapsed

        self._source = 'empty'
        self._spec = None
        self._length = self.DEFAULT_LEN
        self._anchor_x = 0
        self._anchor_y = 0
        self._main_state = 'hidden'

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
            Qt.Tool | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(self.ANIM_MS)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(16)          # ~60fps
        self._frame_timer.setTimerType(Qt.PreciseTimer)
        self._frame_timer.timeout.connect(self._tick)

        self._pin_timer = QTimer(self)
        self._pin_timer.setInterval(self.PIN_INTERVAL_MS)
        self._pin_timer.timeout.connect(self._pin_top)

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self.collapse)

        self.refresh_content()

    # ---------- 内容 ----------
    def refresh_content(self):
        prev_w = self._effective_width()

        spec = None
        if self.plugin_manager is not None:
            spec = self.plugin_manager.get_subisland_spec()

        if spec and (spec.get('text') or spec.get('draw')):
            source = 'plugin'
            length = self._clamp(spec.get('length', self.DEFAULT_LEN))
        else:
            source = 'empty'
            length = self.COLLAPSED

        self._source = source
        self._spec = spec if source == 'plugin' else None
        self._length = length

        self._update_auto_timer()

        if self._effective_width() != prev_w:
            self._sync_geometry(animate=True)
        self.update()

    def _effective_width(self):
        return self.COLLAPSED if self.collapsed else self._length

    def _update_auto_timer(self):
        spec = self._spec or {}
        want_auto = self._source == 'empty' or bool(spec.get('auto_collapse'))
        if not want_auto or self.collapsed:
            self._auto_timer.stop()
        elif not self._auto_timer.isActive():
            self._restart_auto()

    def _clamp(self, value):
        try:
            return max(self.MIN_LEN, min(self.MAX_LEN, int(value)))
        except (TypeError, ValueError):
            return self.DEFAULT_LEN

    def _restart_auto(self):
        try:
            sec = int(self.settings.get('sub_island_auto_collapse_sec', 5))
        except (TypeError, ValueError):
            sec = 5
        if sec > 0:
            self._auto_timer.start(sec * 1000)
        else:
            self._auto_timer.stop()

    # ---------- 几何 ----------
    def _target_rect(self):
        w = self.COLLAPSED if self.collapsed else self._length
        return QRect(int(self._anchor_x), int(self._anchor_y),
                     int(w), self.HEIGHT)

    def reposition(self, main_geom):
        new_x = main_geom.right() + 1 + self.GAP
        new_y = main_geom.top()
        if new_x == self._anchor_x and new_y == self._anchor_y:
            return
        self._anchor_x = new_x
        self._anchor_y = new_y

        target = self._target_rect()
        if self.anim.state() == QPropertyAnimation.Running:
            self.anim.setEndValue(target)
        elif target != self.geometry():
            self.setGeometry(target)

    def _sync_geometry(self, animate=False):
        target = self._target_rect()
        if target == self.geometry():
            return
        if animate and self.isVisible():
            self.anim.stop()
            self.anim.setStartValue(self.geometry())
            self.anim.setEndValue(target)
            self.anim.start()
        else:
            self.anim.stop()
            self.setGeometry(target)

    # ---------- 状态 ----------
    def set_main_state(self, state):
        self._main_state = state
        want = self.enabled and state in self.ACTIVE_STATES
        if want and not self.isVisible():
            self.show()
        elif not want and self.isVisible():
            self.hide()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.set_main_state(self._main_state)

    def apply_settings(self):
        self.enabled = bool(self.settings.get('show_sub_island', True))

        new_default = bool(self.settings.get('sub_island_collapsed', False))
        if new_default != self._collapsed_setting:
            self._collapsed_setting = new_default
            was = self._effective_width()
            self.collapsed = new_default
            self.refresh_content()
            if self._effective_width() != was:
                self._sync_geometry(animate=True)
        else:
            self.refresh_content()

        self.set_main_state(self._main_state)

    def expand(self):
        if not self.enabled:
            return
        if self.collapsed:
            self.collapsed = False
            self._update_auto_timer()
            self._sync_geometry(animate=True)
        self.refresh_content()

    def collapse(self):
        self.collapsed = True
        self._update_auto_timer()
        self._sync_geometry(animate=True)
        self.update()

    def toggle(self):
        if self.collapsed:
            self.expand()
        else:
            self.collapse()

    # ---------- 事件 ----------
    def showEvent(self, event):
        super().showEvent(event)
        self._pin_top()
        self._frame_timer.start()
        self._pin_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._frame_timer.stop()
        self._pin_timer.stop()

    def _pin_top(self):
        _set_topmost(self.winId())

    def _tick(self):
        spec = self._spec or {}
        if spec.get('draw'):
            self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.plugin_manager is not None:
            self.plugin_manager.handle_subisland_click()
        self.toggle()

    def contextMenuEvent(self, event):
        m = QMenu(self)
        m.addAction("收起" if not self.collapsed else "展开", self.toggle)
        m.addSeparator()
        m.addAction("关闭副岛", self._disable)
        m.exec(event.globalPos())

    def _disable(self):
        self.enabled = False
        self.settings['show_sub_island'] = False
        self.settings.save()
        self.hide()
        if self.controller is not None:
            self.controller.refresh_tray()

    # ---------- 绘制 ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        radius = rect.height() / 2
        path = QPainterPath()
        path.addRoundedRect(0, 0, rect.width(), rect.height(), radius, radius)
        p.fillPath(path, QColor('#1c1c1e'))

        if self._source == 'plugin':
            self._paint_plugin(p)
        else:
            self._paint_empty(p)

    def _paint_empty(self, p):
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(16)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor('#8a8a8e'))
        p.drawText(self.rect(), Qt.AlignCenter, "—")

    def _paint_plugin(self, p):
        spec = self._spec or {}
        draw = spec.get('draw')
        if callable(draw):
            try:
                draw(p, self.rect(), time.monotonic())
            except Exception:
                pass
            return

        text = str(spec.get('text', ''))
        icon = spec.get('icon')

        if self.collapsed:
            label = str(icon) if icon else (text[:1] if text else "•")
            font = QFont("Segoe UI Emoji")
            font.setPixelSize(18)
            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor('white'))
            p.drawText(self.rect(), Qt.AlignCenter, label)
            return

        x = 10
        if icon:
            font = QFont("Segoe UI Emoji")
            font.setPixelSize(18)
            p.setFont(font)
            p.setPen(QColor('white'))
            p.drawText(QRect(x, 0, 28, self.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, str(icon))
            x += 30

        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(13)
        p.setFont(font)
        p.setPen(QColor('#e6e6e6'))
        p.drawText(QRect(x, 0, self.width() - x - 10, self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, text)

    def closeEvent(self, event):
        self._frame_timer.stop()
        self._pin_timer.stop()
        self._auto_timer.stop()
        self.anim.stop()
        super().closeEvent(event)
