import sys
import os
import time
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta

from PySide6.QtWidgets import QWidget, QMenu, QApplication
from PySide6.QtCore import (Qt, QTimer, QRect, QRectF, QPoint, QPointF,
                            QPropertyAnimation, QEasingCurve, QEvent,
                            QElapsedTimer)
from PySide6.QtGui import (QPainter, QColor, QPainterPath, QFont, QPen,
                           QLinearGradient)

from panel_window import PanelWindow, FadeMask

# ---------- Win32 ----------
_user32 = ctypes.windll.user32 if sys.platform == 'win32' else None
_DESKTOP_CLASSES = ('Progman', 'WorkerW', 'Shell_TrayWnd', 'SysListView32')
MONITOR_DEFAULTTONEAREST = 2
SWP_NOSIZE, SWP_NOMOVE = 0x0001, 0x0002
SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0010, 0x0040
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# WPS / MS Office 的进程名（全部小写）
_OFFICE_PROCESSES = {
    'wps.exe', 'et.exe', 'wpp.exe', 'wpspdf.exe',       # WPS 文字/表格/演示/PDF
    'winword.exe', 'excel.exe', 'powerpnt.exe',          # Microsoft Office
}


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def _set_topmost(hwnd):
    if sys.platform != 'win32':
        return
    try:
        ctypes.windll.user32.SetWindowPos(
            ctypes.c_void_p(int(hwnd)), ctypes.c_void_p(-1), 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
    except Exception:
        pass


def _fg_hwnd():
    return _user32.GetForegroundWindow() if _user32 else 0


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _root_hwnd(hwnd):
    r = _user32.GetAncestor(hwnd, 2)
    return r if r else hwnd


def _is_desktop(hwnd):
    return (not hwnd) or _class_name(hwnd) in _DESKTOP_CLASSES


def _process_name(hwnd):
    """取窗口所属进程的可执行文件名（小写），失败返回空串"""
    if sys.platform != 'win32' or not hwnd:
        return ''
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(ctypes.c_void_p(int(hwnd)),
                                     ctypes.byref(pid))
    if not pid.value:
        return ''
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                  False, pid.value)
    if not handle:
        return ''
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf,
                                               ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ''
    finally:
        kernel32.CloseHandle(handle)


def _is_office_foreground(hwnd):
    """前台窗口是否属于 WPS / MS Office"""
    return _process_name(hwnd) in _OFFICE_PROCESSES


def _is_fullscreen(hwnd):
    if not hwnd or _is_desktop(hwnd):
        return False
    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    hmon = _user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not hmon:
        return False
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not _user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return False
    mon = mi.rcMonitor
    mw, mh = mon.right - mon.left, mon.bottom - mon.top
    if mw <= 0 or mh <= 0:
        return False
    w, h = rect.right - rect.left, rect.bottom - rect.top
    tol = 4
    return (rect.left <= mon.left + tol and rect.top <= mon.top + tol and
            w >= mw - tol * 2 and h >= mh - tol * 2)


class DynamicIsland(QWidget):
    # 尺寸
    COMPACT_W = 240
    COMPACT_H = 40
    RING_SIZE = 28
    COUNTDOWN_W = 600
    MINI_W = 48

    # 面板约束
    PANEL_GAP = 4
    PANEL_STAGGER = 70
    PANEL_MIN_W = 120
    PANEL_MAX_W = 320
    SCHEDULE_DEFAULT_W = 240
    SCHEDULE_MIN_W = 180
    MAX_TOTAL_RATIO = 0.80
    MAX_HEIGHT_RATIO = 1 / 3

    # 时长
    ANIM_MS = 200            # 几何动画基准时长
    ANIM_MIN_MS = 120
    ANIM_MAX_MS = 320
    STEP_GAP_MS = 60
    WATCH_INTERVAL = 400
    TEXT_ROLL_MS = 140
    FILL_MS = 180            # 进度条填充时长
    PANEL_FADE_MS = 160      # 面板内容淡入时长
    PULL_HOLD_MS = 3000      # 下拉后停留 3 秒自动收回
    SHEEN_CYCLE_MS = 1400    # 蓝条流光扫过一轮
    BAR_INSET = 1            # 蓝条相对胶囊内缩
    SCENARIO_ALERT_MS = 1000  # 情景测试里单条提醒的展示时长

    DEBUG = False

    def __init__(self, schedule_manager, settings, plugin_manager=None,
                 controller=None):
        super().__init__()
        self.schedule = schedule_manager
        self.settings = settings
        self.plugin_manager = plugin_manager
        self.controller = controller
        self.enabled = True
        self._geometry_cb = None
        self.TOP_MARGIN = int(settings.get("island_top_margin", 6))

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
            Qt.Tool | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.screen_w = self.screen().geometry().width()
        self.screen_h = self.screen().geometry().height()

        self._state = 'hidden'
        self._last_status = None
        self._last_key = None
        self._anim_done_cb = None

        # 顶掉
        self._roll_active = False
        self._roll_progress = 0.0
        self._old_text = ""
        self._new_text = ""

        # 进度条填充
        self._fill_progress = 0.0
        self._countdown_window = 60      # 进入倒计时那一刻的剩余秒数
        self._countdown_end = None       # 真实倒计时的连续终点
        self._fill_clock = QElapsedTimer()
        self._fill_timer = QTimer(self)
        self._fill_timer.setInterval(16)
        self._fill_timer.setTimerType(Qt.PreciseTimer)
        self._fill_timer.timeout.connect(self._fill_tick)

        self._anim_clock = QElapsedTimer()
        self._anim_clock.start()
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(16)
        self._countdown_timer.setTimerType(Qt.PreciseTimer)
        self._countdown_timer.timeout.connect(self.update)

        # 主岛加长片段（插件媒体等）
        self._extra_spec = None
        self._extra_width = 0
        self._extra_timer = QTimer(self)
        self._extra_timer.setInterval(16)
        self._extra_timer.setTimerType(Qt.PreciseTimer)
        self._extra_timer.timeout.connect(self.update)

        # 下拉
        self._pulled = False
        self._panels = []
        self._panel_rects = []
        self._scroll_offset = 0
        self._scroll_max = 0
        self._fade_mask = None

        # 提醒
        self._alert_text = ""
        self._alert_is_end = False

        # 倒计时忽略（收起后本次不再展开）
        self._countdown_dismissed = None
        self._mouse_down = False
        self._holiday_alerted_date = None

        # 强制演示倒计时（测试用）
        self._testing = False
        self._test_restore_enabled = None
        self._test_phase = None
        self._scenario_id = 0
        self._scenario_advance_end = 0.0
        self._scenario_advance_total = 1.0
        self._scenario_end_hold_ms = 0
        self._test_timer = QTimer(self)
        self._test_timer.setSingleShot(True)
        self._test_timer.timeout.connect(self._end_test_countdown)

        # 定时器
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(self.ANIM_MS)
        self.anim.setEasingCurve(QEasingCurve.OutQuint)
        self.anim.valueChanged.connect(self._on_anim_tick)
        self.anim.finished.connect(self._on_anim_finished)

        self._roll_clock = QElapsedTimer()
        self._roll_timer = QTimer(self)
        self._roll_timer.setInterval(16)
        self._roll_timer.setTimerType(Qt.PreciseTimer)
        self._roll_timer.timeout.connect(self._roll_tick)

        self._pull_timer = QTimer(self)
        self._pull_timer.setSingleShot(True)
        self._pull_timer.timeout.connect(self._push_up)

        self.resize(self.MINI_W, self.COMPACT_H)
        self._move_to(self.MINI_W, self.COMPACT_H, -self.COMPACT_H - 24)

        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self._refresh)
        self.tick_timer.start(1000)

        self.pin_timer = QTimer(self)
        self.pin_timer.timeout.connect(self._pin_top)
        self.pin_timer.start(1000)

        self._click_timer = None
        if sys.platform == 'win32':
            self.watch_timer = QTimer(self)
            self.watch_timer.timeout.connect(self._check_foreground)
            self.watch_timer.start(self.WATCH_INTERVAL)

            self._click_timer = QTimer(self)
            self._click_timer.setInterval(40)
            self._click_timer.timeout.connect(self._poll_outside_click)

        QApplication.instance().installEventFilter(self)
        QTimer.singleShot(200, self._on_start)

    # ---------- 位置 ----------
    def _center_x(self, w):
        return self.screen_w // 2 - w // 2

    def _move_to(self, w, h, y):
        self.setGeometry(self._center_x(w), y, w, h)
        self._notify_geometry()

    def set_geometry_callback(self, cb):
        self._geometry_cb = cb

    def _notify_geometry(self):
        if self._geometry_cb is not None:
            try:
                self._geometry_cb(self.geometry())
            except Exception:
                pass

    # ---------- 主岛加长片段 ----------
    def _compact_width(self):
        return self.COMPACT_W + self._extra_width

    def _extra_rect(self):
        if self._extra_width <= 0:
            return QRect()
        return QRect(self.width() - self._extra_width, 0,
                     self._extra_width, self.height())

    def _sync_extra(self):
        spec = None
        if (not self._testing and self.isVisible()
                and self.plugin_manager is not None):
            spec = self.plugin_manager.get_island_extra()
        has_draw = bool(spec and callable(spec.get('draw')))
        if has_draw:
            try:
                new_w = max(0, min(400, int(spec.get('width', 160))))
            except (TypeError, ValueError):
                new_w = 160
        else:
            spec, new_w = None, 0

        changed = (new_w != self._extra_width)
        self._extra_spec = spec
        self._extra_width = new_w

        if has_draw and not self._extra_timer.isActive():
            self._extra_timer.start()
        elif not has_draw and self._extra_timer.isActive():
            self._extra_timer.stop()

        if changed and self._state == 'compact':
            self._animate_to(self._compact_width(), self.COMPACT_H)
        self.update()

    def refresh_plugins(self):
        self._sync_extra()
        self._last_key = None
        self.update()

    def _extra_hit(self, pos):
        r = self._extra_rect()
        return (not r.isNull()) and r.contains(pos)

    def _animate_to(self, w, h, y=None, on_finished=None):
        """统一的位置/尺寸动画入口（时长随位移自适应）"""
        if y is None:
            y = self.TOP_MARGIN
        self._anim_done_cb = on_finished
        start = self.geometry()
        target = QRect(self._center_x(w), y, w, h)
        self.anim.stop()
        self.anim.setDuration(self._duration_for(start, target))
        self.anim.setStartValue(start)
        self.anim.setEndValue(target)
        self._pin_top()
        self.anim.start()

    def _duration_for(self, start, target):
        d = max(abs(target.width() - start.width()),
                abs(target.height() - start.height()),
                abs(target.y() - start.y()),
                abs(target.x() - start.x()))
        dur = self.ANIM_MIN_MS + d * 0.6
        return int(max(self.ANIM_MIN_MS, min(self.ANIM_MAX_MS, dur)))

    def _on_anim_tick(self, *_):
        # 动画期间只通知几何变化（供副岛跟随），避免每帧 Win32 置顶
        self._notify_geometry()

    def _on_anim_finished(self):
        cb = self._anim_done_cb
        self._anim_done_cb = None
        self._pin_top()
        if cb:
            cb()

    def _pin_top(self, *args):
        if self.isVisible():
            self.raise_()
            _set_topmost(self.winId())
        self._notify_geometry()

    # ---------- 状态 ----------
    def _countdown_sec(self):
        try:
            return max(1, int(self.settings.get("island_countdown_sec", 60)))
        except (TypeError, ValueError):
            return 60

    def _is_countdown(self, status):
        return (status.get('status') == 'upcoming'
                and status.get('until_sec') is not None
                and status['until_sec'] <= self._countdown_sec())

    def _office_in_foreground(self):
        """当前前台是否是 WPS / Office（灵动岛自己除外）"""
        if sys.platform != 'win32':
            return False
        fg = _fg_hwnd()
        if not fg:
            return False
        if _root_hwnd(fg) == int(self.winId()):
            return False
        return _is_office_foreground(fg)

    def _leave_countdown(self):
        """退出倒计时，回默认胶囊状态"""
        self._fill_timer.stop()
        self._countdown_timer.stop()
        self._fill_progress = 0.0
        self._countdown_end = None
        self._stop_click_poll()
        self._state = 'compact'
        self.update()
        self._animate_to(self._compact_width(), self.COMPACT_H)

    # ---------- 强制演示倒计时（测试） ----------
    def start_test_countdown(self, seconds=None):
        """无视当前时刻，强制让灵动岛演示一次倒计时。"""
        try:
            seconds = int(seconds) if seconds else self._countdown_sec()
        except (TypeError, ValueError):
            seconds = self._countdown_sec()
        seconds = max(3, min(600, seconds))

        self._test_timer.stop()
        self._scenario_id += 1
        self._test_phase = None
        if not self.enabled:
            self._test_restore_enabled = False
            self.enabled = True
        else:
            self._test_restore_enabled = None

        if not self.isVisible():
            self.show()
        self._pin_top()
        if self._pulled:
            self._push_up()

        self._testing = True
        self._countdown_dismissed = None
        self._countdown_end = None
        self._state = 'countdown'
        self._fill_progress = 0.0
        self._countdown_window = seconds
        self._fill_clock.restart()
        self._fill_timer.start()
        self._countdown_timer.start()
        self._start_click_poll()

        def _begin():
            if self._testing:
                self._test_timer.start(seconds * 1000)

        self._animate_to(self.COUNTDOWN_W, self.COMPACT_H, on_finished=_begin)
        return True

    def _end_test_countdown(self):
        self._stop_tests()

    def _stop_tests(self):
        """结束全部测试/情景演示并恢复真实状态。"""
        self._scenario_id += 1
        self._test_timer.stop()
        self._test_phase = None
        self._testing = False
        self._fill_timer.stop()
        self._countdown_timer.stop()
        self._fill_progress = 0.0
        self._countdown_end = None
        self._stop_click_poll()
        self._state = 'compact'
        self.update()
        self._animate_to(self._compact_width(), self.COMPACT_H)
        if self._test_restore_enabled is False:
            self._test_restore_enabled = None
            self.enabled = False
            self._go_to_sleep()
        else:
            self._last_status = None
            self._last_key = None
            self._refresh()

    def _abort_demo(self):
        """静默中止演示（不重置为胶囊），供“全屏/Office 收起”时调用。"""
        self._scenario_id += 1
        self._test_timer.stop()
        self._test_phase = None
        self._testing = False
        self._fill_timer.stop()
        self._countdown_timer.stop()
        self._fill_progress = 0.0
        self._countdown_end = None
        self._stop_click_poll()
        if self._test_restore_enabled is False:
            self._test_restore_enabled = None
            self.enabled = False

    # ---------- 整段情景演示（提前 → 倒计时 → 上课 → 下课 → 恢复） ----------
    def start_scenario_test(self, advance_sec, countdown_sec, end_hold_sec,
                            speed=10.0):
        try:
            speed = max(0.1, float(speed))
        except (TypeError, ValueError):
            speed = 10.0
        advance_sec = max(0, int(advance_sec))
        countdown_sec = max(1, int(countdown_sec))
        end_hold_sec = max(0, int(end_hold_sec))

        self._test_timer.stop()
        self._scenario_id += 1
        sid = self._scenario_id

        if not self.enabled:
            self._test_restore_enabled = False
            self.enabled = True
        else:
            self._test_restore_enabled = None
        if not self.isVisible():
            self.show()
        self._pin_top()
        if self._pulled:
            self._push_up()

        self._testing = True
        self._countdown_dismissed = None
        self._scenario_end_hold_ms = end_hold_sec * 1000.0 / speed

        # 阶段1：提前提醒（胶囊文案）
        self._test_phase = 'advance'
        self._state = 'compact'
        self._scenario_advance_total = max(1.0, advance_sec / speed)
        self._scenario_advance_end = time.monotonic() + self._scenario_advance_total
        self.update()
        self._animate_to(self._compact_width(), self.COMPACT_H)
        self._scenario_later(advance_sec * 1000.0 / speed,
                             lambda: self._scenario_start_countdown(
                                 countdown_sec, speed, sid), sid)
        return True

    def _scenario_later(self, ms, fn, sid):
        def cb():
            if sid == self._scenario_id and self._testing:
                fn()
        QTimer.singleShot(int(max(1, ms)), cb)

    def _scenario_start_countdown(self, countdown_sec, speed, sid):
        self._test_phase = 'countdown'
        self._state = 'countdown'
        self._fill_progress = 0.0
        window_s = countdown_sec / speed
        self._countdown_window = max(1.0, window_s)   # 缩放后秒数，蓝条按时长走完
        self._countdown_end = None
        self._fill_clock.restart()
        self._fill_timer.start()
        self._countdown_timer.start()
        self._start_click_poll()
        self._animate_to(self.COUNTDOWN_W, self.COMPACT_H)
        self._scenario_later(window_s * 1000.0,
                             lambda: self._scenario_up_alert(sid), sid)

    def _scenario_up_alert(self, sid):
        self._test_phase = 'up'
        self._countdown_timer.stop()
        self._fill_timer.stop()
        self._stop_click_poll()
        self._show_alert("上课了！", False)
        self._scenario_later(
            self.SCENARIO_ALERT_MS + self._scenario_end_hold_ms,
            lambda: self._scenario_down_alert(sid), sid)

    def _scenario_down_alert(self, sid):
        self._test_phase = 'down'
        self._show_alert("下课了！", True)
        self._scenario_later(self.SCENARIO_ALERT_MS, self._end_scenario, sid)

    def _end_scenario(self):
        self._stop_tests()

    def _countdown_key(self, status):
        return (status.get('course'), status.get('start'),
                datetime.now().strftime('%Y-%m-%d'))

    def _dismiss_countdown(self):
        """收起倒计时，并记下这节课，本轮不再展开。"""
        if self._testing:
            self._test_timer.stop()
            self._end_test_countdown()
            return
        self._countdown_dismissed = self._countdown_key(
            self.schedule.get_status())
        self._leave_countdown()

    def _start_click_poll(self):
        if self._click_timer is not None:
            self._mouse_down = False
            self._click_timer.start()

    def _stop_click_poll(self):
        if self._click_timer is not None:
            self._click_timer.stop()

    def _poll_outside_click(self):
        """系统任意位置左键单击：若在岛外则收起倒计时。"""
        try:
            down = bool(_user32.GetAsyncKeyState(0x01) & 0x8000)
        except Exception:
            return
        rising = down and not self._mouse_down
        self._mouse_down = down
        if not rising:
            return
        if self._state != 'countdown':
            self._stop_click_poll()
            return
        try:
            pt = wintypes.POINT()
            _user32.GetCursorPos(ctypes.byref(pt))
            pos = QPoint(pt.x, pt.y)
        except Exception:
            return
        if not self._hit_island(pos):
            self._dismiss_countdown()

    def _alert_width(self):
        return int(self.settings.get("island_alert_width", 300))

    def _text_for(self, status):
        if self._testing and self._test_phase == 'advance':
            remain = max(0, int(round(
                self._scenario_advance_end - time.monotonic())))
            return f"距离上课 测试 · {remain}s"
        st = status.get('status')
        if self._state == 'countdown':
            if self._testing:
                remain = max(0, int(self._countdown_window
                                    - self._fill_clock.elapsed() / 1000.0))
                base = f"测试倒计时 · {remain}s"
            else:
                base = f"下节 {status['course']} · {status.get('until_sec', 0)}s"
        elif st == 'upcoming':
            base = f"下节 {status['course']} · {status['until_min']}分钟后"
        elif st == 'ongoing':
            base = f"本节：{status['course']} 还剩 {status['remain_min']}分钟"
        elif st == 'holiday':
            name = status.get('name') or ''
            base = f"假期中 · {name}" if name else "假期中"
        elif st == 'none':
            base = "今日无课"
        else:
            base = "今日课程已结束"

        plugin_text = ""
        if self.plugin_manager is not None:
            try:
                plugin_text = self.plugin_manager.get_island_text()
            except Exception:
                plugin_text = ""
        if plugin_text:
            return f"{base} · {plugin_text}"
        return base

    def apply_settings(self):
        self.TOP_MARGIN = int(self.settings.get("island_top_margin", 6))
        self._last_key = None
        if self._pulled:
            self._push_up()
        self.update()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        if not self.enabled:
            if self._pulled:
                self._push_up()
            self._go_to_sleep()
        elif self._state == 'hidden':
            self._wake_up()

    # ---------- 填充动画 ----------
    def _fill_tick(self):
        try:
            self._fill_progress = self._fill_clock.elapsed() / self.FILL_MS
        except Exception:
            self._fill_progress = 1.0
        if self._fill_progress >= 1.0:
            self._fill_progress = 1.0
            self._fill_timer.stop()
        self.update()

    # ---------- 绘制 ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        radius = rect.height() / 2
        path = QPainterPath()
        path.addRoundedRect(0, 0, rect.width(), rect.height(), radius, radius)
        p.fillPath(path, QColor("#1c1c1e"))

        status = self.schedule.get_status()

        if self._state == 'countdown':
            self._paint_countdown_fill(p, path, rect)
            ring_color, ring_ratio = self._countdown_ring()
        else:
            ring_color, ring_ratio = self._ring_spec(status)

        if self._state == 'alert':
            self._paint_alert(p)
        elif self._state == 'mini':
            self._paint_mini(p, status)
        else:
            self._paint_compact(p, status, ring_color, ring_ratio)
            if self._state == 'compact':
                self._paint_extra(p)

    def _paint_extra(self, p):
        spec = self._extra_spec
        if not spec or self._extra_width <= 0:
            return
        r = self._extra_rect()
        if r.width() <= 0 or r.height() <= 0:
            return
        p.setPen(QPen(QColor(255, 255, 255, 45), 1))
        p.drawLine(r.left(), 7, r.left(), self.height() - 8)
        try:
            spec['draw'](p, r, time.monotonic())
        except Exception:
            pass

    # ---------- 倒计时进度与圆环 ----------
    def _countdown_remaining(self):
        window = max(1, self._countdown_window)
        if self._testing:
            sec = window - self._fill_clock.elapsed() / 1000.0
        elif self._countdown_end is not None:
            sec = (self._countdown_end - datetime.now()).total_seconds()
        else:
            sec = self.schedule.get_status().get('until_sec', 0)
        return max(0.0, sec)

    def _countdown_ring(self):
        window = max(1, self._countdown_window)
        remain = self._countdown_remaining()
        return QColor("#4da3ff"), max(0.0, min(1.0, remain / window))

    def _ring_spec(self, status):
        if self._testing and self._test_phase == 'advance':
            total = max(1.0, self._scenario_advance_total)
            remain = max(0.0, self._scenario_advance_end - time.monotonic())
            return QColor("#4da3ff"), max(0.0, min(1.0, remain / total))
        st = status.get('status')
        if st == 'upcoming':
            total = max(1, status.get('advance_sec', 0), self._countdown_sec())
            ratio = status.get('until_sec', 0) / total
            return QColor("#4da3ff"), max(0.0, min(1.0, ratio))
        if st == 'ongoing':
            total = max(1, status.get('duration_sec', 0))
            ratio = status.get('remain_sec', 0) / total
            return QColor("#30d158"), max(0.0, min(1.0, ratio))
        return QColor("#8a8a8e"), 0.0

    def _paint_countdown_fill(self, p, path, rect):
        window = max(1, self._countdown_window)
        remain = self._countdown_remaining()
        ratio = max(0.0, min(1.0, remain / window))
        shown = min(self._fill_progress, ratio)
        if shown <= 0:
            return

        h = rect.height()
        inset = self.BAR_INSET
        bar_h = max(2.0, h - inset * 2)
        r = bar_h / 2
        fill_w = max(0.0, rect.width() * shown)

        p.save()
        p.setClipPath(path)
        p.setPen(Qt.NoPen)

        # 底色蓝条（内缩 + 圆角）
        bar_w = max(0.0, fill_w - inset)
        rr = min(r, bar_w / 2.0)
        bar_rect = QRectF(inset, inset, bar_w, bar_h)
        p.setBrush(QColor("#0a84ff"))
        p.drawRoundedRect(bar_rect, rr, rr)

        # 流光扫过
        phase = (self._anim_clock.elapsed() % self.SHEEN_CYCLE_MS) \
            / self.SHEEN_CYCLE_MS
        sheen_w = max(40.0, fill_w * 0.5)
        cx = -sheen_w + phase * (fill_w + 2 * sheen_w)
        grad = QLinearGradient(cx, 0, cx + sheen_w, 0)
        grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        grad.setColorAt(0.5, QColor(255, 255, 255, 70))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(grad)
        p.drawRoundedRect(bar_rect, rr, rr)

        # 前缘彗星光晕
        head_x = inset + fill_w
        glow_w = min(20.0, max(8.0, bar_h))
        g2 = QLinearGradient(head_x - glow_w, 0, head_x, 0)
        g2.setColorAt(0.0, QColor(120, 200, 255, 0))
        g2.setColorAt(1.0, QColor(150, 210, 255, 200))
        p.setBrush(g2)
        p.drawRoundedRect(
            QRectF(max(inset, head_x - glow_w), inset, glow_w, bar_h), r, r)

        # 前缘亮点
        p.setBrush(QColor(235, 245, 255, 230))
        p.drawEllipse(QPointF(head_x - r, h / 2.0), r * 0.6, r * 0.6)
        p.restore()

    def _paint_alert(self, p):
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(16)
        font.setBold(True)
        p.setFont(font)
        color = QColor("#ffffff") if self._alert_is_end else QColor("#30d158")
        p.setPen(color)
        p.drawText(self.rect(), Qt.AlignCenter, self._alert_text)

    def _paint_compact(self, p, status, ring_color, ring_ratio):
        ring_x = 6
        ring_y = (self.COMPACT_H - self.RING_SIZE) // 2
        self._draw_ring(p, ring_x, ring_y, self.RING_SIZE,
                        ring_color, ring_ratio)

        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(14)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("white"))

        text_x = ring_x + self.RING_SIZE + 8
        right_margin = self._extra_width + 10 if self._extra_width > 0 else 10
        text_rect = self.rect().adjusted(text_x, 0, -right_margin, 0)

        if self._roll_active and self._old_text and self._new_text:
            self._draw_rolling_text(p, text_rect)
        else:
            p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                       self._text_for(status))

    def _draw_rolling_text(self, p, text_rect):
        h = text_rect.height()
        t = max(0.0, min(1.0, self._roll_progress))
        offset = int(t * h)
        old_op = max(0.0, 1.0 - 1.5 * t)
        new_op = max(0.0, 1.5 * t - 0.5)

        p.save()
        p.setOpacity(old_op)
        old_rect = QRect(text_rect.x(), text_rect.y() - offset,
                         text_rect.width(), text_rect.height())
        p.drawText(old_rect, Qt.AlignVCenter | Qt.AlignLeft, self._old_text)
        p.restore()

        p.save()
        p.setOpacity(new_op)
        new_rect = QRect(text_rect.x(), text_rect.y() + (h - offset),
                         text_rect.width(), text_rect.height())
        p.drawText(new_rect, Qt.AlignVCenter | Qt.AlignLeft, self._new_text)
        p.restore()

    def _draw_ring(self, p, x, y, size, color, ratio):
        p.setPen(QPen(QColor("#3a3a3c"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(x + 2, y + 2, size - 4, size - 4)

        ratio = max(0.0, min(1.0, ratio))
        if ratio > 0:
            p.setPen(QPen(color, 2))
            p.drawArc(x + 2, y + 2, size - 4, size - 4,
                      90 * 16, int(-360 * 16 * ratio))

    def _paint_mini(self, p, status):
        st = status.get('status')
        color = QColor({'ongoing': '#30d158',
                        'upcoming': '#4da3ff'}.get(st, '#8a8a8e'))
        cx, cy = self.width() // 2, self.height() // 2
        r = 6
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

    # ---------- 顶掉 ----------
    def _start_text_roll(self, old_text, new_text):
        if not self.settings.get("anim_fade_text", True):
            self.update()
            return
        self._old_text = old_text
        self._new_text = new_text
        self._roll_progress = 0.0
        self._roll_active = True
        self._roll_clock.restart()
        self._roll_timer.start()

    def _roll_tick(self):
        try:
            self._roll_progress = self._roll_clock.elapsed() / self.TEXT_ROLL_MS
        except Exception:
            self._roll_progress = 1.0
        if self._roll_progress >= 1.0:
            self._roll_progress = 1.0
            self._roll_timer.stop()
            self._roll_active = False
        self.update()

    # ---------- 下拉面板 ----------
    def _collect_specs(self):
        left, right = [], []

        if self.plugin_manager:
            for s in self.plugin_manager.get_panel_specs():
                s.setdefault('min_width', self.PANEL_MIN_W)
                s.setdefault('order', 100)
                s.setdefault('position', 'left')
                if s['position'] == 'right':
                    right.append(s)
                else:
                    left.append(s)

        left.sort(key=lambda s: s.get('order', 100))
        right.sort(key=lambda s: s.get('order', 100))

        schedule_spec = self._make_schedule_spec()
        return left, schedule_spec, right

    def _make_schedule_spec(self):
        today = self.schedule.get_today()
        periods = self.schedule.periods_for()
        status = self.schedule.get_status()
        cur = status.get('index', -1)

        lines = []
        for i, p in enumerate(periods):
            course = today[i] if i < len(today) else ""
            if course and course.strip():
                mark = "▶ " if i == cur else "  "
                start = self.schedule.offset_time_str(p['start'])
                lines.append(f"{mark}{course}  {start}")

        if status.get('status') == 'holiday':
            name = status.get('name') or ''
            text = f"假期中 · {name}" if name else "假期中"
        else:
            text = "\n".join(lines) if lines else "今天没有课"
        line_count = max(1, len(lines))
        h = 20 + line_count * 22 + 14
        return {
            'text': text,
            'width': self.SCHEDULE_DEFAULT_W,
            'min_width': self.SCHEDULE_MIN_W,
            'height': h,
            'is_schedule': True,
        }

    def _layout(self, left, mid, right):
        all_specs = left + [mid] + right
        max_total = int(self.screen_w * self.MAX_TOTAL_RATIO)

        widths = []
        for s in all_specs:
            w = int(s.get('width', 180))
            w = max(s.get('min_width', self.PANEL_MIN_W), w)
            if s.get('is_schedule'):
                w = min(self.SCHEDULE_DEFAULT_W, w)
            else:
                w = min(self.PANEL_MAX_W, w)
            widths.append(w)

        def total(ws):
            return sum(ws) + self.PANEL_GAP * (len(ws) - 1)

        sched_idx = len(left)
        if total(widths) > max_total and sched_idx < len(widths):
            overflow = total(widths) - max_total
            shrink = min(overflow, widths[sched_idx] - self.SCHEDULE_MIN_W)
            widths[sched_idx] -= shrink

        if total(widths) > max_total:
            overflow = total(widths) - max_total
            for i in range(len(widths)):
                if overflow <= 0:
                    break
                if i == sched_idx:
                    continue
                shrink = min(overflow, widths[i] - self.PANEL_MIN_W)
                widths[i] -= shrink
                overflow -= shrink

        while total(widths) > max_total and len(all_specs) > 1:
            all_specs.pop()
            widths.pop()

        if not all_specs:
            return []

        total_w = total(widths)
        start_x = self._center_x(total_w)
        y_top = self.TOP_MARGIN + self.COMPACT_H + self.PANEL_GAP

        rects = []
        x = start_x
        for spec, w in zip(all_specs, widths):
            rects.append({
                'spec': spec, 'x': x, 'y': y_top, 'w': w,
                'h': spec.get('height', 40),
            })
            x += w + self.PANEL_GAP
        return rects

    def _total_panel_width(self):
        if not self._panel_rects:
            return self._compact_width()
        return sum(r['w'] for r in self._panel_rects) + \
               self.PANEL_GAP * (len(self._panel_rects) - 1)

    def _pull_down(self):
        if self._pulled or self._state != 'compact':
            return
        self._pulled = True

        left, mid, right = self._collect_specs()
        rects = self._layout(left, mid, right)
        if not rects:
            self._pulled = False
            return

        self._panel_rects = rects
        self._panels = []
        fade = bool(self.settings.get("anim_fade_panel", True))
        for r in rects:
            pw = PanelWindow(r['w'], r['h'], fade=fade)
            pw.set_content(r['spec'].get('text', ''))
            pw.place(r['x'], r['y'])
            self._panels.append(pw)

        target_w = self._total_panel_width()
        self._animate_to(target_w, self.COMPACT_H,
                         on_finished=self._stagger_panels_in)

    def _stagger_panels_in(self):
        for i, pw in enumerate(self._panels):
            QTimer.singleShot(i * self.PANEL_STAGGER, pw.animate_in)

        last_delay = (len(self._panels) - 1) * self.PANEL_STAGGER + 240
        QTimer.singleShot(last_delay, self._setup_scroll)
        QTimer.singleShot(last_delay,
                          lambda: self._pull_timer.start(self.PULL_HOLD_MS))

    def _setup_scroll(self):
        if not self._panel_rects:
            return
        max_bottom = max(r['y'] + r['h'] for r in self._panel_rects)
        top_limit = self.TOP_MARGIN + self.COMPACT_H + self.PANEL_GAP
        max_allowed = int(self.screen_h * self.MAX_HEIGHT_RATIO)

        if max_bottom <= top_limit + max_allowed:
            return

        bottom_y = top_limit + max_allowed
        total_w = self._total_panel_width()
        x = self._center_x(total_w)
        self._fade_mask = FadeMask(total_w, 24)
        self._fade_mask.move(x, bottom_y - 24)
        self._fade_mask.show()

        self._scroll_max = max_bottom - bottom_y
        self._scroll_offset = 0

    def _push_up(self):
        self._pull_timer.stop()

        if not self._pulled:
            return
        self._pulled = False

        if self._fade_mask:
            self._fade_mask.hide()
            self._fade_mask.deleteLater()
            self._fade_mask = None

        if not self._panels:
            self._after_panels_out()
            return

        done = [0]
        total = len(self._panels)

        def on_done():
            done[0] += 1
            if done[0] >= total:
                self._after_panels_out()

        for pw in self._panels:
            pw.animate_out(on_done=on_done)

    def _after_panels_out(self):
        for pw in self._panels:
            try:
                pw.close()
                pw.deleteLater()
            except Exception:
                pass
        self._panels = []
        self._panel_rects = []
        self._scroll_offset = 0
        self._scroll_max = 0
        self._animate_to(self._compact_width(), self.COMPACT_H)

    def _do_scroll(self, delta):
        if not self._pulled or self._scroll_max <= 0:
            return
        new_offset = max(-self._scroll_max,
                         min(0, self._scroll_offset + delta))
        if new_offset == self._scroll_offset:
            return
        self._scroll_offset = new_offset
        for pw in self._panels:
            pw.set_scroll(self._scroll_offset)

        if self._fade_mask:
            top_limit = self.TOP_MARGIN + self.COMPACT_H + self.PANEL_GAP
            max_allowed = int(self.screen_h * self.MAX_HEIGHT_RATIO)
            new_y = top_limit + max_allowed + self._scroll_offset - 24
            self._fade_mask.move(self._fade_mask.x(), new_y)

    def wheelEvent(self, event):
        self._do_scroll(-event.angleDelta().y() // 2)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and self._pulled:
            try:
                pos = event.globalPosition().toPoint()
            except Exception:
                return super().eventFilter(obj, event)
            for pw in self._panels:
                if pw.frameGeometry().contains(pos):
                    self._do_scroll(-event.angleDelta().y() // 2)
                    return True

        if event.type() == QEvent.MouseButtonPress and self._pulled:
            try:
                pos = event.globalPosition().toPoint()
            except Exception:
                return super().eventFilter(obj, event)
            if not self._hit_island(pos):
                self._push_up()

        return super().eventFilter(obj, event)

    def _hit_island(self, pos):
        if self.frameGeometry().contains(pos):
            return True
        for pw in self._panels:
            if pw.frameGeometry().contains(pos):
                return True
        return False

    # ---------- 提醒 ----------
    def notify(self, text, is_end=False):
        if not self.enabled:
            return
        self._show_alert(str(text), bool(is_end))

    def _show_alert(self, text, is_end):
        self._fill_timer.stop()
        self._countdown_timer.stop()
        self._fill_progress = 0.0
        self._countdown_end = None
        self._alert_text = text
        self._alert_is_end = is_end
        self._state = 'alert'
        self.update()

        w = self._alert_width()
        hold = int(self.settings.get("island_alert_hold_ms", 600))

        self._animate_to(w, self.COMPACT_H,
                         on_finished=lambda: QTimer.singleShot(
                             hold, self._alert_return))

    def _alert_return(self):
        """平滑回收到胶囊宽度（不再收到 0 宽）"""
        self._state = 'compact'
        self.update()
        self._animate_to(self._compact_width(), self.COMPACT_H)

    # ---------- 唤醒/休眠 ----------
    def _on_start(self):
        self._wake_up()

    def _wake_up(self):
        if not self.enabled:
            return
        if self._state != 'hidden':
            return
        self.setGeometry(self._center_x(self.MINI_W), -self.COMPACT_H - 24,
                         self.MINI_W, self.COMPACT_H)
        self._state = 'mini'
        self.update()
        if self.settings.get("island_show_wakeup_anim", True):
            self._animate_to(self.MINI_W, self.COMPACT_H,
                             on_finished=self._wakeup_step2)
        else:
            self._state = 'compact'
            self._animate_to(self._compact_width(), self.COMPACT_H)

    def _wakeup_step2(self):
        if self._state != 'mini':
            return
        QTimer.singleShot(self.STEP_GAP_MS, self._wakeup_step2_anim)

    def _wakeup_step2_anim(self):
        if self._state != 'mini':
            return
        self._state = 'compact'
        self.update()
        self._animate_to(self._compact_width(), self.COMPACT_H)

    def _go_to_sleep(self):
        if self._state == 'hidden':
            return
        self._fill_timer.stop()
        self._countdown_timer.stop()
        self._fill_progress = 0.0
        self._countdown_end = None
        self._stop_click_poll()
        if self._pulled:
            self._push_up()
        self._state = 'mini'
        self._animate_to(self.MINI_W, self.COMPACT_H,
                         on_finished=lambda: QTimer.singleShot(
                             600, self._slide_out))

    def _slide_out(self):
        if self._state != 'mini':
            return
        self._state = 'hidden'
        self._animate_to(self.MINI_W, self.COMPACT_H, -self.COMPACT_H - 24)

    # ---------- 前台检测 ----------
    def _check_foreground(self):
        if not self.enabled:
            return
        fg = _fg_hwnd()
        if not fg:
            return
        if _root_hwnd(fg) == int(self.winId()):
            return

        # 倒计时期间切到 WPS / Office → 退出进度条，回默认状态（演示中则中止）
        if self._state == 'countdown' and _is_office_foreground(fg):
            if self._testing:
                self._abort_demo()
            self._leave_countdown()
            return

        # 只要全屏就收起来（演示中则中止演示后收起，回到正常课表）
        if _is_fullscreen(fg):
            if not self.settings.get("island_hide_on_fullscreen", True):
                return
            if self._testing:
                self._abort_demo()
            if self._state == 'hidden':
                return
            self._go_to_sleep()
            return

        if self._state == 'hidden':
            self._wake_up()

    def _maybe_holiday_reminder(self):
        """放假前最后一个上学日的最后一节课下课后，弹一次“放假啦”。"""
        try:
            now = datetime.now()
            d = now.date()
            if not self.schedule.is_last_school_day_before_holiday(d):
                return False
            key = d.strftime('%Y-%m-%d')
            if self._holiday_alerted_date == key:
                return False
            end = self.schedule.last_course_end_today(now)
            if end is None or now < end:
                return False
            self._holiday_alerted_date = key
            self._show_alert("放假啦！", is_end=True)
            return True
        except Exception:
            return False

    # ---------- 定时刷新 ----------
    def _refresh(self):
        if self._state == 'hidden':
            self._last_key = None
            self._sync_extra()
            return
        if self._testing:
            return
        self._sync_extra()

        status = self.schedule.get_status()
        prev = self._last_status
        self._last_status = status

        if self._maybe_holiday_reminder():
            return

        if self._state == 'alert':
            self.update()
            return

        # 状态切换（下课不展示提醒）
        if prev is not None:
            p_st = prev.get('status')
            n_st = status.get('status')
            if p_st == 'ongoing' and n_st in ('upcoming', 'done'):
                if self._pulled:
                    self._push_up()
            elif p_st == 'upcoming' and n_st == 'ongoing':
                if self._pulled:
                    self._push_up()
                self._show_alert("上课了！", is_end=False)
                return

        # 倒计时（WPS / Office 在前台时不进入；已收起的这节课不再展开）
        if (self._is_countdown(status)
                and not self._office_in_foreground()
                and self._countdown_key(status) != self._countdown_dismissed):
            if self._state != 'countdown':
                if self._pulled:
                    self._push_up()
                self._state = 'countdown'
                self._fill_progress = 0.0
                self._countdown_window = self._countdown_sec()
                self._countdown_end = datetime.now() + timedelta(
                    seconds=status.get('until_sec', self._countdown_window))
                self._fill_timer.start()
                self._countdown_timer.start()
                self._start_click_poll()
                self._animate_to(self.COUNTDOWN_W, self.COMPACT_H)
        elif self._state == 'countdown':
            self._leave_countdown()

        # 内容变化
        new_key = (status.get('status'), status.get('course'),
                   status.get('until_min'), status.get('remain_min'),
                   status.get('until_sec'), self._state)
        if new_key == self._last_key:
            return

        old_key = self._last_key
        self._last_key = new_key

        if (old_key and self._state == 'compact'
                and old_key[0] == new_key[0]
                and old_key[1] == new_key[1]
                and old_key[2:4] != new_key[2:4]):
            old_text = self._text_from_key(old_key)
            new_text = self._text_from_key(new_key)
            if old_text and new_text and old_text != new_text:
                self._start_text_roll(old_text, new_text)
                return

        self.update()

    def _text_from_key(self, key):
        st = key[0]
        course = key[1]
        if st == 'upcoming':
            return f"下节 {course} · {key[2]}分钟后"
        if st == 'ongoing':
            return f"本节：{course} 还剩 {key[3]}分钟"
        if st == 'none':
            return "今日无课"
        return "今日课程已结束"

    # ---------- 交互 ----------
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._state in ('hidden', 'countdown', 'alert', 'mini'):
            return

        if self._state == 'compact' and self._extra_spec is not None:
            if self._extra_hit(event.position().toPoint()):
                cb = self._extra_spec.get('on_click')
                if callable(cb):
                    try:
                        cb()
                    except Exception:
                        pass
                return

        if self._pulled:
            self._push_up()
        else:
            self._pull_down()

    def contextMenuEvent(self, event):
        m = QMenu(self)
        m.addAction("关闭灵动岛", self.close)
        m.exec(event.globalPos())

    def closeEvent(self, event):
        self._scenario_id += 1
        self._testing = False
        timers = [self.tick_timer, self.pin_timer, self._fill_timer,
                  self._roll_timer, self._pull_timer, self._test_timer,
                  self._countdown_timer, self._extra_timer,
                  getattr(self, 'watch_timer', None), self._click_timer]
        for timer in timers:
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass
        for pw in self._panels:
            try:
                pw.close()
                pw.deleteLater()
            except Exception:
                pass
        self._panels = []
        self._panel_rects = []
        if self._fade_mask is not None:
            try:
                self._fade_mask.hide()
                self._fade_mask.deleteLater()
            except Exception:
                pass
            self._fade_mask = None
        try:
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
        except Exception:
            pass
        super().closeEvent(event)