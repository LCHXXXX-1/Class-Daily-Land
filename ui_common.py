"""对话框与动画的公共工具。"""
import sys
import ctypes

from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtCore import (Qt, QPropertyAnimation, QEasingCurve,
                            QAbstractAnimation, QObject, QEvent)

from utils import set_window_icon

_GWL_EXSTYLE = -20
_WS_EX_APPWINDOW = 0x00040000
_WS_EX_TOOLWINDOW = 0x00000080
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020


def force_taskbar(widget):
    """让被 Tool 窗口拥有的对话框也出现在 Windows 任务栏。"""
    if sys.platform != 'win32':
        return
    try:
        user32 = ctypes.windll.user32
        hwnd = int(widget.winId())
        ex = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        ex = (ex | _WS_EX_APPWINDOW) & ~_WS_EX_TOOLWINDOW
        user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, ex)
        user32.SetWindowPos(
            ctypes.c_void_p(hwnd), None, 0, 0, 0, 0,
            _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOZORDER | _SWP_NOACTIVATE
            | _SWP_FRAMECHANGED)
    except Exception:
        pass


class _TaskbarHelper(QObject):
    """在每次显示时重设扩展样式，避免被 Qt 覆盖。"""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show:
            force_taskbar(obj)
        return False


def setup_dialog_style(dlg):
    dlg.setWindowFlags(
        (dlg.windowFlags() & ~Qt.WindowStaysOnTopHint)
        | Qt.Window | Qt.WindowSystemMenuHint
        | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
        | Qt.WindowCloseButtonHint
    )
    dlg.setAttribute(Qt.WA_NativeWindow, True)
    set_window_icon(dlg)

    helper = _TaskbarHelper(dlg)
    dlg.installEventFilter(helper)
    dlg._taskbar_helper = helper
    force_taskbar(dlg)


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
        sub = item.layout()
        if sub is not None:
            clear_layout(sub)


def fade_in(widget, duration=220, start=0.0, end=1.0):
    eff = widget.graphicsEffect()
    if not isinstance(eff, QGraphicsOpacityEffect):
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
    eff.setOpacity(start)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start(QAbstractAnimation.DeleteWhenStopped)
    return anim
