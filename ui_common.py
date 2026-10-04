import sys
import ctypes

from PySide6.QtWidgets import (QAbstractItemView, QAbstractScrollArea,
                               QComboBox, QGraphicsOpacityEffect, QScroller,
                               QScrollerProperties)
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


# ---------------- Windows 11 材质（DWM） ----------------
# 参考：DWMWINDOWATTRIBUTE 取值
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWA_SYSTEMBACKDROP_TYPE = 38
_DWMWA_MICA_EFFECT = 1029        # 21H2 旧接口

_DWMWCP_ROUND = 2
_DWMSBT_NONE = 1
_DWMSBT_MAINWINDOW = 2           # 云母（Mica）


def _dwm_set(hwnd, attr, value):
    """调用 DwmSetWindowAttribute，成功返回 True。"""
    try:
        v = ctypes.c_int(int(value))
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(int(hwnd)), ctypes.c_int(int(attr)),
            ctypes.byref(v), ctypes.c_int(ctypes.sizeof(v)))
        return res == 0
    except Exception:
        return False


def set_dark_titlebar(widget, dark):
    """设置原生标题栏明暗（Windows 10 1809+ / Windows 11）。"""
    if sys.platform != 'win32':
        return False
    try:
        hwnd = int(widget.winId())
    except Exception:
        return False
    return _dwm_set(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0)


def apply_round_corners(widget):
    """Windows 11 圆角窗口。"""
    if sys.platform != 'win32':
        return False
    try:
        hwnd = int(widget.winId())
    except Exception:
        return False
    return _dwm_set(hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, _DWMWCP_ROUND)


class _MARGINS(ctypes.Structure):
    _fields_ = [("cxLeftWidth", ctypes.c_int),
                ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int),
                ("cyBottomHeight", ctypes.c_int)]


def extend_frame_into_client(widget):
    """把 DWM 边框扩展到整个客户区（-1 边距），
    让云母材质覆盖整窗，而不只是标题栏。"""
    if sys.platform != 'win32':
        return False
    try:
        hwnd = int(widget.winId())
        m = _MARGINS(-1, -1, -1, -1)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
            ctypes.c_void_p(hwnd), ctypes.byref(m))
        return True
    except Exception:
        return False


def apply_mica(widget):
    """开启 Windows 11 云母（Mica）背板；成功返回 True。

    需要窗口背景透明（Qt.WA_TranslucentBackground）才能看到效果，
    并把 DWM 边框扩展到客户区，使云母覆盖整个窗口。
    Windows 10 直接返回 False。
    """
    if sys.platform != 'win32':
        return False
    from utils import is_windows_11
    if not is_windows_11():
        return False
    try:
        hwnd = int(widget.winId())
    except Exception:
        return False
    extend_frame_into_client(widget)           # 云母铺满整个窗口
    if _dwm_set(hwnd, _DWMWA_SYSTEMBACKDROP_TYPE, _DWMSBT_MAINWINDOW):
        return True
    return _dwm_set(hwnd, _DWMWA_MICA_EFFECT, 1)   # 旧版 Win11 回退


def disable_mica(widget):
    """关闭云母背板，恢复为不透明窗口。"""
    if sys.platform != 'win32':
        return
    try:
        hwnd = int(widget.winId())
    except Exception:
        return
    _dwm_set(hwnd, _DWMWA_SYSTEMBACKDROP_TYPE, _DWMSBT_NONE)


def apply_window_material(widget, mica=True, dark=False):
    """统一应用 Windows 11 窗口材质：圆角 + 可选云母 + 标题栏明暗。

    返回云母是否成功启用（Windows 10 上恒为 False）。
    """
    apply_round_corners(widget)
    material = False
    if mica:
        material = apply_mica(widget)
    set_dark_titlebar(widget, dark)
    return material


class _TaskbarHelper(QObject):
    """在每次显示时重设扩展样式，避免被 Qt 覆盖。"""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show:
            force_taskbar(obj)
        return False


def setup_dialog_style(dlg, translucent=False):
    dlg.setWindowFlags(
        (dlg.windowFlags() & ~Qt.WindowStaysOnTopHint)
        | Qt.Window | Qt.WindowSystemMenuHint
        | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
        | Qt.WindowCloseButtonHint
    )
    # WA_TranslucentBackground 必须在原生窗口创建之前设置，否则不生效
    # （会导致云母只出现在标题栏、客户区仍是黑/不透明）
    if translucent:
        dlg.setAttribute(Qt.WA_TranslucentBackground, True)
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


# ---------------- 触屏滑动（QScroller 惯性滚动） ----------------
# 一体机 / 触摸屏上没有滚轮，全靠手指拖 + 松手后的惯性。
# 用 Qt 自带的 QScroller：只抓手势，点击、按钮、滑杆照旧，不会抢事件。
_TOUCH_SCROLL_PROP = "_cdlTouchScroll"

# 手感参数：跟手一点、松手平滑减速、别冲太远（Qt 版本缺哪项就自动跳过）
_SCROLL_METRICS = (
    ("DragVelocitySmoothingFactor", 0.6),
    ("MinimumVelocity", 0.05),        # 松手速度低于 50px/s 视为「停下」（点击停惯性走干净路径）
    ("MaximumVelocity", 1.4),
    # Qt 默认 0.0665：惯性慢下来后按下只停惯性、这次拖动直接作废（要按第二次才能拖）。
    # 调成 0 后只要惯性还在动，手指/鼠标一按就直接接管拖拽；原生触摸的手感。
    ("MaximumClickThroughVelocity", 0.0),
    ("DecelerationFactor", 0.12),
    ("AxisLockThreshold", 0.4),
    ("OvershootDragResistanceFactor", 0.5),
    ("OvershootScrollDistanceFactor", 0.5),
)

# 只有开了鼠标拖拽滚动才需要：按下先压 50ms，区分「点一下」和「拖着滚」
_MOUSE_DRAG_METRICS = (
    ("MousePressEventDelay", 0.05),
)


def _scroll_target(widget):
    """真正该抓手势的对象：滚动控件抓 viewport，普通控件抓自己。"""
    viewport = getattr(widget, "viewport", None)
    if callable(viewport):
        try:
            vp = viewport()
        except Exception:
            vp = None
        if vp is not None:
            return vp
    return widget


def _tune_scroller(target, mouse_drag=False):
    """把 QScroller 的手感调成适合手指的一套。"""
    try:
        scroller = QScroller.scroller(target)
        props = scroller.scrollerProperties()
    except Exception:
        return
    metrics = _SCROLL_METRICS + (_MOUSE_DRAG_METRICS if mouse_drag else ())
    for name, value in metrics:
        metric = getattr(QScrollerProperties.ScrollMetric, name, None)
        if metric is None:
            continue
        try:
            props.setScrollMetric(metric, value)
        except Exception:
            pass
    try:
        scroller.setScrollerProperties(props)
    except Exception:
        pass


def setup_touch_scroll(widget, mouse_drag=False, pixel_scroll=True):
    """给滚动控件装上触屏惯性滑动（幂等，重复调用没关系）。

    - QScrollArea / QTableView / QTextEdit 这类会自动用 viewport 抓手势；
    - pixel_scroll=True 把列表 / 表格切成逐像素滚动，手指拖起来才顺滑；
    - mouse_drag=True 额外支持鼠标左键拖拽滚动（触摸被系统转成鼠标时的兜底）。
    返回是否成功装上手势。

    Qt 行为备忘：QFlickGesture 给"仍在 Dragging/Scrolling 的 scroller"
    全局优先权——按压点若落在它的区域内会被忽略。同一窗口内各滚动区
    几何互不重叠，不影响使用；只有"两个顶层窗口重叠且下层惯性未停"
    这种罕见场景需要等惯性结束再按。
    """
    if widget is None:
        return False
    try:
        done = bool(widget.property(_TOUCH_SCROLL_PROP))
    except Exception:
        done = False
    # 已经装过、这次也没要求开鼠标拖拽 → 跳过（幂等）；
    # 要求 mouse_drag=True 时即使装过也要继续，把左键拖拽手势补上。
    if done and not mouse_drag:
        return True

    target = _scroll_target(widget)
    ok = False
    try:
        ok = bool(QScroller.grabGesture(
            target, QScroller.ScrollerGestureType.TouchGesture))
        if mouse_drag:
            QScroller.grabGesture(
                target, QScroller.ScrollerGestureType.LeftMouseButtonGesture)
    except Exception:
        ok = False

    if pixel_scroll:
        mode = QAbstractItemView.ScrollMode.ScrollPerPixel
        for setter in ("setVerticalScrollMode", "setHorizontalScrollMode"):
            fn = getattr(widget, setter, None)
            if fn is None:
                continue
            try:
                fn(mode)
            except Exception:
                pass

    _tune_scroller(target, mouse_drag=mouse_drag)
    try:
        widget.setProperty(_TOUCH_SCROLL_PROP, True)
    except Exception:
        pass
    return ok


class _TouchScrollInstaller(QObject):
    """应用级兜底：任何滚动控件一显示就自动获得触屏惯性滑动。

    逐个控件去调 setup_touch_scroll() 容易漏（插件自带的控件、下拉列表、
    输入框都会漏），这里统一在控件首次显示时补上手势。
    """

    def __init__(self, mouse_drag=False, parent=None):
        super().__init__(parent)
        self.mouse_drag = bool(mouse_drag)

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Show:
            return False
        if isinstance(obj, QAbstractScrollArea):
            try:
                setup_touch_scroll(obj, mouse_drag=self.mouse_drag)
            except Exception:
                pass
        elif isinstance(obj, QComboBox):
            # 下拉框的弹出列表是懒创建的，这里提前把它的视图也装上
            try:
                setup_touch_scroll(obj.view(), mouse_drag=self.mouse_drag)
            except Exception:
                pass
        return False


def install_touch_scrolling(app=None, mouse_drag=False):
    """装上全局触屏滑动适配（在 QApplication 建好后调用一次）。"""
    if app is None:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
    if app is None:
        return None
    installer = getattr(app, "_touch_scroll_installer", None)
    if installer is not None:
        return installer
    installer = _TouchScrollInstaller(mouse_drag=mouse_drag, parent=app)
    app.installEventFilter(installer)
    app._touch_scroll_installer = installer
    return installer
