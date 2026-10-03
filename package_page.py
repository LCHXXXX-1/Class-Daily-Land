# -*- coding: utf-8 -*-
"""第三方包管理页（设置 → 扩展）。

工具栏（下载源选择 / 刷新 / 手动安装）+ 包卡片列表 + 空态 + 底部日志。
所有耗时操作走 PackageStore 的后台线程。
"""
import os
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QProgressBar,
                               QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from package_store import PackageStore
from settings_widgets import Badge, BusySpinner
from ui_common import setup_touch_scroll

import plugin_deps

STATUS_TEXT = {
    "not_installed": "未安装",
    "installed": "已安装",
    "update": "可更新",
}


class PackageCard(QFrame):
    def __init__(self, entry, page, parent=None):
        super().__init__(parent)
        self.setObjectName("marketCard")
        self.page = page
        self.entry = entry

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(10)
        self.name_lbl = QLabel()
        self.name_lbl.setObjectName("marketName")
        self.badge = Badge()
        self.ver_lbl = QLabel()
        self.ver_lbl.setObjectName("marketVer")
        self.ver_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.addWidget(self.name_lbl)
        head.addWidget(self.badge)
        head.addStretch(1)
        head.addWidget(self.ver_lbl)
        lay.addLayout(head)

        self.use_lbl = QLabel()
        self.use_lbl.setObjectName("marketDesc")
        self.use_lbl.setWordWrap(True)
        lay.addWidget(self.use_lbl)

        self.progress = QProgressBar()
        self.progress.setObjectName("marketProgress")
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        lay.addWidget(self.progress)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addStretch(1)
        self.btn_install = QPushButton("安装")
        self.btn_install.setObjectName("primary")
        self.btn_update = QPushButton("更新")
        self.btn_update.setObjectName("primary")
        self.btn_uninstall = QPushButton("删除")
        for b in (self.btn_install, self.btn_update, self.btn_uninstall):
            b.setProperty("cardAction", True)
            b.setCursor(Qt.PointingHandCursor)
            btns.addWidget(b)
        lay.addLayout(btns)

        self.btn_install.clicked.connect(
            lambda: self.page.store.install(self.entry["name"]))
        self.btn_update.clicked.connect(
            lambda: self.page.store.install(self.entry["name"]))
        self.btn_uninstall.clicked.connect(
            lambda: self.page.do_uninstall(self.entry["name"]))

        self.update_entry(entry)

    def update_entry(self, entry):
        self.entry = entry
        name = entry.get("name", "")
        st = entry.get("status", "not_installed")
        self.name_lbl.setText(name)

        text = STATUS_TEXT.get(st, st)
        if st == "installed" and entry.get("manual"):
            text = "已安装 · 手动"
        self.badge.set_status(st, text)

        remote = entry.get("version", "")
        lv = entry.get("installed_version", "")
        if entry.get("installed") and lv and remote and lv != remote:
            self.ver_lbl.setText(f"v{lv} → v{remote}")
        elif lv:
            self.ver_lbl.setText(f"v{lv}")
        elif remote:
            self.ver_lbl.setText(f"v{remote}")
        else:
            self.ver_lbl.setText("版本未知")

        users = entry.get("used_by") or []
        if users:
            self.use_lbl.setText("被插件使用：" + "、".join(users))
        elif entry.get("installed"):
            self.use_lbl.setText("当前没有插件使用它")
        else:
            self.use_lbl.setText("暂无插件声明此依赖")
        self.use_lbl.setVisible(True)

        self.btn_install.setVisible(st == "not_installed")
        self.btn_update.setVisible(st == "update")
        self.btn_uninstall.setVisible(bool(entry.get("installed")))

    def set_progress(self, pct):
        if pct < 0:
            self.progress.setValue(0)
            self.progress.hide()
        else:
            self.progress.show()
            self.progress.setValue(pct)

    def flash(self, text, ok=True):
        color = "#2ea043" if ok else "#e5484d"
        self.use_lbl.setText(text)
        self.use_lbl.setStyleSheet(f"color:{color}; font-size:12px;")
        self.use_lbl.show()
        QTimer.singleShot(8000, self._restore_text)

    def _restore_text(self):
        try:
            self.update_entry(self.entry)
            self.use_lbl.setStyleSheet("")
        except Exception:
            pass


class PackagePage(QWidget):
    def __init__(self, plugin_manager, settings, parent=None):
        super().__init__(parent)
        self.store = PackageStore(plugin_manager, settings, parent=self)
        self._cards = {}
        self._auto_synced = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # ---------- 工具栏 ----------
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_refresh = QPushButton("刷新列表")
        self.btn_refresh.setObjectName("primary")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        bar.addWidget(self.btn_refresh)
        self.spinner = BusySpinner()
        bar.addWidget(self.spinner)

        src_lbl = QLabel("下载源：")
        src_lbl.setStyleSheet("color: #888; padding-left: 8px;")
        bar.addWidget(src_lbl)
        self.source_combo = QComboBox()
        for label, sid in self.store.sources():
            self.source_combo.addItem(label, sid)
        idx = self.source_combo.findData(self.store.source_id())
        if idx >= 0:
            self.source_combo.setCurrentIndex(idx)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        bar.addWidget(self.source_combo)
        bar.addStretch(1)
        root.addLayout(bar)

        # ---------- 手动安装 ----------
        manual = QHBoxLayout()
        manual.setSpacing(8)
        m_lbl = QLabel("手动安装：")
        m_lbl.setStyleSheet("color: #888;")
        manual.addWidget(m_lbl)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入包名后安装，例如 pillow")
        self.name_edit.returnPressed.connect(self._manual_install)
        manual.addWidget(self.name_edit, 1)
        self.btn_manual = QPushButton("安装此包")
        self.btn_manual.setCursor(Qt.PointingHandCursor)
        self.btn_manual.clicked.connect(self._manual_install)
        manual.addWidget(self.btn_manual)
        root.addLayout(manual)

        self.status_lbl = QLabel("还没刷新过")
        self.status_lbl.setObjectName("marketStatus")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        root.addWidget(self.status_lbl)

        self.btn_refresh.clicked.connect(self.store.refresh)

        # ---------- 包卡片列表 ----------
        self.scroll = QScrollArea()
        self.scroll.setObjectName("marketScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("pageInner")
        self.cards_box = QVBoxLayout(inner)
        self.cards_box.setContentsMargins(0, 0, 4, 0)
        self.cards_box.setSpacing(10)
        self.cards_box.setAlignment(Qt.AlignTop)

        self.empty_lbl = QLabel(
            "暂无可用包\n\n点击「刷新列表」从下载源获取；也可直接手动输入包名安装")
        self.empty_lbl.setObjectName("emptyTip")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.cards_box.addWidget(self.empty_lbl)
        self.scroll.setWidget(inner)
        root.addWidget(self.scroll, 1)

        setup_touch_scroll(self.scroll, mouse_drag=True)

        # ---------- 日志 ----------
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("marketLog")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(400)
        self.log_view.setFixedHeight(96)
        root.addWidget(self.log_view)

        s = self.store
        s.log_line.connect(self._log)
        s.busy_changed.connect(self._on_busy)
        s.catalog_ready.connect(self._rebuild)
        s.task_progress.connect(self._on_progress)
        s.task_done.connect(self._on_task_done)

    # ---------- 操作 ----------
    def _manual_install(self):
        name = self.name_edit.text().strip()
        if not name:
            return
        self.store.install(name)

    def do_uninstall(self, name):
        self.store.uninstall(name)

    def _on_source_changed(self, idx):
        sid = self.source_combo.currentData() or plugin_deps.DEFAULT_SOURCE
        if sid == self.store.source_id():
            return
        self.store.set_source(sid)
        self._log(f"已切换下载源：{sid}")
        self.store.refresh()

    def shutdown(self):
        self.store.shutdown()

    # ---------- 信号 ----------
    def _log(self, text):
        self.log_view.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {text}")

    def _on_busy(self, busy):
        for b in (self.btn_refresh, self.btn_manual):
            b.setEnabled(not busy)
        self.name_edit.setEnabled(not busy)
        if busy:
            self.spinner.start()
            self.status_lbl.setText("正在忙…")
        else:
            self.spinner.stop()

    def _rebuild(self, entries):
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()
        self.empty_lbl.setVisible(not entries)
        for entry in entries:
            card = PackageCard(entry, self)
            self._cards[entry["name"]] = card
            self.cards_box.addWidget(card)
        installed = sum(1 for e in entries if e.get("installed"))
        self.status_lbl.setText(
            f"共 {len(entries)} 个包 · 已安装 {installed} 个 · "
            f"下载源：{self.store.source_id()}")

    def _on_progress(self, name, pct):
        card = self._cards.get(name)
        if card is not None:
            card.set_progress(pct)

    def _on_task_done(self, name, ok, msg):
        card = self._cards.get(name)
        if card is not None:
            card.flash(("✓ " if ok else "✗ ") + msg, ok)
        if ok and name:
            self._log(f"{name}：{msg}")

    def showEvent(self, event):
        super().showEvent(event)
        if not self._auto_synced:
            self._auto_synced = True
            QTimer.singleShot(120, self.store.refresh)
