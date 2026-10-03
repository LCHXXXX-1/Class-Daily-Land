import re
from datetime import datetime

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QTextEdit, QPushButton, QComboBox,
                               QScrollArea, QWidget, QMessageBox, QTableWidget,
                               QTableWidgetItem, QHeaderView, QAbstractItemView,
                               QListWidget, QListWidgetItem, QSpinBox, QDateEdit,
                               QFileDialog, QMenu, QRadioButton, QButtonGroup)
from PySide6.QtCore import Qt, QDate, QTimer, QPoint
from PySide6.QtGui import QColor

from ui_common import (setup_dialog_style as _setup_dialog_style,
                       clear_layout as _clear_layout)
from settings_widgets import SectionCard, apply_modern_dialog, play_entrance
import theme

FONT_SIZE = 14
DAY_HEADERS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def _valid_time(s):
    return bool(re.match(r'^\d{1,2}:\d{2}$', str(s).strip()))


class AttendanceDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle("出勤")
        self.resize(350, 200)
        _setup_dialog_style(self)
        layout = QVBoxLayout(self)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("应到"))
        self.should_edit = QLineEdit(app.should)
        row1.addWidget(self.should_edit)
        layout.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("实到"))
        self.actual_edit = QLineEdit(app.actual)
        row2.addWidget(self.actual_edit)
        layout.addLayout(row2)
        btns = QHBoxLayout()
        btns.addStretch()
        ok = QPushButton("确认")
        ok.clicked.connect(self._on_confirm)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        btns.addStretch()
        layout.addLayout(btns)

    def _on_confirm(self):
        s = self.should_edit.text().strip()
        a = self.actual_edit.text().strip()
        if s.isdigit() and a.isdigit():
            self.app.should = s
            self.app.actual = a
            self.app.save_config()
            self.app.update_display()
            self.accept()
        else:
            QMessageBox.warning(self, "格式错误", "请输入有效数字。")


class DutyEditor(QDialog):
    def __init__(self, duty_manager, app, parent=None, embedded=False):
        super().__init__(parent)
        self.duty_manager = duty_manager
        self.app = app
        self.setWindowTitle("值日生名单")
        self.resize(500, 420)
        if not embedded:
            _setup_dialog_style(self)
        layout = QVBoxLayout(self)
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("逐个添加："))
        self.single_edit = QLineEdit()
        add_row.addWidget(self.single_edit)
        add_btn = QPushButton("加上")
        add_btn.clicked.connect(self._add_single)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)
        batch_btn = QPushButton("一次加多几个（用逗号隔开）")
        batch_btn.clicked.connect(self._open_batch)
        layout.addWidget(batch_btn)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.inner)
        layout.addWidget(self.scroll)
        close_btn = QPushButton("取消")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)
        self.refresh()

    def refresh(self):
        _clear_layout(self.inner_layout)
        names = self.duty_manager.duty_list
        if not names:
            self.inner_layout.addWidget(QLabel("暂无值日生"))
            return
        for i, name in enumerate(names):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.addWidget(QLabel(f"{i + 1}. {name}"))
            rl.addStretch()
            del_btn = QPushButton("删除")
            del_btn.setMinimumWidth(56)
            del_btn.clicked.connect(lambda _, idx=i: self._delete(idx))
            rl.addWidget(del_btn)
            self.inner_layout.addWidget(row)

    def _add_single(self):
        name = self.single_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "姓名不能为空")
            return
        self.duty_manager.add_duty(name)
        self.single_edit.clear()
        self.refresh()
        self.app.update_display()

    def _open_batch(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("批量添加值日生")
        dlg.resize(450, 250)
        _setup_dialog_style(dlg)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("姓名（用逗号分隔）："))
        text = QTextEdit()
        layout.addWidget(text)
        btns = QHBoxLayout()
        btns.addStretch()

        def do_add():
            raw = text.toPlainText().strip()
            names = [n.strip() for n in raw.split(',') if n.strip()]
            if not names:
                QMessageBox.warning(dlg, "提示", "姓名不能为空")
                return
            for n in names:
                self.duty_manager.add_duty(n)
            dlg.accept()
            self.refresh()
            self.app.update_display()

        ok = QPushButton("确认")
        ok.clicked.connect(do_add)
        cancel = QPushButton("取消")
        cancel.clicked.connect(dlg.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        btns.addStretch()
        layout.addLayout(btns)
        dlg.exec()

    def _delete(self, idx):
        self.duty_manager.remove_duty(idx)
        self.refresh()
        self.app.update_display()


class HomeworkEditor(QDialog):
    def __init__(self, homework_manager, app, parent=None, embedded=False):
        super().__init__(parent)
        self.hw = homework_manager
        self.app = app
        self.setWindowTitle("编辑作业")
        self.resize(700, 600)
        if not embedded:
            _setup_dialog_style(self)
        layout = QVBoxLayout(self)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("科目："))
        self.subject_edit = QLineEdit()
        self.subject_edit.setFixedWidth(150)
        row1.addWidget(self.subject_edit)
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("提交日期（可以自己填）："))
        self.date_edit = QLineEdit()
        self.date_edit.setFixedWidth(200)
        row2.addWidget(self.date_edit)
        row2.addStretch()
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("作业内容："), alignment=Qt.AlignTop)
        self.content_edit = QTextEdit()
        self.content_edit.setFixedHeight(70)
        row3.addWidget(self.content_edit)
        layout.addLayout(row3)

        add_btn = QPushButton("添加作业")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add)
        layout.addWidget(add_btn, alignment=Qt.AlignCenter)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.inner)
        layout.addWidget(self.scroll)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("确认")
        confirm.clicked.connect(self._confirm)
        btns.addWidget(cancel)
        btns.addWidget(confirm)
        btns.addStretch()
        layout.addLayout(btns)
        self.refresh()

    def refresh(self):
        _clear_layout(self.inner_layout)
        grouped = self.hw.get_grouped_homework()
        if not grouped:
            self.inner_layout.addWidget(QLabel("暂无作业"))
            return
        for subject, data in grouped.items():
            title = subject
            date = data.get('date', '')
            if date:
                title += f" ({date})"
            hdr = QWidget()
            hl = QHBoxLayout(hdr)
            hl.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(title)
            lbl.setStyleSheet("font-weight: bold;")
            hl.addWidget(lbl)
            clear_btn = QPushButton("全部清除")
            clear_btn.setMinimumWidth(76)
            clear_btn.clicked.connect(lambda _, s=subject: self._clear_subject(s))
            hl.addWidget(clear_btn)
            hl.addStretch()
            self.inner_layout.addWidget(hdr)
            for content, real_idx in zip(data['contents'], data['indices']):
                row = QWidget()
                rl = QHBoxLayout(row)
                rl.setContentsMargins(20, 0, 0, 0)
                rl.addWidget(QLabel(f"{real_idx + 1}. {content}"))
                del_btn = QPushButton("删除")
                del_btn.setMinimumWidth(56)
                del_btn.clicked.connect(lambda _, i=real_idx: self._delete(i))
                rl.addWidget(del_btn)
                edit_btn = QPushButton("修改")
                edit_btn.setMinimumWidth(56)
                edit_btn.clicked.connect(lambda _, i=real_idx: self._edit(i))
                rl.addWidget(edit_btn)
                self.inner_layout.addWidget(row)

    def _add(self):
        subject = self.subject_edit.text().strip()
        date = self.date_edit.text().strip()
        content = self.content_edit.toPlainText().strip()
        if not subject:
            QMessageBox.warning(self, "提示", "科目不能为空")
            return
        if not content:
            QMessageBox.warning(self, "提示", "作业内容不能为空")
            return
        self.hw.add_homework(subject, content, date)
        self.content_edit.clear()
        self.refresh()
        self.app.update_display()

    def _delete(self, idx):
        self.hw.remove_homework(idx)
        self.refresh()
        self.app.update_display()

    def _clear_subject(self, subject):
        remaining = [h for h in self.hw.get_all_homework()
                     if h.get('subject', '未分类') != subject]
        self.hw.homework_list = remaining
        self.hw.save_homework()
        self.subject_edit.setText(subject)
        self.refresh()
        self.app.update_display()

    def _edit(self, idx):
        all_hw = self.hw.get_all_homework()
        if not (0 <= idx < len(all_hw)):
            return
        item = all_hw[idx]
        dlg = QDialog(self)
        dlg.setWindowTitle("修改作业")
        dlg.resize(450, 400)
        _setup_dialog_style(dlg)
        layout = QVBoxLayout(dlg)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("科目："))
        sub_edit = QLineEdit(item.get('subject', ''))
        r1.addWidget(sub_edit)
        layout.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("提交日期："))
        date_edit = QLineEdit(item.get('date', ''))
        r2.addWidget(date_edit)
        layout.addLayout(r2)
        layout.addWidget(QLabel("作业内容："))
        content_edit = QTextEdit()
        content_edit.setPlainText(item.get('content', ''))
        layout.addWidget(content_edit)
        btns = QHBoxLayout()
        btns.addStretch()

        def save():
            ns = sub_edit.text().strip()
            nd = date_edit.text().strip()
            nc = content_edit.toPlainText().strip()
            if not ns or not nc:
                QMessageBox.warning(dlg, "提示", "科目和内容不能为空")
                return
            self.hw.update_homework(idx, ns, nc, nd)
            dlg.accept()
            self.refresh()
            self.app.update_display()

        ok = QPushButton("保存")
        ok.clicked.connect(save)
        cancel = QPushButton("退出")
        cancel.clicked.connect(dlg.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        btns.addStretch()
        layout.addLayout(btns)
        dlg.exec()

    def _confirm(self):
        self.app.update_display()
        self.accept()


class CourseEditor(QDialog):
    """课表编辑器（全新界面）。

    列：节次 / 开始 / 结束 / 周一…周日。双击单元格编辑，保存时校验 HH:MM。
    公共接口与旧版一致：CourseEditor(schedule_manager, parent, timetable_name)。
    """

    def __init__(self, schedule_manager, parent=None, timetable_name=None,
                 embedded=False):
        super().__init__(parent)
        self.schedule = schedule_manager
        self.name = timetable_name or schedule_manager.active_name
        self._cards = []

        self.setWindowTitle(f"课表编辑器 - {self.name}")
        self.resize(940, 640)
        self.setMinimumSize(760, 520)
        if not embedded:
            _setup_dialog_style(self)
        apply_modern_dialog(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(10)

        title = QLabel("课表编辑器")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        sub = QLabel(f"课表：{self.name}　·　双击格子，时间写成 HH:MM（比如 08:00）")
        sub.setObjectName("pageSub")
        sub.setWordWrap(True)
        root.addWidget(sub)
        root.addSpacing(6)

        card = SectionCard("课程")
        self.table = QTableWidget()
        self.table.setObjectName("courseTable")
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked
                                   | QAbstractItemView.EditKeyPressed)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setMinimumHeight(320)
        card.add_widget(self.table)
        root.addWidget(card, 1)
        self._cards.append(card)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.add_btn = QPushButton("＋ 加一节")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self._add_row)
        self.del_btn = QPushButton("删除选中课节")
        self.del_btn.setCursor(Qt.PointingHandCursor)
        self.del_btn.clicked.connect(self._del_row)
        self.export_btn = QPushButton("导出课表…")
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.clicked.connect(self._export_menu)
        self.import_btn = QPushButton("导入课表…")
        self.import_btn.setCursor(Qt.PointingHandCursor)
        self.import_btn.clicked.connect(self._import_file)
        self.count_lbl = QLabel()
        self.count_lbl.setObjectName("hint")
        self.count_hint = QLabel()
        self.count_hint.setObjectName("hint")
        foot.addWidget(self.add_btn)
        foot.addWidget(self.del_btn)
        foot.addWidget(self.export_btn)
        foot.addWidget(self.import_btn)
        foot.addSpacing(6)
        foot.addWidget(self.count_lbl)
        foot.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("primary")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save)
        foot.addWidget(cancel)
        foot.addWidget(save)
        root.addLayout(foot)
        root.addWidget(self.count_hint)

        self._load_to_table()

    # ---------- 载入 ----------
    def _load_to_table(self):
        tt = self.schedule.get_timetable(self.name)
        if not tt:
            QMessageBox.warning(self, "错误", "未找到该课表")
            self.reject()
            return False
        periods = tt.get("periods", [])
        timetable = tt.get("timetable", {})
        cols = 3 + 7
        self.table.setColumnCount(cols)
        self.table.setHorizontalHeaderLabels(
            ["节次", "开始", "结束"] + DAY_HEADERS)
        header = self.table.horizontalHeader()
        for i in range(cols):
            header.setSectionResizeMode(
                i, QHeaderView.ResizeToContents if i < 3
                else QHeaderView.Stretch)
        self.table.setRowCount(len(periods))
        for r, p in enumerate(periods):
            self._set_cell(r, 0, p.get("name", f"第{r + 1}节"))
            self._set_cell(r, 1, p.get("start", ""))
            self._set_cell(r, 2, p.get("end", ""))
            for d in range(7):
                lst = timetable.get(str(d), [])
                self._set_cell(r, 3 + d, lst[r] if r < len(lst) else "")
        self._update_count()
        return True

    def _set_cell(self, r, c, text):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(r, c, item)

    def _get_cell(self, r, c):
        item = self.table.item(r, c)
        return item.text().strip() if item else ""

    def _update_count(self):
        n = self.table.rowCount()
        self.count_lbl.setText(f"共 {n} 节")
        # 节次多到离谱的时候，底部来一句
        if n >= 30:
            hint = "节次过多，请确认"
        elif n >= 25:
            hint = "节次偏多，请确认"
        elif n >= 20:
            hint = "节次较多，请确认"
        else:
            hint = ""
        self.count_hint.setText(hint)

    # ---------- 行操作 ----------
    def _add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._set_cell(r, 0, f"第{r + 1}节")
        self._set_cell(r, 1, "08:00")
        self._set_cell(r, 2, "08:45")
        for d in range(7):
            self._set_cell(r, 3 + d, "")
        self._update_count()

    def _del_row(self):
        r = self.table.currentRow()
        if r < 0:
            r = self.table.rowCount() - 1
        if r < 0:
            return
        self.table.removeRow(r)
        self._update_count()

    # ---------- 保存 ----------
    def _save(self):
        rows = self.table.rowCount()
        if rows == 0:
            QMessageBox.warning(self, "提示", "至少保留一节课")
            return
        periods = []
        timetable = {str(d): [] for d in range(7)}
        for r in range(rows):
            name = self._get_cell(r, 0) or f"第{r + 1}节"
            start = self._get_cell(r, 1)
            end = self._get_cell(r, 2)
            if not _valid_time(start):
                QMessageBox.warning(self, "格式错误",
                                    f"第 {r + 1} 行的开始时间格式无效：{start}")
                return
            if not _valid_time(end):
                QMessageBox.warning(self, "格式错误",
                                    f"第 {r + 1} 行的结束时间格式无效：{end}")
                return
            periods.append({"name": name, "start": start, "end": end})
            for d in range(7):
                timetable[str(d)].append(self._get_cell(r, 3 + d))
        self.schedule.update_timetable(self.name, periods, timetable)
        QMessageBox.information(self, "保存成功", f"课表“{self.name}”已保存")
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_played", False):
            self._played = True
            QTimer.singleShot(30, self, lambda: play_entrance(self._cards))

    # ---------- 导出 / 导入 ----------
    def _export_menu(self):
        menu = QMenu(self)
        act_json = menu.addAction("导出当前课表（JSON）")
        act_csv = menu.addAction("导出为 CSV（Excel 可打开）")
        menu.addSeparator()
        act_all = menu.addAction("导出全部课表 + 假期 / 周末设置（完整备份）")
        anchor = self.export_btn.mapToGlobal(QPoint(0, self.export_btn.height()))
        chosen = menu.exec(anchor)
        if chosen is None:
            return
        try:
            if chosen is act_csv:
                self._do_export('csv', [self.name])
            elif chosen is act_all:
                self._do_export('json', None, include_extras=True)
            else:
                self._do_export('json', [self.name])
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _do_export(self, fmt, names, include_extras=False):
        default = self.schedule.export_filename(
            fmt=fmt, names=names, include_extras=include_extras)
        flt = "CSV 文件 (*.csv)" if fmt == 'csv' else "JSON 文件 (*.json)"
        path, _ = QFileDialog.getSaveFileName(self, "导出课表", default, flt)
        if not path:
            return
        suffix = ".csv" if fmt == 'csv' else ".json"
        if not path.lower().endswith(suffix):
            path += suffix
        out = self.schedule.write_export(
            path, fmt=fmt, names=names, include_extras=include_extras)
        QMessageBox.information(self, "导出完成", f"文件已保存到：\n{out}")

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入课表", "",
            "课表文件 (*.json *.csv);;所有文件 (*)")
        if not path:
            return
        try:
            info = self.schedule.preview_file(path)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"无法读取该文件：\n{e}")
            return
        dlg = _ImportPreviewDialog(info, self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            result = self.schedule.import_file(path, mode=dlg.mode)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return
        QMessageBox.information(self, "导入完成",
                                TimetableManagerDialog._import_summary(result))
        self._load_to_table()


class _ImportPreviewDialog(QDialog):
    """导入课表前的预览与导入方式选择。"""

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.mode = 'merge'
        self.setWindowTitle("导入预览")
        self.resize(440, 420)
        _setup_dialog_style(self)
        L = QVBoxLayout(self)

        kind = info.get('kind')
        if info.get('format') == 'csv':
            head = "CSV 课表文件（单张课表，不含假期等设置）"
        elif kind == 'full':
            head = "JSON 完整备份（课表 + 假期/调休/周末等设置）"
        else:
            head = "JSON 课表文件"
        title = QLabel(head)
        title.setStyleSheet("font-weight: bold;")
        L.addWidget(title)

        lines = []
        for t in info.get('timetables', []):
            mark = "　⚠ 已有同名课表" if t.get('exists') else ""
            lines.append(f"· {t['name']}：{t['periods']} 节 / "
                         f"{t['courses']} 门课{mark}")
        if kind == 'full':
            ex = info.get('extras') or {}
            bits = []
            if ex.get('holidays'):
                bits.append(f"假期 {ex['holidays']} 天")
            if ex.get('makeup_days'):
                bits.append(f"调休 {ex['makeup_days']} 天")
            if ex.get('weekend'):
                bits.append("周末作息")
            if ex.get('advance_minutes') is not None:
                bits.append(f"提前提醒 {ex['advance_minutes']} 分钟")
            if ex.get('time_offset_seconds'):
                bits.append(f"时间偏移 {ex['time_offset_seconds']} 秒")
            lines.append("顺带带过来的设置：" + ("、".join(bits) if bits else "没有"))

        box = QLabel("\n".join(lines) if lines else "（空的）")
        box.setWordWrap(True)
        L.addWidget(box)

        for w in info.get('warnings', []):
            warn = QLabel(f"⚠ {w}")
            warn.setObjectName("hint")
            warn.setWordWrap(True)
            L.addWidget(warn)

        L.addSpacing(8)
        L.addWidget(QLabel("如何导入："))
        has_same = any(t.get('exists') for t in info.get('timetables', []))
        if kind == 'full':
            opts = [
                ('replace', "整体恢复：课表与假期安排全部替换为备份内容（将覆盖当前内容）"),
                ('merge', "只并课表：都当成新课表加进来，其他设置不动"),
            ]
            default = 'replace'
        else:
            opts = [
                ('merge', "合并：作为新课表导入"
                          + ("（同名自动改名为「xx (导入)」）" if has_same
                             else "")),
                ('replace', "覆盖同名课表（不存在的则新建）"),
            ]
            default = 'replace' if has_same else 'merge'
        self._modes = []
        group = QButtonGroup(self)
        for i, (mode, text) in enumerate(opts):
            rb = QRadioButton(text)
            rb.setChecked(mode == default)
            group.addButton(rb, i)
            self._modes.append((mode, rb))
            L.addWidget(rb)

        btns = QHBoxLayout()
        btns.addStretch()
        ok = QPushButton("导入")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        btns.addStretch()
        L.addLayout(btns)

    def accept(self):
        for mode, rb in self._modes:
            if rb.isChecked():
                self.mode = mode
                break
        super().accept()


class TimetableManagerDialog(QDialog):
    def __init__(self, schedule_manager, on_change=None, parent=None,
                 embedded=False):
        super().__init__(parent)
        self.schedule = schedule_manager
        self.on_change = on_change
        self.setWindowTitle("课表管理")
        self.resize(460, 500)
        if not embedded:
            _setup_dialog_style(self)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("选择课表（双击切换）"))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._switch_selected)
        layout.addWidget(self.list)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("课表名称："))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入名称后按回车创建")
        self.name_edit.returnPressed.connect(self._add)
        input_row.addWidget(self.name_edit, 1)
        layout.addLayout(input_row)

        row1 = QHBoxLayout()
        new_btn = QPushButton("新建")
        new_btn.clicked.connect(self._add)
        copy_btn = QPushButton("复制")
        copy_btn.clicked.connect(self._copy)
        rename_btn = QPushButton("重命名")
        rename_btn.clicked.connect(self._rename)
        del_btn = QPushButton("删除")
        del_btn.clicked.connect(self._delete)
        row1.addWidget(new_btn)
        row1.addWidget(copy_btn)
        row1.addWidget(rename_btn)
        row1.addWidget(del_btn)
        layout.addLayout(row1)
        row2 = QHBoxLayout()
        edit_btn = QPushButton("编辑选中的课表")
        edit_btn.clicked.connect(self._edit_selected)
        switch_btn = QPushButton("设为当前")
        switch_btn.clicked.connect(self._switch_selected)
        row2.addWidget(edit_btn)
        row2.addWidget(switch_btn)
        layout.addLayout(row2)
        row_io = QHBoxLayout()
        export_btn = QPushButton("导出课表…")
        export_btn.clicked.connect(self._export_menu)
        import_btn = QPushButton("导入课表…")
        import_btn.clicked.connect(self._import_file)
        row_io.addWidget(export_btn)
        row_io.addWidget(import_btn)
        layout.addLayout(row_io)
        restore_btn = QPushButton("恢复默认课表（将删除自定义课表）")
        restore_btn.clicked.connect(self._restore_default)
        layout.addWidget(restore_btn)
        bottom = QHBoxLayout()
        bottom.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        bottom.addStretch()
        layout.addLayout(bottom)
        self.refresh()

    def refresh(self):
        self.list.clear()
        active = self.schedule.active_name
        for name in self.schedule.list_timetables():
            tag = "  （当前）" if name == active else ""
            item = QListWidgetItem(f"{name}{tag}")
            item.setData(Qt.UserRole, name)
            self.list.addItem(item)

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.raise_()
        QTimer.singleShot(0, self.name_edit.setFocus)

    def _current_name(self):
        item = self.list.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选择一张课表")
            return None
        return item.data(Qt.UserRole)

    def _switch_selected(self, *_):
        name = self._current_name()
        if not name:
            return
        if self.schedule.switch_timetable(name):
            self.refresh()
            if self.on_change:
                self.on_change()

    def _select_name(self, name):
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.UserRole) == name:
                self.list.setCurrentItem(item)
                break

    def _after_change(self, select=None):
        self.refresh()
        if select:
            self._select_name(select)
        self.name_edit.clear()
        self.name_edit.setFocus()

    def _add(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.information(self, "提示", "请先输入课表名称")
            self.name_edit.setFocus()
            return
        if self.schedule.create_timetable(name):
            self._after_change(select=name)
        else:
            QMessageBox.warning(self, "操作失败", "该名称已存在或不可用")
            self.name_edit.selectAll()
            self.name_edit.setFocus()

    def _copy(self):
        src = self._current_name()
        if not src:
            return
        name = self.name_edit.text().strip() or f"{src} - 副本"
        if self.schedule.create_timetable(name, copy_from=src):
            self._after_change(select=name)
        else:
            QMessageBox.warning(self, "操作失败", "该名称已存在或不可用")
            self.name_edit.selectAll()
            self.name_edit.setFocus()

    def _rename(self):
        src = self._current_name()
        if not src:
            return
        new_name = self.name_edit.text().strip()
        if not new_name:
            QMessageBox.information(self, "提示", "请输入新的课表名称")
            self.name_edit.setFocus()
            return
        if self.schedule.rename_timetable(src, new_name):
            self._after_change(select=new_name)
            if self.on_change:
                self.on_change()
        else:
            QMessageBox.warning(self, "操作失败", "该名称已存在或不可用")
            self.name_edit.selectAll()
            self.name_edit.setFocus()

    def _delete(self):
        name = self._current_name()
        if not name:
            return
        if name == "默认课表":
            QMessageBox.information(self, "提示", "默认课表不能删除")
            return
        if QMessageBox.question(self, "确定吗",
                                f"真的要把“{name}”删掉吗？") != QMessageBox.Yes:
            return
        if self.schedule.delete_timetable(name):
            self.refresh()
            if self.on_change:
                self.on_change()
        else:
            QMessageBox.warning(self, "操作失败", "至少保留一张课表")

    def _edit_selected(self):
        name = self._current_name()
        if not name:
            return
        # 内嵌进设置窗口时由宿主接管：跳到内嵌的课表编辑器子页面，
        # 而不是再弹一个独立窗口
        cb = getattr(self, "edit_requested", None)
        if callable(cb):
            cb(name)
            return
        dlg = CourseEditor(self.schedule, self, timetable_name=name)
        if dlg.exec():
            self.refresh()
            if self.on_change:
                self.on_change()

    def _restore_default(self):
        if QMessageBox.question(
                self, "恢复默认",
                "恢复默认将删除所有自定义课表与临时调课，是否继续？"
        ) != QMessageBox.Yes:
            return
        self.schedule.restore_default()
        self.refresh()
        if self.on_change:
            self.on_change()
        QMessageBox.information(self, "提示", "已恢复默认课表")

    # ---------- 导出 / 导入 ----------
    def _export_target(self):
        """导出目标：选中的课表；没选就用当前使用的。"""
        item = self.list.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return self.schedule.active_name

    def _export_menu(self):
        btn = self.sender()
        menu = QMenu(self)
        act_sel = menu.addAction("导出选中课表（JSON）")
        act_all = menu.addAction("导出全部课表 + 假期/周末等设置（完整备份）")
        menu.addSeparator()
        act_csv = menu.addAction("导出选中课表为 CSV（Excel 可打开）")
        chosen = menu.exec(btn.mapToGlobal(QPoint(0, btn.height())))
        if chosen is None:
            return
        try:
            if chosen is act_all:
                self._do_export(fmt='json', names=None, include_extras=True)
            elif chosen is act_csv:
                self._do_export(fmt='csv', names=[self._export_target()])
            elif chosen is act_sel:
                self._do_export(fmt='json', names=[self._export_target()])
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _do_export(self, fmt, names, include_extras=False):
        default = self.schedule.export_filename(fmt=fmt, names=names,
                                                include_extras=include_extras)
        flt = "CSV 文件 (*.csv)" if fmt == 'csv' else "JSON 文件 (*.json)"
        path, _ = QFileDialog.getSaveFileName(self, "导出课表", default, flt)
        if not path:
            return
        suffix = ".csv" if fmt == 'csv' else ".json"
        if not path.lower().endswith(suffix):
            path += suffix
        out = self.schedule.write_export(path, fmt=fmt, names=names,
                                         include_extras=include_extras)
        QMessageBox.information(self, "导出完成", f"文件已保存到：\n{out}")

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入课表", "",
            "课表文件 (*.json *.csv);;所有文件 (*)")
        if not path:
            return
        try:
            info = self.schedule.preview_file(path)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"无法读取该文件：\n{e}")
            return
        dlg = _ImportPreviewDialog(info, self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            result = self.schedule.import_file(path, mode=dlg.mode)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return
        self.refresh()
        if self.on_change:
            self.on_change()
        QMessageBox.information(self, "导入完成", self._import_summary(result))

    @staticmethod
    def _import_summary(r):
        lines = []
        mode = str(r.get('mode', ''))
        if mode == 'replace/full':
            lines.append("整体恢复完成：课表与假期安排已替换为备份内容。")
        elif r.get('replaced'):
            lines.append("被换掉的同名课表：" + "、".join(r['replaced']))
        if r.get('added'):
            lines.append("加进来的课表：" + "、".join(r['added']))
        for old, new in r.get('renamed', []):
            lines.append(f"“{old}”已重命名为“{new}”")
        if r.get('removed'):
            lines.append("移走的：" + "、".join(r['removed']))
        if r.get('active'):
            lines.append(f"现在用的是：{r['active']}")
        for w in r.get('warnings', []):
            lines.append(f"⚠ {w}")
        return "\n".join(lines) or "完成"


class TempAdjustDialog(QDialog):
    def __init__(self, schedule_manager, parent=None):
        super().__init__(parent)
        self.schedule = schedule_manager
        self.setWindowTitle("临时调课")
        self.resize(560, 560)
        _setup_dialog_style(self)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("哪一天："))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self._load_for_date)
        top.addWidget(self.date_edit)
        self.week_label = QLabel()
        self.week_label.setObjectName("hint")
        top.addWidget(self.week_label)
        top.addStretch()
        layout.addLayout(top)
        tip = QLabel("双击“课程”列可修改，仅对所选日期生效。")
        tip.setObjectName("hint")
        layout.addWidget(tip)
        self.table = QTableWidget()
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        layout.addWidget(self.table)
        btns = QHBoxLayout()
        clear_btn = QPushButton("清除临时调课")
        clear_btn.clicked.connect(self._clear)
        btns.addWidget(clear_btn)
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        layout.addLayout(btns)
        self._load_for_date()

    def _weekday_index(self):
        return self.date_edit.date().dayOfWeek() - 1

    def _load_for_date(self):
        d = self.date_edit.date().toString("yyyy-MM-dd")
        self.week_label.setText(f"（{DAY_HEADERS[self._weekday_index()]}）")
        sel_date = self.date_edit.date().toPython()
        periods = self.schedule.periods_for(sel_date)
        rows = len(periods)
        self.table.setRowCount(rows)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(['节次 / 时间', '课程'])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        ta = self.schedule.get_temp_adjust()
        if ta.get('date') == d:
            courses = list(ta.get('courses', []))
        else:
            courses = self.schedule.courses_for(sel_date)
        for r, p in enumerate(periods):
            label = f"{p.get('name','')} {p.get('start','')}-{p.get('end','')}"
            it0 = QTableWidgetItem(label)
            it0.setFlags(Qt.ItemIsEnabled)
            it0.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 0, it0)
            course = courses[r] if r < len(courses) else ""
            it1 = QTableWidgetItem(course)
            it1.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 1, it1)

    def _clear(self):
        self.schedule.clear_temp_adjust()
        QMessageBox.information(self, "提示", "临时调课已清除")
        self._load_for_date()

    def _save(self):
        d = self.date_edit.date().toString("yyyy-MM-dd")
        courses = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            courses.append(item.text().strip() if item else "")
        self.schedule.set_temp_adjust(d, courses)
        QMessageBox.information(self, "保存成功", f"{d} 的临时课表已保存")
        self.accept()


class HolidayDialog(QDialog):
    """假期区间 + 调休上课日（全新界面）。"""

    def __init__(self, schedule_manager, parent=None, embedded=False):
        super().__init__(parent)
        self.schedule = schedule_manager
        self._cards = []

        self.setWindowTitle("假期与调休")
        self.resize(780, 660)
        self.setMinimumSize(660, 540)
        if not embedded:
            _setup_dialog_style(self)
        apply_modern_dialog(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(10)

        title = QLabel("假期与调休")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        sub = QLabel("一个悲伤的故事")
        sub.setObjectName("pageSub")
        sub.setWordWrap(True)
        root.addWidget(sub)
        root.addSpacing(6)

        # ---------- 假期区间 ----------
        card = SectionCard("放假的日期段", "可以加好几段")
        self.holiday_list = QListWidget()
        self.holiday_list.setMinimumHeight(150)
        card.add_widget(self.holiday_list)
        hrow = QHBoxLayout()
        hrow.setSpacing(8)
        self.h_start = QDateEdit()
        self.h_start.setCalendarPopup(True)
        self.h_start.setDisplayFormat("yyyy-MM-dd")
        self.h_start.setDate(QDate.currentDate())
        self.h_end = QDateEdit()
        self.h_end.setCalendarPopup(True)
        self.h_end.setDisplayFormat("yyyy-MM-dd")
        self.h_end.setDate(QDate.currentDate())
        self.h_name = QLineEdit()
        self.h_name.setPlaceholderText("起个名（可以不填，比如：国庆）")
        add_h = QPushButton("加上")
        add_h.setObjectName("primary")
        add_h.setCursor(Qt.PointingHandCursor)
        add_h.clicked.connect(self._add_holiday)
        del_h = QPushButton("删除选中项")
        del_h.setCursor(Qt.PointingHandCursor)
        del_h.clicked.connect(self._del_holiday)
        hrow.addWidget(QLabel("开始"))
        hrow.addWidget(self.h_start)
        hrow.addWidget(QLabel("结束"))
        hrow.addWidget(self.h_end)
        hrow.addWidget(self.h_name, 1)
        hrow.addWidget(add_h)
        hrow.addWidget(del_h)
        card.body.addLayout(hrow)
        root.addWidget(card, 1)
        self._cards.append(card)

        # ---------- 调休上课日 ----------
        card2 = SectionCard("要补课的日子", "周末和假期也得按“补周几”来上课")
        self.makeup_list = QListWidget()
        self.makeup_list.setMinimumHeight(130)
        card2.add_widget(self.makeup_list)
        mrow = QHBoxLayout()
        mrow.setSpacing(8)
        self.m_date = QDateEdit()
        self.m_date.setCalendarPopup(True)
        self.m_date.setDisplayFormat("yyyy-MM-dd")
        self.m_date.setDate(QDate.currentDate())
        self.m_wd = QComboBox()
        for i, name in enumerate(DAY_HEADERS):
            self.m_wd.addItem("补" + name, i)
        add_m = QPushButton("加上")
        add_m.setObjectName("primary")
        add_m.setCursor(Qt.PointingHandCursor)
        add_m.clicked.connect(self._add_makeup)
        del_m = QPushButton("删除选中项")
        del_m.setCursor(Qt.PointingHandCursor)
        del_m.clicked.connect(self._del_makeup)
        mrow.addWidget(QLabel("日期"))
        mrow.addWidget(self.m_date)
        mrow.addWidget(self.m_wd)
        mrow.addWidget(add_m)
        mrow.addWidget(del_m)
        mrow.addStretch(1)
        card2.body.addLayout(mrow)
        root.addWidget(card2, 1)
        self._cards.append(card2)

        foot = QHBoxLayout()
        foot.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("primary")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        root.addLayout(foot)

        self.refresh()

    def refresh(self):
        self.holiday_list.clear()
        for h in self.schedule.list_holidays():
            nm = h.get('name', '')
            text = f"{h.get('start')} ~ {h.get('end')}"
            if nm:
                text += f"    {nm}"
            self.holiday_list.addItem(text)
        self.makeup_list.clear()
        for m in self.schedule.list_makeups():
            try:
                wd = int(m.get('as_weekday', 0))
            except (TypeError, ValueError):
                wd = 0
            wd_name = DAY_HEADERS[wd] if 0 <= wd < 7 else '?'
            self.makeup_list.addItem(f"{m.get('date')}    补{wd_name}")

    def _add_holiday(self):
        if self.h_end.date() < self.h_start.date():
            QMessageBox.warning(self, "日期错误", "结束日期不能早于开始日期")
            return
        s = self.h_start.date().toString("yyyy-MM-dd")
        e = self.h_end.date().toString("yyyy-MM-dd")
        self.schedule.add_holiday(s, e, self.h_name.text())
        self.h_name.clear()
        self.refresh()

    def _del_holiday(self):
        i = self.holiday_list.currentRow()
        if i >= 0:
            self.schedule.remove_holiday(i)
            self.refresh()

    def _add_makeup(self):
        d = self.m_date.date().toString("yyyy-MM-dd")
        self.schedule.add_makeup(d, self.m_wd.currentData())
        self.refresh()

    def _del_makeup(self):
        i = self.makeup_list.currentRow()
        if i >= 0:
            self.schedule.remove_makeup(i)
            self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_played", False):
            self._played = True
            QTimer.singleShot(30, self, lambda: play_entrance(self._cards))


class WeekendScheduleDialog(QDialog):
    """全局周末作息：上午同工作日、下午自定义，周六日共用。"""

    def __init__(self, schedule_manager, parent=None, embedded=False):
        super().__init__(parent)
        self.schedule = schedule_manager
        self._morning_count = 0
        self.setWindowTitle("周末作息")
        self.resize(560, 640)
        if not embedded:
            _setup_dialog_style(self)
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("上午上到几点："))
        self.split_edit = QLineEdit(
            self.schedule.get_weekend().get('morning_split', '12:00'))
        self.split_edit.setFixedWidth(70)
        top.addWidget(self.split_edit)
        top.addWidget(QLabel("（比这个早的算上午，自动跟工作日一样）"))
        top.addStretch()
        layout.addLayout(top)

        layout.addWidget(QLabel("周六 / 周日共用"))
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(['节次', '开始', '结束', '课程'])
        header = self.table.horizontalHeader()
        for i in range(3):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.table)

        tools = QHBoxLayout()
        add_btn = QPushButton("添加下午课节")
        add_btn.clicked.connect(self._add_row)
        del_btn = QPushButton("删除选中课节")
        del_btn.clicked.connect(self._del_row)
        tools.addWidget(add_btn)
        tools.addWidget(del_btn)
        tools.addStretch()
        layout.addLayout(tools)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        btns.addStretch()
        layout.addLayout(btns)
        self._load()

    def _load(self):
        morning = self.schedule.morning_periods()
        self._morning_count = len(morning)
        afternoon = self.schedule.get_weekend().get('afternoon_periods', [])
        courses = self.schedule.get_weekend().get('courses', [])
        rows = morning + list(afternoon)
        self.table.setRowCount(len(rows))
        for r, p in enumerate(rows):
            self._set_cell(r, 0, p.get('name', f'第{r + 1}节'))
            self._set_cell(r, 1, p.get('start', ''))
            self._set_cell(r, 2, p.get('end', ''))
            self._set_cell(r, 3, courses[r] if r < len(courses) else '')
            if r < self._morning_count:
                for c in (0, 1, 2):
                    item = self.table.item(r, c)
                    if item:
                        item.setFlags(Qt.ItemIsEnabled)
                item = self.table.item(r, 0)
                if item:
                    item.setBackground(QColor(theme.color("disabled_row_bg")))

    def _set_cell(self, r, c, text):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(r, c, item)

    def _get_cell(self, r, c):
        item = self.table.item(r, c)
        return item.text().strip() if item else ''

    def _add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._set_cell(r, 0, f"第{r + 1}节")
        self._set_cell(r, 1, "14:00")
        self._set_cell(r, 2, "14:45")
        self._set_cell(r, 3, "")

    def _del_row(self):
        r = self.table.currentRow()
        if r < self._morning_count or r < 0:
            return
        self.table.removeRow(r)

    def _save(self):
        split = self.split_edit.text().strip() or "12:00"
        if not _valid_time(split):
            QMessageBox.warning(self, "格式错误", "上午截止时间需写成 HH:MM")
            return
        afternoon = []
        courses = []
        for r in range(self.table.rowCount()):
            courses.append(self._get_cell(r, 3))
            if r < self._morning_count:
                continue
            name = self._get_cell(r, 0) or f"第{r + 1}节"
            start = self._get_cell(r, 1)
            end = self._get_cell(r, 2)
            if not _valid_time(start) or not _valid_time(end):
                QMessageBox.warning(self, "格式错误",
                                    f"第 {r + 1} 行的时间格式无效")
                return
            afternoon.append({'name': name, 'start': start, 'end': end})
        self.schedule.set_weekend(split, afternoon, courses)
        QMessageBox.information(self, "保存成功", "周末作息已保存")
        self.accept()