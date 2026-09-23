import sys
import os
import ctypes
from ctypes import wintypes
from datetime import datetime

from PySide6.QtWidgets import QWidget, QMenu, QApplication
from PySide6.QtCore import (Qt, QTimer, QRect, QPropertyAnimation,
                            QEasingCurve, QEvent)
from PySide6.QtGui import QPainter, QColor, QPainterPath, QFont, QPen

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
    ANIM_MS = 200
    STEP_GAP_MS = 60
    WATCH_INTERVAL = 400
    TEXT_ROLL_MS = 140
    FILL_MS = 180            # 进度条填充时长
    PULL_HOLD_MS = 3000      # 下拉后停留 3 秒自动收回

    DEBUG = False

    def __init__(self, schedule_manager, settings, plugin_manager=None):
        super().__init__()
        self.schedule = schedule_manager
        self.settings = settings
        self.plugin_manager = plugin_manager
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
        self._fill_timer = QTimer(self)
        self._fill_timer.setInterval(16)
        self._fill_timer.timeout.connect(self._fill_tick)

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

        # 定时器
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(self.ANIM_MS)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._pin_top)
        self.anim.finished.connect(self._on_anim_finished)

        self._roll_timer = QTimer(self)
        self._roll_timer.setInterval(16)
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

        if sys.platform == 'win32':
            self.watch_timer = QTimer(self)
            self.watch_timer.timeout.connect(self._check_foreground)
            self.watch_timer.start(self.WATCH_INTERVAL)

        QApplication.instance().installEventFilter(self)
        QTimer.singleShot(200, self._on_start)

    # ---------- 位置 ----------
    def _center_x(self, w):
        return self.screen_w // 2 - w // 2

    def _move_to(self, w, h, y):
        self.setGeometry(self._center_x(w), y, w, h)

    def _animate_to(self, w, h, y=None, on_finished=None):
        """统一的位置/尺寸动画入口"""
        if y is None:
            y = self.TOP_MARGIN
        self._anim_done_cb = on_finished
        self.anim.stop()
        self.anim.setStartValue(self.geometry())
        self.anim.setEndValue(QRect(self._center_x(w), y, w, h))
        self._pin_top()
        self.anim.start()

    def _on_anim_finished(self):
        cb = self._anim_done_cb
        self._anim_done_cb = None
        if cb:
            cb()

    def _pin_top(self, *args):
        if self.isVisible():
            self.raise_()
            _set_topmost(self.winId())

    # ---------- 状态 ----------
    def _is_countdown(self, status):
        return (status.get('status') == 'upcoming'
                and status.get('advance_sec', 0) > 0
                and status.get('until_sec') is not None
                and status['until_sec'] <= 60)

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
        self._fill_progress = 0.0
        self._state = 'compact'
        self.update()
        self._animate_to(self.COMPACT_W, self.COMPACT_H)

    def _alert_width(self):
        return int(self.settings.get("island_alert_width", 300))

    def _text_for(self, status):
        st = status.get('status')
        if self._state == 'countdown':
            return f"下节 {status['course']} · {status.get('until_sec', 0)}s"
        if st == 'upcoming':
            return f"下节 {status['course']} · {status['until_min']}分钟后"
        if st == 'ongoing':
            return f"本节：{status['course']} 还剩 {status['remain_min']}分钟"
        if st == 'none':
            return "今日无课"
        return "今日课程已结束"

    def _apply_settings(self):
        self.TOP_MARGIN = int(self.settings.get("island_top_margin", 6))
        self._last_key = None
        if self._pulled:
            self._push_up()
        self.update()

    # ---------- 填充动画 ----------
    def _fill_tick(self):
        self._fill_progress += 16.0 / self.FILL_MS
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

        # 进度条：以进入倒计时那一刻的秒数为分母，才能从满格开始
        if self._state == 'countdown':
            sec = status.get('until_sec', 0)
            window = max(1, self._countdown_window)
            ratio = max(0.0, min(1.0, sec / window))
            shown = min(self._fill_progress, ratio)
            fill_w = int(rect.width() * shown)
            if fill_w > 0:
                p.save()
                p.setClipPath(path)
                p.fillRect(0, 0, fill_w, rect.height(), QColor("#0a84ff"))
                p.restore()

        if self._state == 'alert':
            self._paint_alert(p)
        elif self._state == 'mini':
            self._paint_mini(p, status)
        else:
            self._paint_compact(p, status)

    def _paint_alert(self, p):
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(16)
        font.setBold(True)
        p.setFont(font)
        color = QColor("#ffffff") if self._alert_is_end else QColor("#30d158")
        p.setPen(color)
        p.drawText(self.rect(), Qt.AlignCenter, self._alert_text)

    def _paint_compact(self, p, status):
        ring_x = 6
        ring_y = (self.COMPACT_H - self.RING_SIZE) // 2
        self._draw_ring(p, ring_x, ring_y, self.RING_SIZE, False, status)

        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(14)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("white"))

        text_x = ring_x + self.RING_SIZE + 8
        text_rect = self.rect().adjusted(text_x, 0, -10, 0)

        if self._roll_active and self._old_text and self._new_text:
            self._draw_rolling_text(p, text_rect)
        else:
            p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                       self._text_for(status))

    def _draw_rolling_text(self, p, text_rect):
        h = text_rect.height()
        offset = int(self._roll_progress * h)

        p.save()
        old_rect = QRect(text_rect.x(), text_rect.y() - offset,
                         text_rect.width(), text_rect.height())
        p.drawText(old_rect, Qt.AlignVCenter | Qt.AlignLeft, self._old_text)
        p.restore()

        p.save()
        new_rect = QRect(text_rect.x(), text_rect.y() + (h - offset),
                         text_rect.width(), text_rect.height())
        p.drawText(new_rect, Qt.AlignVCenter | Qt.AlignLeft, self._new_text)
        p.restore()

    def _draw_ring(self, p, x, y, size, show_num, status):
        st = status.get('status')
        if st == 'upcoming':
            color = QColor("#4da3ff")
            label = str(status.get('until_min', 0))
            advance = status.get('advance_sec', 60) or 60
            ratio = max(0.0, min(1.0, status.get('until_sec', 0) / advance))
        elif st == 'ongoing':
            color = QColor("#30d158")
            label = str(status.get('remain_min', 0))
            ratio = 1.0
        else:
            color = QColor("#8a8a8e")
            label = "—"
            ratio = 0.0

        p.setPen(QPen(QColor("#3a3a3c"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(x + 2, y + 2, size - 4, size - 4)

        if ratio > 0:
            p.setPen(QPen(color, 2))
            p.drawArc(x + 2, y + 2, size - 4, size - 4,
                      90 * 16, int(-360 * 16 * ratio))

        if show_num:
            font = QFont("Microsoft YaHei UI")
            font.setPixelSize(14)
            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor("white"))
            p.drawText(QRect(x, y, size, size), Qt.AlignCenter, label)

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
        self._roll_timer.start()

    def _roll_tick(self):
        self._roll_progress += 16.0 / self.TEXT_ROLL_MS
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
        periods = self.schedule.periods
        status = self.schedule.get_status()
        cur = status.get('index', -1)

        lines = []
        for i, p in enumerate(periods):
            course = today[i] if i < len(today) else ""
            if course and course.strip():
                mark = "▶ " if i == cur else "  "
                lines.append(f"{mark}{course}  {p['start']}")

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
            return self.COMPACT_W
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
        for r in rects:
            pw = PanelWindow(r['w'], r['h'])
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
        self._panels = []
        self._panel_rects = []
        self._scroll_offset = 0
        self._scroll_max = 0
        self._animate_to(self.COMPACT_W, self.COMPACT_H)

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
    def _show_alert(self, text, is_end):
        self._alert_text = text
        self._alert_is_end = is_end
        self._state = 'alert'
        self.update()

        w = self._alert_width()
        hold = int(self.settings.get("island_alert_hold_ms", 600))

        self._animate_to(w, self.COMPACT_H,
                         on_finished=lambda: QTimer.singleShot(
                             hold, self._alert_shrink))

    def _alert_shrink(self):
        self._animate_to(0, self.COMPACT_H,
                         on_finished=lambda: QTimer.singleShot(
                             70, self._alert_expand))

    def _alert_expand(self):
        self._state = 'compact'
        self.update()
        self._animate_to(self.COMPACT_W, self.COMPACT_H)

    # ---------- 唤醒/休眠 ----------
    def _on_start(self):
        self._wake_up()

    def _wake_up(self):
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
            self._animate_to(self.COMPACT_W, self.COMPACT_H)

    def _wakeup_step2(self):
        if self._state != 'mini':
            return
        QTimer.singleShot(self.STEP_GAP_MS, self._wakeup_step2_anim)

    def _wakeup_step2_anim(self):
        if self._state != 'mini':
            return
        self._state = 'compact'
        self.update()
        self._animate_to(self.COMPACT_W, self.COMPACT_H)

    def _go_to_sleep(self):
        if self._state == 'hidden':
            return
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
        fg = _fg_hwnd()
        if not fg:
            return
        if _root_hwnd(fg) == int(self.winId()):
            return

        # 倒计时期间切到 WPS / Office → 退出进度条，回默认状态
        if self._state == 'countdown' and _is_office_foreground(fg):
            self._leave_countdown()
            return

        if _is_fullscreen(fg):
            if not self.settings.get("island_hide_on_fullscreen", True):
                return
            if self._state == 'hidden':
                return
            self._go_to_sleep()
            return

        if self._state == 'hidden':
            self._wake_up()

    # ---------- 定时刷新 ----------
    def _refresh(self):
        if self._state == 'hidden':
            self._last_key = None
            return

        status = self.schedule.get_status()
        prev = self._last_status
        self._last_status = status

        if self._state == 'alert':
            self.update()
            return

        # 状态切换
        if prev is not None:
            p_st = prev.get('status')
            n_st = status.get('status')
            if p_st == 'ongoing' and n_st in ('upcoming', 'done'):
                if self._pulled:
                    self._push_up()
                self._show_alert("下课了！", is_end=True)
                return
            if p_st == 'upcoming' and n_st == 'ongoing':
                if self._pulled:
                    self._push_up()
                self._show_alert("上课了！", is_end=False)
                return

        # 倒计时（WPS / Office 在前台时不进入）
        if self._is_countdown(status) and not self._office_in_foreground():
            if self._state != 'countdown':
                if self._pulled:
                    self._push_up()
                self._state = 'countdown'
                self._fill_progress = 0.0
                self._countdown_window = max(1, status.get('until_sec', 60))
                self._fill_timer.start()
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

        if self._pulled:
            self._push_up()
        else:
            self._pull_down()

    def contextMenuEvent(self, event):
        m = QMenu(self)
        m.addAction("关闭灵动岛", self.close)
        m.exec(event.globalPos())