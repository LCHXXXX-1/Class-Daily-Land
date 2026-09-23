import re
from datetime import datetime

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QTextEdit, QPushButton, QComboBox,
                               QScrollArea, QWidget, QMessageBox, QTableWidget,
                               QTableWidgetItem, QHeaderView, QAbstractItemView,
                               QListWidget, QListWidgetItem, QSpinBox, QDateEdit,
                               QInputDialog)
from PySide6.QtCore import Qt, QDate
from utils import set_window_icon

FONT_SIZE = 14
DAY_HEADERS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()


def _valid_time(s):
    return bool(re.match(r'^\d{1,2}:\d{2}$', str(s).strip()))


def _setup_dialog_style(dlg):
    dlg.setWindowFlags(
        (dlg.windowFlags() & ~Qt.WindowStaysOnTopHint)
        | Qt.Window
        | Qt.WindowSystemMenuHint
        | Qt.WindowMinimizeButtonHint
        | Qt.WindowMaximizeButtonHint
        | Qt.WindowCloseButtonHint
    )
    dlg.setAttribute(Qt.WA_NativeWindow, True)
    set_window_icon(dlg)


class AttendanceDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle("修改出勤")
        self.resize(350, 200)
        _setup_dialog_style(self)
        layout = QVBoxLayout(self)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("应到："))
        self.should_edit = QLineEdit(app.should)
        row1.addWidget(self.should_edit)
        layout.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("实到："))
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
            QMessageBox.warning(self, "格式错误", "请输入有效数字")


class DutyEditor(QDialog):
    def __init__(self, duty_manager, app, parent=None):
        super().__init__(parent)
        self.duty_manager = duty_manager
        self.app = app
        self.setWindowTitle("编辑值日生")
        self.resize(500, 420)
        _setup_dialog_style(self)
        layout = QVBoxLayout(self)
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("单个添加："))
        self.single_edit = QLineEdit()
        add_row.addWidget(self.single_edit)
        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self._add_single)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)
        batch_btn = QPushButton("批量添加（逗号分隔）")
        batch_btn.clicked.connect(self._open_batch)
        layout.addWidget(batch_btn)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.inner)
        layout.addWidget(self.scroll)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)
        self.refresh()

    def refresh(self):
        _clear_layout(self.inner_layout)
        names = self.duty_manager.duty_list
        if not names:
            self.inner_layout.addWidget(QLabel("无值日生"))
            return
        for i, name in enumerate(names):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.addWidget(QLabel(f"{i + 1}. {name}"))
            rl.addStretch()
            del_btn = QPushButton("×")
            del_btn.setFixedWidth(30)
            del_btn.clicked.connect(lambda _, idx=i: self._delete(idx))
            rl.addWidget(del_btn)
            self.inner_layout.addWidget(row)

    def _add_single(self):
        name = self.single_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入姓名")
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
        layout.addWidget(QLabel("请输入姓名（以逗号分隔）："))
        text = QTextEdit()
        layout.addWidget(text)
        btns = QHBoxLayout()
        btns.addStretch()

        def do_add():
            raw = text.toPlainText().strip()
            names = [n.strip() for n in raw.split(',') if n.strip()]
            if not names:
                QMessageBox.warning(dlg, "提示", "请输入有效姓名")
                return
            for n in names:
                self.duty_manager.add_duty(n)
            dlg.accept()
            self.refresh()
            self.app.update_display()

        ok = QPushButton("确定添加")
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
    def __init__(self, homework_manager, app, parent=None):
        super().__init__(parent)
        self.hw = homework_manager
        self.app = app
        self.setWindowTitle("编辑作业")
        self.resize(700, 600)
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
        row2.addWidget(QLabel("提交日期（自定义）："))
        self.date_edit = QLineEdit()
        self.date_edit.setFixedWidth(200)
        row2.addWidget(self.date_edit)
        row2.addStretch()
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("内容："), alignment=Qt.AlignTop)
        self.content_edit = QTextEdit()
        self.content_edit.setFixedHeight(70)
        row3.addWidget(self.content_edit)
        layout.addLayout(row3)

        add_btn = QPushButton("添加")
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
            self.inner_layout.addWidget(QLabel("无作业"))
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
            clear_btn = QPushButton("清空")
            clear_btn.setFixedWidth(60)
            clear_btn.clicked.connect(lambda _, s=subject: self._clear_subject(s))
            hl.addWidget(clear_btn)
            hl.addStretch()
            self.inner_layout.addWidget(hdr)
            for content, real_idx in zip(data['contents'], data['indices']):
                row = QWidget()
                rl = QHBoxLayout(row)
                rl.setContentsMargins(20, 0, 0, 0)
                rl.addWidget(QLabel(f"{real_idx + 1}. {content}"))
                del_btn = QPushButton("×")
                del_btn.setFixedWidth(30)
                del_btn.clicked.connect(lambda _, i=real_idx: self._delete(i))
                rl.addWidget(del_btn)
                edit_btn = QPushButton("编辑")
                edit_btn.setFixedWidth(50)
                edit_btn.clicked.connect(lambda _, i=real_idx: self._edit(i))
                rl.addWidget(edit_btn)
                self.inner_layout.addWidget(row)

    def _add(self):
        subject = self.subject_edit.text().strip()
        date = self.date_edit.text().strip()
        content = self.content_edit.toPlainText().strip()
        if not subject:
            QMessageBox.warning(self, "提示", "请输入科目")
            return
        if not content:
            QMessageBox.warning(self, "提示", "请输入作业内容")
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
        layout.addWidget(QLabel("内容："))
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
        cancel = QPushButton("取消")
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
    def __init__(self, schedule_manager, parent=None, timetable_name=None):
        super().__init__(parent)
        self.schedule = schedule_manager
        self.name = timetable_name or schedule_manager.active_name
        self.setWindowTitle(f"编辑课表 - {self.name}")
        self.resize(900, 600)
        _setup_dialog_style(self)
        layout = QVBoxLayout(self)
        tip = QLabel("双击单元格编辑。时间格式：HH:MM（例 08:00）")
        tip.setStyleSheet("color: #666;")
        layout.addWidget(tip)
        self.table = QTableWidget()
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        layout.addWidget(self.table)
        tools = QHBoxLayout()
        add_row_btn = QPushButton("添加节次")
        add_row_btn.clicked.connect(self._add_row)
        del_row_btn = QPushButton("删除选中节次")
        del_row_btn.clicked.connect(self._del_row)
        tools.addWidget(add_row_btn)
        tools.addWidget(del_row_btn)
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
        self._load_to_table()

    def _load_to_table(self):
        tt = self.schedule.get_timetable(self.name)
        if not tt:
            QMessageBox.warning(self, "错误", "课表不存在")
            self.reject()
            return
        periods = tt.get('periods', [])
        timetable = tt.get('timetable', {})
        rows = len(periods)
        cols = 3 + 7
        self.table.setRowCount(rows)
        self.table.setColumnCount(cols)
        self.table.setHorizontalHeaderLabels(['节次', '开始', '结束'] + DAY_HEADERS)
        header = self.table.horizontalHeader()
        for i in range(cols):
            if i < 3:
                header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
            else:
                header.setSectionResizeMode(i, QHeaderView.Stretch)
        for r, p in enumerate(periods):
            self._set_cell(r, 0, p.get('name', f'第{r+1}节'))
            self._set_cell(r, 1, p.get('start', ''))
            self._set_cell(r, 2, p.get('end', ''))
            for d in range(7):
                day_list = timetable.get(str(d), [])
                course = day_list[r] if r < len(day_list) else ''
                self._set_cell(r, 3 + d, course)

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
        self._set_cell(r, 1, "08:00")
        self._set_cell(r, 2, "08:45")
        for d in range(7):
            self._set_cell(r, 3 + d, "")

    def _del_row(self):
        r = self.table.currentRow()
        if r < 0:
            r = self.table.rowCount() - 1
        if r < 0:
            return
        self.table.removeRow(r)

    def _save(self):
        periods = []
        timetable = {str(d): [] for d in range(7)}
        rows = self.table.rowCount()
        if rows == 0:
            QMessageBox.warning(self, "提示", "至少保留一节")
            return
        for r in range(rows):
            name = self._get_cell(r, 0) or f"第{r + 1}节"
            start = self._get_cell(r, 1)
            end = self._get_cell(r, 2)
            if not _valid_time(start):
                QMessageBox.warning(self, "格式错误",
                                    f"第 {r + 1} 行开始时间格式错误：{start}")
                return
            if not _valid_time(end):
                QMessageBox.warning(self, "格式错误",
                                    f"第 {r + 1} 行结束时间格式错误：{end}")
                return
            periods.append({'name': name, 'start': start, 'end': end})
            for d in range(7):
                timetable[str(d)].append(self._get_cell(r, 3 + d))
        self.schedule.update_timetable(self.name, periods, timetable)
        QMessageBox.information(self, "已保存", f"课表“{self.name}”已保存")
        self.accept()


class TimetableManagerDialog(QDialog):
    def __init__(self, schedule_manager, on_change=None, parent=None):
        super().__init__(parent)
        self.schedule = schedule_manager
        self.on_change = on_change
        self.setWindowTitle("课表管理")
        self.resize(460, 500)
        _setup_dialog_style(self)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("选择要使用的课表（双击切换）："))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._switch_selected)
        layout.addWidget(self.list)
        row1 = QHBoxLayout()
        new_btn = QPushButton("新建")
        new_btn.clicked.connect(self._new)
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
        edit_btn = QPushButton("编辑选中课表")
        edit_btn.clicked.connect(self._edit_selected)
        switch_btn = QPushButton("设为当前")
        switch_btn.clicked.connect(self._switch_selected)
        row2.addWidget(edit_btn)
        row2.addWidget(switch_btn)
        layout.addLayout(row2)
        restore_btn = QPushButton("恢复默认课表（清除全部自定义）")
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
            tag = "  (当前)" if name == active else ""
            item = QListWidgetItem(f"{name}{tag}")
            item.setData(Qt.UserRole, name)
            self.list.addItem(item)

    def _current_name(self):
        item = self.list.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选择一个课表")
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

    def _new(self):
        name, ok = QInputDialog.getText(self, "新建课表", "课表名称：")
        if not ok or not name.strip():
            return
        if self.schedule.create_timetable(name.strip()):
            self.refresh()
        else:
            QMessageBox.warning(self, "失败", "名称已存在或无效")

    def _copy(self):
        name = self._current_name()
        if not name:
            return
        new_name, ok = QInputDialog.getText(
            self, "复制课表", "新名称：", text=f"{name} - 副本")
        if not ok or not new_name.strip():
            return
        if self.schedule.create_timetable(new_name.strip(), copy_from=name):
            self.refresh()
        else:
            QMessageBox.warning(self, "失败", "名称已存在或无效")

    def _rename(self):
        name = self._current_name()
        if not name:
            return
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称：", text=name)
        if not ok or not new_name.strip():
            return
        if self.schedule.rename_timetable(name, new_name.strip()):
            self.refresh()
            if self.on_change:
                self.on_change()
        else:
            QMessageBox.warning(self, "失败", "名称已存在或无效")

    def _delete(self):
        name = self._current_name()
        if not name:
            return
        if name == "默认课表":
            QMessageBox.information(self, "提示", "默认课表不可删除")
            return
        if QMessageBox.question(self, "确认",
                                f"确定删除课表“{name}”？") != QMessageBox.Yes:
            return
        if self.schedule.delete_timetable(name):
            self.refresh()
            if self.on_change:
                self.on_change()
        else:
            QMessageBox.warning(self, "失败", "删除失败（至少保留一个课表）")

    def _edit_selected(self):
        name = self._current_name()
        if not name:
            return
        dlg = CourseEditor(self.schedule, self, timetable_name=name)
        if dlg.exec():
            self.refresh()
            if self.on_change:
                self.on_change()

    def _restore_default(self):
        if QMessageBox.question(
                self, "确认",
                "恢复默认课表将清除所有自定义课表和临时调课，确定吗？"
        ) != QMessageBox.Yes:
            return
        self.schedule.restore_default()
        self.refresh()
        if self.on_change:
            self.on_change()
        QMessageBox.information(self, "完成", "已恢复默认课表")


class TempAdjustDialog(QDialog):
    def __init__(self, schedule_manager, parent=None):
        super().__init__(parent)
        self.schedule = schedule_manager
        self.setWindowTitle("临时调课")
        self.resize(560, 560)
        _setup_dialog_style(self)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("生效日期："))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self._load_for_date)
        top.addWidget(self.date_edit)
        self.week_label = QLabel()
        self.week_label.setStyleSheet("color: #666;")
        top.addWidget(self.week_label)
        top.addStretch()
        layout.addLayout(top)
        tip = QLabel("双击“课程”列编辑，只影响上面选中的日期。")
        tip.setStyleSheet("color: #666;")
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
        periods = self.schedule.periods
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
            courses = list(self.schedule.timetable.get(
                str(self._weekday_index()), []))
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
        QMessageBox.information(self, "已清除", "临时调课已清除")
        self._load_for_date()

    def _save(self):
        d = self.date_edit.date().toString("yyyy-MM-dd")
        courses = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            courses.append(item.text().strip() if item else "")
        self.schedule.set_temp_adjust(d, courses)
        QMessageBox.information(self, "已保存", f"已为 {d} 设置临时课表")
        self.accept()