"""媒体播放插件：通过 Windows PowerShell(WinRT SMTC) 获取正在播放的媒体并在岛上显示。

- 无需任何第三方包；脚本运行时自动生成到插件数据目录。
- 可设置显示在主岛（加长一段）或副岛（替换天气内容）。
- 点击岛上的媒体片段 = 播放/暂停切换。
- 媒体停止后 hide_after_sec 秒自动隐藏。
- 上课期间：隐藏整个插件并停止 PowerShell 轮询进程；下课后自动恢复。
"""
import os
import sys
import json
import time
import tempfile
import threading
import subprocess

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QComboBox,
                               QSpinBox, QCheckBox, QLabel, QHBoxLayout,
                               QPushButton)

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
from builtin.data import builtin_dir as _builtin_dir  # noqa: E402
_CONFIG_PATH = os.path.join(_builtin_dir('audio'), 'config.json')

_PS = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'),
                   'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
_HAS_PS = (sys.platform == 'win32' and os.path.isfile(_PS))
_CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

_DEFAULTS = {
    "enabled": True,
    "show_on": "main",       # main / sub
    "hide_after_sec": 5,
    "show_title": True,
    "max_width": 240,
}

# ---------------- PowerShell 脚本 ----------------
_PS_HEADER = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $ty) {
  $m = $asTaskGeneric.MakeGenericMethod($ty)
  $t = $m.Invoke($null, @($op))
  $t.Wait(-1) | Out-Null
  $t.Result
}
$mgrType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]
$propsType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media.Control, ContentType=WindowsRuntime]
function Get-Mgr() { Await ($mgrType::RequestAsync()) ($mgrType) }
"""

_POLL_PS = 'param([int]$ParentPid = 0)\n' + _PS_HEADER + r"""
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$mgr = Get-Mgr
while ($true) {
  # 父进程已退出（如主程序崩溃）时自动退出，避免成为孤儿进程
  if ($ParentPid -gt 0) {
    $parent = Get-Process -Id $ParentPid -ErrorAction SilentlyContinue
    if ($null -eq $parent) { exit }
  }
  $o = @{ title = ''; artist = ''; status = 'none' }
  try {
    $s = $mgr.GetCurrentSession()
    if ($s -ne $null) {
      $p = Await ($s.TryGetMediaPropertiesAsync()) ($propsType)
      $st = [int]$s.GetPlaybackInfo().PlaybackStatus
      if ($st -eq 4) { $o.status = 'playing' }
      elseif ($st -eq 5) { $o.status = 'paused' }
      else { $o.status = 'other' }
      $o.title = [string]$p.Title
      $o.artist = [string]$p.Artist
    }
  } catch { }
  [Console]::Out.WriteLine(($o | ConvertTo-Json -Compress))
  [Console]::Out.Flush()
  Start-Sleep -Milliseconds 1000
}
"""

_TOGGLE_PS = _PS_HEADER + r"""
try {
  $mgr = Get-Mgr
  $s = $mgr.GetCurrentSession()
  if ($s -ne $null) {
    Await ($s.TryTogglePlayPauseAsync()) ([bool]) | Out-Null
  }
} catch { }
"""

_state = {
    "config": dict(_DEFAULTS),
    "api": None,
    "media": None,
    "last_info": None,
    "last_active": 0.0,
    "in_class": False,
    "running": False,
    "proc": None,
    "thread": None,
    "worker_stop": None,
}


def _log(*a):
    print("[Audio]", *a)


# ---------- 配置 ----------
def _load_config():
    cfg = dict(_DEFAULTS)
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
        except Exception as e:
            _log("读取配置失败:", e)
    else:
        _save_config(cfg)
    return cfg


def _save_config(cfg):
    try:
        with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _log("保存配置失败:", e)


def _data_dir():
    api = _state.get("api")
    if api is not None:
        try:
            return api.get_data_dir()
        except Exception:
            pass
    d = os.path.join(_PLUGIN_DIR, 'data')
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _ensure_script(src, name):
    candidates = []
    d = _data_dir()
    if d:
        candidates.append(d)
    candidates.append(os.path.join(tempfile.gettempdir(), 'ClassBoard_audio'))
    for folder in candidates:
        try:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, name)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(src)
            return path
        except Exception:
            continue
    _log("写脚本失败：无可写目录")
    return None


# ---------- 后台轮询 ----------
def _apply_media(data):
    status = data.get('status')
    if status in ('playing', 'paused') and (data.get('title') or '').strip():
        _state["media"] = {
            "title": (data.get("title") or "").strip(),
            "artist": (data.get("artist") or "").strip(),
            "playing": status == 'playing',
            "paused": status == 'paused',
        }
    else:
        _state["media"] = None


def _worker(poll_path):
    while not _state["worker_stop"].is_set():
        try:
            proc = subprocess.Popen(
                [_PS, '-NoProfile', '-ExecutionPolicy', 'Bypass',
                 '-File', poll_path, '-ParentPid', str(os.getpid())],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, creationflags=_CREATE_NO_WINDOW)
        except Exception as e:
            _log("启动 PowerShell 失败:", e)
            return
        _state["proc"] = proc
        try:
            for raw in iter(proc.stdout.readline, b''):
                if _state["worker_stop"].is_set():
                    break
                line = raw.decode('utf-8', 'ignore').strip()
                if not line:
                    continue
                try:
                    _apply_media(json.loads(line))
                except Exception:
                    continue
        except Exception as e:
            _log("读取媒体输出异常:", e)
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
            _state["proc"] = None
        if _state["worker_stop"].is_set():
            break
        time.sleep(2.0)
    _state["running"] = False


def _start_worker():
    if _state["running"] or not _HAS_PS:
        return
    poll = _ensure_script(_POLL_PS, 'smtc_poll.ps1')
    if not poll:
        return
    _state["worker_stop"] = threading.Event()
    _state["running"] = True
    t = threading.Thread(target=_worker, args=(poll,), daemon=True)
    _state["thread"] = t
    t.start()


def _stop_worker():
    _state["running"] = False
    ev = _state.get("worker_stop")
    if ev is not None:
        ev.set()
    proc = _state.get("proc")
    if proc is not None:
        try:
            proc.terminate()
        except Exception:
            pass
    _state["media"] = None


# ---------- UI 线程 ----------
def _current_info():
    info = _state.get("media")
    if info and (info.get("playing") or info.get("paused")):
        return info
    return None


def _display_info():
    """播放中一直显示；暂停/停止后 hide_after_sec 秒内仍显示最后一条，然后隐藏。"""
    if _state.get("in_class"):
        return None
    info = _state.get("media")
    if info and info.get("playing"):
        return info
    cfg = _state["config"]
    try:
        keep = max(0, int(cfg.get("hide_after_sec", 5)))
    except (TypeError, ValueError):
        keep = 5
    if time.monotonic() - _state.get("last_active", 0.0) <= keep:
        return _state.get("last_info") or info
    return None


def _tick():
    api = _state.get("api")
    in_class = False
    if api is not None:
        try:
            in_class = api.is_in_class()
        except Exception:
            in_class = False
    _state["in_class"] = in_class

    if not _HAS_PS or not _state["config"].get("enabled", True):
        if _state.get("running"):
            _stop_worker()
        _state["media"] = None
    elif in_class:
        if _state.get("running"):
            _stop_worker()          # 上课：隐藏并停止 PowerShell 进程
    else:
        if not _state.get("running"):
            _start_worker()

    now = time.monotonic()
    info = _state.get("media")
    if info:
        _state["last_info"] = info
        if info.get("playing"):
            _state["last_active"] = now
    if api is not None:
        try:
            api.request_refresh()
        except Exception:
            pass


def _toggle():
    if not _HAS_PS:
        return
    toggle = _ensure_script(_TOGGLE_PS, 'smtc_toggle.ps1')
    if not toggle:
        return

    def run():
        try:
            subprocess.run(
                [_PS, '-NoProfile', '-ExecutionPolicy', 'Bypass',
                 '-File', toggle],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW, timeout=15)
        except Exception as e:
            _log("切换播放失败:", e)

    threading.Thread(target=run, daemon=True).start()


# ---------- 绘制 ----------
def _draw_glyph(p, rect, playing):
    p.setRenderHint(QPainter.Antialiasing)
    cx = rect.center().x()
    cy = rect.center().y()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor('white'))
    if playing:
        bw = max(3.0, rect.width() * 0.14)
        p.drawRoundedRect(QRectF(cx - bw - 1, cy - bw, bw, bw * 2), 1, 1)
        p.drawRoundedRect(QRectF(cx + 1, cy - bw, bw, bw * 2), 1, 1)
    else:
        r = max(4.0, rect.width() * 0.22)
        p.drawPolygon(QPolygonF([
            QPointF(cx - r * 0.6, cy - r),
            QPointF(cx - r * 0.6, cy + r),
            QPointF(cx + r * 0.9, cy),
        ]))


def _draw_note(p, rect):
    font = QFont("Segoe UI Symbol")
    font.setPixelSize(max(12, int(rect.height() * 0.95)))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor('#9ad1ff'))
    p.drawText(rect, Qt.AlignCenter, "♪")


def _draw_media(painter, rect, t):
    info = _display_info()
    if info is None:
        return
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    h = rect.height()
    cfg = _state["config"]

    if rect.width() <= 46:
        _draw_note(painter, rect)
        painter.restore()
        return

    btn_w = 26
    btn_rect = QRectF(rect.right() - btn_w, rect.top(), btn_w, h)
    _draw_glyph(painter, btn_rect, bool(info.get("playing")))

    note_rect = QRectF(rect.left() + 7, rect.top() + (h - 16) / 2.0, 15, 16)
    _draw_note(painter, note_rect)

    tx = note_rect.right() + 4
    text_w = btn_rect.left() - tx - 4
    if text_w <= 6:
        painter.restore()
        return

    if cfg.get("show_title", True):
        label = info.get("title", "")
        if info.get("artist"):
            label += f" - {info['artist']}"
    else:
        label = "正在播放"

    font = QFont("Microsoft YaHei UI")
    font.setPixelSize(12)
    painter.setFont(font)
    painter.setPen(QColor('white'))
    fm = painter.fontMetrics()
    elided = fm.elidedText(label, Qt.ElideRight, int(text_w))
    painter.drawText(QRectF(tx, rect.top(), text_w, h),
                     Qt.AlignVCenter | Qt.AlignLeft, elided)
    painter.restore()


# ---------- 主岛 / 副岛 spec ----------
def _enabled():
    return bool(_state["config"].get("enabled", True))


def _extra_spec():
    if _state.get("in_class") or not _enabled():
        return None
    if _state["config"].get("show_on") != "main":
        return None
    if _display_info() is None:
        return None
    try:
        w = max(80, min(400, int(_state["config"].get("max_width", 240))))
    except (TypeError, ValueError):
        w = 240
    return {"width": w, "draw": _draw_media, "on_click": _toggle,
            "priority": 10}


def _sub_spec():
    if _state.get("in_class") or not _enabled():
        return None
    if _state["config"].get("show_on") != "sub":
        return None
    if _display_info() is None:
        return None
    try:
        length = max(80, min(380, int(_state["config"].get("max_width", 240))))
    except (TypeError, ValueError):
        length = 240
    return {"length": length, "draw": _draw_media, "auto_collapse": False,
            "priority": 10}


# ---------- 设置页 ----------
def _build_settings(api):
    cfg = _state["config"]

    w = QWidget()
    root = QVBoxLayout(w)
    root.setContentsMargins(0, 0, 0, 0)
    form = QFormLayout()
    form.setHorizontalSpacing(24)
    form.setVerticalSpacing(10)

    enabled = QCheckBox("启用媒体显示")
    enabled.setChecked(bool(cfg.get("enabled", True)))
    show_on = QComboBox()
    show_on.addItem("主岛（在右侧加长）", "main")
    show_on.addItem("副岛（替换天气内容）", "sub")
    show_on.setCurrentIndex(1 if cfg.get("show_on") == "sub" else 0)
    hide_after = QSpinBox()
    hide_after.setRange(0, 120)
    hide_after.setSuffix(" 秒")
    hide_after.setValue(int(cfg.get("hide_after_sec", 5)))
    max_width = QSpinBox()
    max_width.setRange(80, 400)
    max_width.setSuffix(" px")
    max_width.setValue(int(cfg.get("max_width", 240)))
    show_title = QCheckBox("显示歌名/歌手")
    show_title.setChecked(bool(cfg.get("show_title", True)))

    def save(*_):
        c = _state["config"]
        c["enabled"] = bool(enabled.isChecked())
        c["show_on"] = show_on.currentData()
        c["hide_after_sec"] = int(hide_after.value())
        c["max_width"] = int(max_width.value())
        c["show_title"] = bool(show_title.isChecked())
        _save_config(c)
        api.request_refresh()

    enabled.toggled.connect(save)
    show_on.currentIndexChanged.connect(save)
    hide_after.valueChanged.connect(save)
    max_width.valueChanged.connect(save)
    show_title.toggled.connect(save)

    form.addRow("", enabled)
    form.addRow("显示位置", show_on)
    form.addRow("暂停/停止后隐藏", hide_after)
    form.addRow("最大宽度", max_width)
    form.addRow("", show_title)
    root.addLayout(form)

    hint = QLabel("播放中一直显示；暂停或停止后按上面的秒数自动隐藏。"
                  "上课期间会自动隐藏并停止后台轮询，下课后自动恢复。")
    hint.setObjectName("hint")
    root.addWidget(hint)

    status = QLabel()
    status.setWordWrap(True)
    status.setObjectName("hint")

    def refresh_status():
        if not _HAS_PS:
            status.setText(
                "媒体桥不可用，请确认 Windows PowerShell 可用：<br>"
                "<code>C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\"
                "powershell.exe</code><br>"
                "手动测试：<code>powershell -NoProfile -ExecutionPolicy "
                "Bypass -File &lt;数据目录&gt;\\smtc_poll.ps1</code>")
            return
        if _state.get("in_class"):
            status.setText("上课中：已隐藏并停止轮询。")
            return
        info = _current_info()
        if info:
            st = "播放中" if info.get("playing") else "已暂停"
            status.setText(f"当前媒体：<b>{info.get('title','')}</b>"
                           f"（{info.get('artist','')}） · {st}")
        else:
            status.setText("当前没有正在播放的媒体。")

    refresh_status()
    root.addWidget(status)

    test_row = QHBoxLayout()
    test_btn = QPushButton("注入测试媒体")
    clear_btn = QPushButton("清除测试")

    def inject():
        _state["media"] = {"title": "测试歌曲", "artist": "测试歌手",
                           "playing": True, "paused": False}
        _state["last_info"] = _state["media"]
        _state["last_active"] = time.monotonic()
        api.request_refresh()
        refresh_status()

    def clear():
        _state["media"] = None
        _state["last_active"] = 0.0
        api.request_refresh()
        refresh_status()

    test_btn.clicked.connect(inject)
    clear_btn.clicked.connect(clear)
    test_row.addWidget(test_btn)
    test_row.addWidget(clear_btn)
    test_row.addStretch()
    root.addLayout(test_row)

    t = QTimer(w)
    t.setInterval(1000)
    t.timeout.connect(refresh_status)
    t.start()

    root.addStretch()
    return w


def _on_stop():
    _stop_worker()


def register(api):
    _state["api"] = api
    _state["config"] = _load_config()
    api.add_island_extra(_extra_spec)
    api.add_subisland(_sub_spec)
    api.add_settings_page("媒体", _build_settings)
    api.set_interval(1, _tick)
    api.on_stop(_on_stop)
    if _HAS_PS:
        _tick()
    else:
        _log("媒体桥不可用：未找到 Windows PowerShell")
