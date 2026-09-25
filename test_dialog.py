"""状态测试：叠加「提前 + 倒计时 + 时间偏移」，并可整段演示。"""
import time
from datetime import datetime, timedelta

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QDateTimeEdit, QComboBox,
                               QFrame, QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QDateTime, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPainterPath, QFont, QPen

from ui_common import setup_dialog_style


def _clamp01(v):
    return max(0.0, min(1.0, v))


class IslandPreview(QFrame):
    """按灵动岛样式预览，支持宽度/进度/提醒动画。"""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(46)
        self.setMinimumWidth(260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._text = ""
        self._state = 'none'
        self._ratio = 0.0
        self._width_ratio = 1.0
        self._is_end = False

    def set_state(self, text, state, ratio=0.0, width_ratio=1.0, is_end=False):
        self._text = text
        self._state = state
        self._ratio = _clamp01(ratio)
        self._width_ratio = _clamp01(width_ratio) or 1.0
        self._is_end = is_end
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        full = self.rect()
        cap_w = max(40, int(full.width() * self._width_ratio))
        cap_x = (full.width() - cap_w) / 2.0
        h = full.height()
        radius = h / 2.0

        path = QPainterPath()
        path.addRoundedRect(QRectF(cap_x, 0, cap_w, h), radius, radius)
        p.fillPath(path, QColor('#1c1c1e'))

        if self._state == 'alert':
            font = QFont("Microsoft YaHei UI")
            font.setPixelSize(16)
            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor('#ffffff') if self._is_end else QColor('#30d158'))
            p.drawText(QRectF(cap_x, 0, cap_w, h), Qt.AlignCenter, self._text)
            return

        # 蓝色进度条（倒计时）
        if self._state == 'countdown' and self._ratio > 0:
            p.save()
            p.setClipPath(path)
            bar_w = cap_w * self._ratio
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#0a84ff'))
            rr = min(h / 2.0, bar_w / 2.0)
            p.drawRoundedRect(QRectF(cap_x, 1, max(0.0, bar_w), h - 2), rr, rr)
            p.restore()

        color = QColor({'ongoing': '#30d158',
                        'upcoming': '#4da3ff',
                        'countdown': '#4da3ff'}.get(self._state, '#8a8a8e'))

        ring = 26
        rx = cap_x + 6
        ry = (h - ring) // 2
        p.setPen(QPen(QColor('#3a3a3c'), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(rx + ring / 2, ry + ring / 2),
                      (ring - 4) / 2, (ring - 4) / 2)
        if self._ratio > 0:
            p.setPen(QPen(color, 2))
            p.drawArc(int(rx + 2), int(ry + 2), ring - 4, ring - 4,
                      90 * 16, int(-360 * 16 * self._ratio))
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPointF(rx + ring / 2, ry + ring / 2), 3, 3)

        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(14)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor('white'))
        text_rect = QRectF(rx + ring + 8, 0, cap_x + cap_w - (rx + ring + 8) - 10,
                           h)
        p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self._text)


def _fmt(dt):
    return dt.strftime('%H:%M:%S')


def _fmt_secs(sec):
    sec = int(sec)
    m, s = divmod(max(0, sec), 60)
    return f"{m}分{s:02d}秒"


class StatusTestDialog(QDialog):
    def __init__(self, schedule_manager, settings, controller=None, parent=None):
        super().__init__(parent)
        self.schedule = schedule_manager
        self.settings = settings
        self.controller = controller

        self.setWindowTitle("状态测试")
        self.resize(600, 620)
        setup_dialog_style(self)

        self._demo_running = False
        self._sim_timer = QTimer(self)
        self._sim_timer.setInterval(16)
        self._sim_timer.timeout.connect(self._sim_tick)
        self._sim_start = 0.0

        layout = QVBoxLayout(self)

        # 测试时刻
        row = QHBoxLayout()
        row.addWidget(QLabel("测试时刻："))
        self.dt_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_edit.setCalendarPopup(True)
        self.dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.dt_edit.dateTimeChanged.connect(self._update)
        row.addWidget(self.dt_edit, 1)
        now_btn = QPushButton("现在")
        now_btn.clicked.connect(self._set_now)
        row.addWidget(now_btn)
        layout.addLayout(row)

        # 参数
        params = QHBoxLayout()
        params.addWidget(QLabel("时间偏移(秒)"))
        self.offset = QSpinBox()
        self.offset.setRange(-1800, 1800)
        self.offset.setValue(int(self.schedule.time_offset_seconds))
        self.offset.valueChanged.connect(self._update)
        params.addWidget(self.offset)
        params.addSpacing(10)
        params.addWidget(QLabel("提前(分钟)"))
        self.advance = QSpinBox()
        self.advance.setRange(0, 60)
        self.advance.setValue(int(self.schedule.advance_minutes))
        self.advance.valueChanged.connect(self._update)
        params.addWidget(self.advance)
        params.addSpacing(10)
        params.addWidget(QLabel("倒计时(秒)"))
        self.countdown = QSpinBox()
        self.countdown.setRange(5, 600)
        self.countdown.setValue(
            int(self.settings.get("island_countdown_sec", 60)))
        self.countdown.valueChanged.connect(self._update)
        params.addWidget(self.countdown)
        params.addSpacing(10)
        params.addWidget(QLabel("倍速"))
        self.speed = QComboBox()
        for x in ("1", "5", "10", "20", "30"):
            self.speed.addItem(f"{x}×", int(x))
        self.speed.setCurrentIndex(2)   # 10×
        params.addWidget(self.speed)
        params.addStretch()
        layout.addLayout(params)

        # 预览
        layout.addWidget(QLabel("灵动岛预览："))
        self.preview = IslandPreview()
        layout.addWidget(self.preview)

        # 详情
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.RichText)
        self.detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.detail.setStyleSheet(
            "background:#f7f7f7; border:1px solid #e0e0e0; border-radius:6px;"
            "padding:10px; color:#1b1b1b; font-size:13px;")
        layout.addWidget(self.detail, 1)

        # 按钮
        btns = QHBoxLayout()
        self.demo_btn = QPushButton("开始演示")
        self.demo_btn.clicked.connect(self._start_demo)
        apply_btn = QPushButton("保存到设置")
        apply_btn.clicked.connect(self._save)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(self.demo_btn)
        btns.addWidget(apply_btn)
        btns.addStretch()
        btns.addWidget(close_btn)
        layout.addLayout(btns)

        self._update()

    # ---------- 行为 ----------
    def _set_now(self):
        self.dt_edit.setDateTime(QDateTime.currentDateTime())

    def _save(self):
        self.schedule.set_time_offset_seconds(int(self.offset.value()))
        self.schedule.set_advance_minutes(int(self.advance.value()))
        self.settings["island_countdown_sec"] = int(self.countdown.value())
        self.settings.save()

    def _test_time(self):
        try:
            return self.dt_edit.dateTime().toPython()
        except Exception:
            return datetime.now()

    def _speed_value(self):
        try:
            return max(1.0, float(self.speed.currentData()))
        except (TypeError, ValueError):
            return 10.0

    # ---------- 整段演示 ----------
    def _start_demo(self):
        if self._demo_running:
            return
        advance_sec = int(self.advance.value()) * 60
        countdown_sec = int(self.countdown.value())
        end_hold_sec = 10
        speed = self._speed_value()

        self._advance_s = advance_sec / speed
        self._countdown_s = countdown_sec / speed
        self._hold_s = end_hold_sec / speed
        self._alert_s = 1.0
        self._sim_start = time.monotonic()
        self._demo_running = True
        self.demo_btn.setEnabled(False)

        if self.controller is not None:
            self.controller.run_scenario_test(
                advance_sec, countdown_sec, end_hold_sec, speed)

        self._sim_timer.start()
        self._sim_tick()

    def _sim_tick(self):
        elapsed = time.monotonic() - self._sim_start
        a, c, hold, al = (self._advance_s, self._countdown_s,
                          self._hold_s, self._alert_s)

        if elapsed < a:
            remain = a - elapsed
            self.preview.set_state(
                f"距离上课 测试 · {int(remain)}s", 'upcoming',
                _clamp01(remain / max(1.0, a)), 0.6)
        elif elapsed < a + c:
            remain = a + c - elapsed
            self.preview.set_state(
                f"下节 测试 · {int(remain)}s", 'countdown',
                _clamp01(remain / max(1.0, c)), 1.0)
        elif elapsed < a + c + al + hold:
            self.preview.set_state("上课了！", 'alert', 0.0, 0.9, is_end=False)
        elif elapsed < a + c + al + hold + al:
            self.preview.set_state("下课了！", 'alert', 0.0, 0.9, is_end=True)
        else:
            self._sim_timer.stop()
            self._demo_running = False
            self.demo_btn.setEnabled(True)
            self._update()
        return

    # ---------- 静态预览 ----------
    def _update(self, *_):
        if self._demo_running:
            return
        now = self._test_time()
        offset = int(self.offset.value())
        advance = int(self.advance.value())
        cd_sec = int(self.countdown.value())

        status = self.schedule.get_status(
            now, advance_minutes=advance, offset_seconds=offset)
        st = status.get('status')

        until_sec = status.get('until_sec')
        if (st == 'upcoming' and until_sec is not None and until_sec <= cd_sec):
            island_state = 'countdown'
            text = f"下节 {status['course']} · {until_sec}s"
            ratio = max(0.0, min(1.0, until_sec / max(1, cd_sec)))
            width = 1.0
        elif st == 'upcoming':
            island_state = 'upcoming'
            text = f"下节 {status['course']} · {status['until_min']}分钟后"
            ratio = 0.0
            width = 0.6
        elif st == 'ongoing':
            island_state = 'ongoing'
            text = f"本节：{status['course']} 还剩 {status['remain_min']}分钟"
            ratio = 1.0
            width = 1.0
        elif st == 'holiday':
            island_state = 'none'
            nm = status.get('name') or ''
            text = f"假期中 · {nm}" if nm else "假期中"
            ratio = 0.0
            width = 0.6
        elif st == 'none':
            island_state = 'none'
            text = "今日无课"
            ratio = 0.0
            width = 0.6
        else:
            island_state = 'done'
            text = "今日课程已结束"
            ratio = 0.0
            width = 0.6

        self.preview.set_state(text, island_state, ratio, width)

        lines = [
            f"<b>状态：</b>{island_state}（schedule={st}）",
            f"<b>岛文案：</b>{text}",
            f"<b>测试时刻：</b>{_fmt(now)}",
            f"<b>参数：</b>偏移 {offset:+d}s，提前 {advance} 分，"
            f"倒计时窗口 {cd_sec}s，倍速 {int(self._speed_value())}×",
        ]

        idx = status.get('index')
        periods = self.schedule.periods_for(now)
        if idx is not None and 0 <= idx < len(periods):
            p = periods[idx]
            base = now.replace(second=0, microsecond=0)
            try:
                ph, pm = str(p['start']).split(':')
                printed = base.replace(hour=int(ph), minute=int(pm))
            except Exception:
                printed = None
            if printed is not None:
                effective = printed + timedelta(seconds=offset) - timedelta(
                    minutes=advance)
                cd_at = effective - timedelta(seconds=cd_sec)
                lines.append(f"<b>课程：</b>{status.get('course')} "
                             f"（{p.get('name','')}）")
                lines.append(f"<b>课表时间：</b>{p['start']} - {p['end']}")
                lines.append(f"<b>有效上课：</b>{_fmt(effective)}"
                             f"（提前 {advance} 分 / 偏移 {offset}s）")
                lines.append(f"<b>进入倒计时：</b>{_fmt(cd_at)}")
        if st == 'upcoming' and until_sec is not None:
            lines.append(f"<b>距上课：</b>{_fmt_secs(until_sec)}")
        elif st == 'ongoing':
            lines.append(f"<b>距下课：</b>{_fmt_secs(status.get('remain_sec', 0))}")

        self.detail.setText("<br>".join(lines))

    def closeEvent(self, event):
        self._sim_timer.stop()
        super().closeEvent(event)
