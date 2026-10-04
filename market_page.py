import os
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel,
                               QPlainTextEdit,
                               QProgressBar, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from plugin_market import PluginMarket
from settings_widgets import Badge, BusySpinner
from ui_common import setup_touch_scroll
import theme

STATUS_TEXT = {
    "not_installed": "未安装",
    "installed": "已安装",
    "update": "可更新",
    "disabled": "已禁用",
    "failed": "加载失败",
    # 索引记录本身有问题：装不了，但照样显示
    "invalid": "装不了",
}


class PluginCard(QFrame):
    """一个插件一张卡片：名字、版本、状态、说明，以及能点的操作。"""

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
        self.name_lbl = QLabel(entry.get("name", entry.get("id", "")))
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

        self.id_lbl = QLabel()
        self.id_lbl.setObjectName("marketVer")
        self.id_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        lay.addWidget(self.id_lbl)

        self.desc_lbl = QLabel()
        self.desc_lbl.setObjectName("marketDesc")
        self.desc_lbl.setWordWrap(True)
        lay.addWidget(self.desc_lbl)

        # 出问题时挂在这里：⚠ 加一句能看懂的原因
        self.warn_lbl = QLabel()
        self.warn_lbl.setObjectName("marketWarn")
        self.warn_lbl.setWordWrap(True)
        self.warn_lbl.hide()
        lay.addWidget(self.warn_lbl)

        self.progress = QProgressBar()
        self.progress.setObjectName("marketProgress")
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        lay.addWidget(self.progress)

        self.msg_lbl = QLabel()
        self.msg_lbl.setObjectName("marketVer")
        self.msg_lbl.hide()
        lay.addWidget(self.msg_lbl)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addStretch(1)
        self.btn_install = QPushButton("装上")
        self.btn_update = QPushButton("更新")
        self.btn_enable = QPushButton("启用")
        self.btn_disable = QPushButton("禁用")
        self.btn_uninstall = QPushButton("卸掉")
        for b in (self.btn_install, self.btn_update, self.btn_enable,
                  self.btn_disable, self.btn_uninstall):
            b.setProperty("cardAction", True)
            b.setCursor(Qt.PointingHandCursor)
            btns.addWidget(b)
        lay.addLayout(btns)

        self.btn_install.clicked.connect(
            lambda: self.page.do_install(self.entry["id"]))
        self.btn_update.clicked.connect(
            lambda: self.page.do_install(self.entry["id"]))
        self.btn_enable.clicked.connect(
            lambda: self.page.market.set_enabled(self.entry["id"], True))
        self.btn_disable.clicked.connect(
            lambda: self.page.market.set_enabled(self.entry["id"], False))
        self.btn_uninstall.clicked.connect(
            lambda: self.page.do_uninstall(self.entry["id"]))

        self.update_entry(entry)

    def update_entry(self, entry):
        """按 entry 刷新整张卡片；哪些按钮能点由状态说了算。"""
        self.entry = entry
        st = entry.get("status", "not_installed")
        self.badge.set_status(st, STATUS_TEXT.get(st, st))

        remote = entry.get("version", "")
        lv = entry.get("installed_version", "")
        if entry.get("installed") and lv and lv != remote:
            self.ver_lbl.setText(f"v{lv} → v{remote}")
        else:
            self.ver_lbl.setText(f"v{remote}")

        author = entry.get("author") or "?"
        self.id_lbl.setText(f"id: {entry['id']}    作者: {author}")

        desc = entry.get("description") or ""
        self.desc_lbl.setText(desc)
        self.desc_lbl.setVisible(bool(desc))

        # 索引记录不合法 / 插件加载失败，都在这里写清楚原因
        self.set_warning(entry.get("problem") or entry.get("load_error") or "")

        has = st in ("installed", "update", "disabled", "failed")
        installed_now = bool(entry.get("installed"))
        self.btn_install.setVisible(st == "not_installed")
        self.btn_update.setVisible(st == "update")
        # 记录有问题也别把退路堵死：真装了就还能卸
        self.btn_uninstall.setVisible(has or installed_now)
        self.btn_enable.setVisible(st == "disabled")
        self.btn_disable.setVisible(has and st != "disabled")

    def set_warning(self, reason):
        """挂上"⚠ + 原因"；没原因就收起来。"""
        reason = str(reason or "").strip()
        if not reason:
            self.warn_lbl.setText("")
            self.warn_lbl.hide()
            return
        color = theme.color("danger")
        self.warn_lbl.setText("⚠ " + reason)
        self.warn_lbl.setStyleSheet(f"color:{color}; font-size:12px;")
        self.warn_lbl.show()

    def set_progress(self, pct):
        if pct < 0:
            self.progress.setValue(0)
            self.progress.hide()
        else:
            self.progress.show()
            self.progress.setValue(pct)

    def flash(self, text, ok=True):
        """临时提示，8 秒后自己收起来。"""
        color = "#2ea043" if ok else "#e5484d"
        self.msg_lbl.setText(text)
        self.msg_lbl.setStyleSheet(f"color:{color}; font-size:12px;")
        self.msg_lbl.show()
        QTimer.singleShot(8000, self.msg_lbl.hide)

    def show_dep(self, ev):
        """依赖安装进度：进度条 + 实时文案。"""
        stage = str(ev.get("stage", ""))
        text = str(ev.get("text", ""))
        pct = int(ev.get("pct", -1) or -1)
        if stage in ("done", "failed"):
            self.progress.setValue(100 if stage == "done" else 0)
            self.progress.hide()
        else:
            self.progress.show()
            self.progress.setValue(max(0, min(100, pct)) if pct >= 0 else 0)
        if text:
            color = "#e5484d" if stage == "failed" else "#57606a"
            self.msg_lbl.setText(text)
            self.msg_lbl.setStyleSheet(f"color:{color}; font-size:12px;")
            self.msg_lbl.show()


class MarketPage(QWidget):
    # 依赖下载跑在工作线程，事件先跳板回主线程再刷 UI
    _ext_dep_event = Signal(dict)

    def __init__(self, plugin_manager, settings, parent=None):
        super().__init__(parent)
        self.market = PluginMarket(plugin_manager, settings, parent=self)
        self._cards = {}
        self._auto_synced = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # ---- 工具栏 ----
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_sync = QPushButton("检查更新")
        self.btn_sync.setObjectName("primary")
        self.btn_rescan = QPushButton("刷新一下")
        self.btn_all = QPushButton("全部更新")
        self.btn_open = QPushButton("打开插件文件夹")
        for b in (self.btn_sync, self.btn_rescan, self.btn_all, self.btn_open):
            b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            bar.addWidget(b)
        self.spinner = BusySpinner()
        bar.addWidget(self.spinner)
        bar.addStretch(1)
        root.addLayout(bar)

        # ---- 索引来源 ----
        source_bar = QHBoxLayout()
        source_bar.setSpacing(6)
        source_lbl = QLabel("索引来源：")
        source_lbl.setStyleSheet("color: #888; padding: 0 4px;")
        self.source_combo = QComboBox()
        self.source_combo.addItem("官方服务器", "official")
        self.source_combo.addItem("GitHub", "github")
        self.source_combo.addItem("Gitee", "gitee")
        idx = self.source_combo.findData(
            self.market.settings.get("market_source", "official"))
        if idx >= 0:
            self.source_combo.setCurrentIndex(idx)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        source_bar.addWidget(source_lbl)
        source_bar.addWidget(self.source_combo)
        source_bar.addStretch(1)
        root.addLayout(source_bar)

        self.status_lbl = QLabel("还没同步过")
        self.status_lbl.setObjectName("marketStatus")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred)
        root.addWidget(self.status_lbl)

        self.btn_sync.clicked.connect(self.do_check)
        self.btn_rescan.clicked.connect(self.market.rescan)
        self.btn_all.clicked.connect(self.market.update_all)
        self.btn_open.clicked.connect(self._open_dir)

        # ---- 重启提示横幅 ----
        self.banner = QFrame()
        self.banner.setObjectName("restartBanner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 8, 10, 8)
        bl.setSpacing(8)
        self.banner_lbl = QLabel()
        self.banner_lbl.setObjectName("bannerText")
        bl.addWidget(self.banner_lbl, 1)
        btn_x = QPushButton("✕")
        btn_x.setProperty("cardAction", True)
        btn_x.clicked.connect(self.banner.hide)
        bl.addWidget(btn_x)
        self.banner.hide()
        root.addWidget(self.banner)

        # ---- 卡片列表 ----
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
            "暂无插件\n\n点击上方「检查更新」从插件索引拉取插件列表")
        self.empty_lbl.setObjectName("emptyTip")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.cards_box.addWidget(self.empty_lbl)
        self.scroll.setWidget(inner)
        root.addWidget(self.scroll, 1)

        # 触屏：手指拖拽 + 惯性滑动
        setup_touch_scroll(self.scroll, mouse_drag=True)

        # ---- 日志 ----
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("marketLog")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(400)
        self.log_view.setFixedHeight(96)
        root.addWidget(self.log_view)

        m = self.market
        m.log_line.connect(self._log)
        m.busy_changed.connect(self._on_busy)
        m.sync_finished.connect(self._on_sync)
        m.catalog_ready.connect(self._rebuild)
        m.task_progress.connect(self._on_progress)
        m.task_done.connect(self._on_task_done)
        m.dep_progress.connect(self._on_dep_progress)

        # 宿主自己后台装的依赖（启动时补下载）也刷到这里：
        # 回调在工作线程触发 → 信号跳板 → 主线程槽函数
        self._ext_dep_event.connect(self._on_dep_progress)
        try:
            if plugin_manager is not None:
                plugin_manager.deps_progress = \
                    lambda ev: self._ext_dep_event.emit(
                        ev if isinstance(ev, dict) else {})
        except Exception:
            pass

    # ---------- 操作 ----------
    def do_check(self):
        self.market.check_updates()

    def do_install(self, pid):
        self.market.install(pid)

    def do_uninstall(self, pid):
        self.market.uninstall(pid)

    def _open_dir(self):
        try:
            if os.path.isdir(self.market.plugins_dir):
                os.startfile(self.market.plugins_dir)
        except Exception as e:
            self._log(f"文件夹没打开：{e}")

    def shutdown(self):
        self.market.shutdown()
        # 卸掉页面时挂的依赖进度回调，避免向已析构对象发信号
        try:
            if (self.market.manager is not None
                    and getattr(self.market.manager, 'deps_progress',
                                None) is not None):
                self.market.manager.deps_progress = None
        except Exception:
            pass

    # ---------- 信号 ----------
    def _log(self, text):
        self.log_view.appendPlainText(
            f"[{time.strftime('%H:%M:%S')}] {text}")

    def _on_busy(self, busy):
        for b in (self.btn_sync, self.btn_rescan, self.btn_all):
            b.setEnabled(not busy)
        if busy:
            self.spinner.start()
            self.status_lbl.setText("正在忙…")
        else:
            self.spinner.stop()

    def _on_sync(self, ok, msg):
        if ok:
            self.status_lbl.setText(
                f"上次检查: {self.market.last_sync_text} · {msg}")
        else:
            self.status_lbl.setText(f"同步没成功：{msg}")

    def _rebuild(self, entries):
        """索引里有多少条就渲染多少张，一条都不藏。"""
        # 光 deleteLater() 不够：控件要等事件循环才销毁，
        # 布局里的条目会一直堆着。先摘下来再销毁。
        for card in self._cards.values():
            self.cards_box.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self.empty_lbl.setVisible(not entries)

        used = {}
        for entry in entries:
            card = PluginCard(entry, self)
            pid = str(entry.get("id") or "")
            if pid and pid in used:
                # id 撞车了，给后到的另起 key，别把前一张顶掉
                used[pid] += 1
                key = f"{pid}#{used[pid]}"
            else:
                used[pid] = 1
                key = pid or f"?{len(self._cards)}"
            self._cards[key] = card
            self.cards_box.addWidget(card)
        # 不额外加 stretch：cards_box 已经是 AlignTop，
        # 而且 _rebuild 会被反复调用，加一次就多一个 spacer。

        upd = sum(1 for e in entries if e.get("update_available"))
        self.btn_all.setEnabled(upd > 0 and not self.market.is_busy())
        self.btn_all.setText(f"⬆ 全部更新({upd})" if upd else "⬆ 全部更新")

    def _on_progress(self, pid, pct):
        card = self._cards.get(pid)
        if card is not None:
            card.set_progress(pct)

    def _on_task_done(self, pid, ok, msg, restart):
        if pid:
            card = self._cards.get(pid)
            if card is not None:
                card.flash(("✓ " if ok else "✗ ") + msg, ok)
                if not ok:
                    # 失败原因常驻，别只闪 8 秒就没了
                    card.set_warning(msg)
            if ok and not restart:
                self._try_runtime_load(pid)
        if restart and ok:
            self.banner_lbl.setText(
                "更新 / 卸载 / 启用 / 禁用等改动需重启程序后生效")
            self.banner.show()

    def _on_dep_progress(self, ev):
        card = self._cards.get(str(ev.get("plugin", "")))
        if card is not None:
            card.show_dep(ev)
        text = str(ev.get("text", ""))
        if text:
            self._log(text)

    def _on_source_changed(self, idx):
        """切换索引来源时自动同步一次。"""
        source = self.source_combo.currentData() or "official"
        if source == self.market.settings.get("market_source"):
            return
        self.market.settings["market_source"] = source
        self.market.settings.save()
        self._log(f"已切换索引来源：{source}")
        self.do_check()

    def _try_runtime_load(self, pid):
        """新装的插件试着当场加载，省一次重启。"""
        manager = self.market.manager
        if manager is None:
            return
        try:
            ok, info = manager.load_installed_plugin(pid)
        except Exception as e:
            ok, info = False, str(e)
        card = self._cards.get(pid)
        if card is None:
            return
        if ok:
            card.flash("✓ 已即时加载，无需重启", True)
        else:
            card.flash(f"装好啦（{info}）", True)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._auto_synced:
            self._auto_synced = True
            QTimer.singleShot(120, self.do_check)
