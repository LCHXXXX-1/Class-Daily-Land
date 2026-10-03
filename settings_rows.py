"""设置项描述符与行控件（全新实现）。

SettingRow 以数据方式描述一个设置项；RowWidget 生成
「左：标题 / 说明，右：控件」的标准行，并负责：

- 变更即时写回（SettingsManager 或自定义 setter）并通知宿主应用
- 从当前配置刷新控件（用于「恢复默认」）
- 提供搜索文本与定位高亮
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QHBoxLayout,
                               QLabel, QSlider, QSpinBox, QVBoxLayout,
                               QWidget)

from settings_manager import DEFAULTS
from settings_widgets import SegmentedControl, ToggleSwitch


class SettingRow:
    """一个设置项的描述（不含控件）。"""

    def __init__(self, key, title, kind, *, hint="", options=None,
                 vmin=0, vmax=100, suffix="", decimals=0, step=None,
                 scale=1.0, get=None, setv=None, default=None, keywords=""):
        self.key = key                  # settings.json 键；'' 表示非持久项
        self.title = title
        self.kind = kind                # switch/segmented/spin/dspin/slider/combo
        self.hint = hint
        self.options = options or []    # segmented/combo: [(显示文本, 数据)]
        self.vmin = vmin
        self.vmax = vmax
        self.suffix = suffix
        self.decimals = decimals
        self.step = step
        self.scale = scale              # 控件值 × scale = 存储值
        self.getter = get               # 自定义读取（返回存储值）
        self.setter = setv              # 自定义写入（参数为存储值）
        self.default = default          # 非持久项的默认值
        self.keywords = keywords

    @property
    def has_default(self):
        if self.default is not None:
            return True
        return bool(self.key) and self.key in DEFAULTS

    def default_value(self):
        if self.default is not None:
            return self.default
        return DEFAULTS.get(self.key)


class RowWidget(QWidget):
    """设置项的一行。ctx 需提供 .settings 与 .on_row_change(row_widget)。"""

    def __init__(self, row, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("rowWidget")
        self.row = row
        self.ctx = ctx
        self._loading = False
        self._flash_timer = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(2)
        title = QLabel(row.title)
        title.setObjectName("rowTitle")
        left.addWidget(title)
        if row.hint:
            hint = QLabel(row.hint)
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            left.addWidget(hint)
        lay.addLayout(left, 1)

        right = QHBoxLayout()
        right.setSpacing(8)
        self.control = self._build_control()
        right.addStretch(1)
        right.addWidget(self.control, 0, Qt.AlignVCenter)
        lay.addLayout(right, 0)

        self.search_text = " ".join((row.title, row.hint, row.keywords,
                                     str(row.key or ""))).lower()
        self.refresh()

    # ---------- 控件构建 ----------
    def _build_control(self):
        r = self.row
        if r.kind == "switch":
            w = ToggleSwitch()
            w.toggled.connect(lambda on: self._commit(bool(on)))
            return w

        if r.kind == "segmented":
            w = SegmentedControl(r.options)
            w.changed.connect(lambda v: self._commit(v))
            return w

        if r.kind == "spin":
            w = QSpinBox()
            w.setRange(int(r.vmin), int(r.vmax))
            if r.step:
                w.setSingleStep(int(r.step))
            w.setSuffix(r.suffix)
            w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            w.valueChanged.connect(
                lambda v: self._commit(v * r.scale if r.scale != 1.0 else v))
            return w

        if r.kind == "dspin":
            w = QDoubleSpinBox()
            w.setRange(float(r.vmin), float(r.vmax))
            w.setDecimals(r.decimals)
            if r.step:
                w.setSingleStep(float(r.step))
            w.setSuffix(r.suffix)
            w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            w.valueChanged.connect(
                lambda v: self._commit(v * r.scale if r.scale != 1.0 else v))
            return w

        if r.kind == "slider":
            box = QWidget()
            bl = QHBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(10)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(int(r.vmin), int(r.vmax))
            slider.setSingleStep(int(r.step or 1))
            slider.setMinimumWidth(170)
            val = QLabel()
            val.setMinimumWidth(46)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val.setObjectName("rowTitle")
            slider.valueChanged.connect(lambda v: self._on_slider(v))
            bl.addWidget(slider, 1)
            bl.addWidget(val)
            box._slider = slider
            box._label = val
            return box

        if r.kind == "combo":
            w = QComboBox()
            for text, data in r.options:
                w.addItem(text, data)
            w.currentIndexChanged.connect(
                lambda _=0: self._commit(w.currentData()))
            return w

        raise ValueError(f"未知控件类型: {r.kind}")

    # ---------- 读写 ----------
    def _read_stored(self):
        r = self.row
        if r.getter is not None:
            return r.getter()
        if not r.key:
            return r.default_value()
        return self.ctx.settings.get(r.key)

    def value(self):
        r = self.row
        c = self.control
        if r.kind == "switch":
            return bool(c.isChecked())
        if r.kind == "segmented":
            return c.value()
        if r.kind == "spin":
            raw = int(c.value())
        elif r.kind == "dspin":
            raw = float(c.value())
        elif r.kind == "slider":
            return float(c._slider.value()) * r.scale
        elif r.kind == "combo":
            return c.currentData()
        else:
            return None
        return raw * r.scale if r.scale != 1.0 else raw

    def _on_slider(self, v):
        self.control._label.setText(f"{int(v)}{self.row.suffix}")
        self._commit(v * self.row.scale)

    def _commit(self, value):
        if self._loading:
            return
        r = self.row
        if r.setter is not None:
            r.setter(value)
        elif r.key:
            self.ctx.settings[r.key] = value
        self.ctx.on_row_change(self)

    # ---------- 显示刷新 ----------
    def refresh(self):
        r = self.row
        value = self._read_stored()
        if value is None:
            value = r.default_value()
        self._loading = True
        try:
            c = self.control
            if r.kind == "switch":
                c.set_state(bool(value))
            elif r.kind == "segmented":
                c.set_value(value, animate=False)
            elif r.kind == "spin":
                c.setValue(int(round(float(value) / (r.scale or 1.0))))
            elif r.kind == "dspin":
                c.setValue(float(value) / (r.scale or 1.0))
            elif r.kind == "slider":
                iv = int(round(float(value) / (r.scale or 1.0)))
                iv = max(c._slider.minimum(), min(c._slider.maximum(), iv))
                c._slider.setValue(iv)
                c._label.setText(f"{iv}{r.suffix}")
            elif r.kind == "combo":
                idx = c.findData(value)
                if idx >= 0:
                    c.setCurrentIndex(idx)
        finally:
            self._loading = False

    def load_default(self):
        """恢复默认值并写回；返回是否有默认值。"""
        r = self.row
        if not r.has_default:
            return False
        value = r.default_value()
        if r.setter is not None:
            r.setter(value)
        elif r.key:
            self.ctx.settings[r.key] = value
        self.refresh()
        return True

    # ---------- 搜索定位高亮 ----------
    def flash(self):
        self.setProperty("flash", True)
        self.style().unpolish(self)
        self.style().polish(self)
        if self._flash_timer is not None:
            self._flash_timer.stop()
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._unflash)
        self._flash_timer.start(1300)

    def _unflash(self):
        self.setProperty("flash", False)
        self.style().unpolish(self)
        self.style().polish(self)
