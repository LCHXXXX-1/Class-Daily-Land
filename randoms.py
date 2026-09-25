import os
import json
import random

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QFileDialog, QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from paths import CONFIG_DIR
from utils import set_window_icon

COOLDOWN = 10
DEFAULT_JSON = os.path.join(CONFIG_DIR, 'name.json')


class RollCallDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("随机点名器")
        self.resize(520, 360)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        set_window_icon(self)
        self.names = []
        self.recent = []
        layout = QVBoxLayout(self)
        self.name_label = QLabel("随机点名")
        self.name_label.setAlignment(Qt.AlignCenter)
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(48)
        font.setBold(True)
        self.name_label.setFont(font)
        layout.addWidget(self.name_label, stretch=1)
        self.status_label = QLabel("请打开名单文件")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        btns = QHBoxLayout()
        btns.addStretch()
        open_btn = QPushButton("打开文件")
        open_btn.setFixedSize(120, 50)
        open_btn.clicked.connect(self.open_file)
        pick_btn = QPushButton("随  机")
        pick_btn.setFixedSize(120, 50)
        pick_btn.clicked.connect(self.pick)
        btns.addWidget(open_btn)
        btns.addWidget(pick_btn)
        btns.addStretch()
        layout.addLayout(btns)
        self._auto_load()

    def _auto_load(self):
        if os.path.isfile(DEFAULT_JSON):
            if self._load(DEFAULT_JSON):
                self.status_label.setText(
                    f"已自动加载 name.json（{len(self.names)} 人）")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择名单文件", "", "JSON 文件 (*.json);;所有文件 (*.*)")
        if not path:
            return
        if self._load(path):
            self.status_label.setText(
                f"已加载 {os.path.basename(path)}（{len(self.names)} 人）")

    def _load(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "读取失败", f"无法读取文件：\n{e}")
            return False
        if isinstance(data, dict):
            data = data.get("names", [])
        if not isinstance(data, list):
            QMessageBox.critical(self, "格式错误", '文件内容应为数组')
            return False
        names = [str(x).strip() for x in data if str(x).strip()]
        if not names:
            QMessageBox.critical(self, "名单为空", "文件里没有有效的名字。")
            return False
        self.names = names
        self.recent = []
        self.name_label.setText("随机点名")
        return True

    def pick(self):
        if not self.names:
            QMessageBox.information(self, "提示", "请先打开名单文件。")
            return
        candidates = [n for n in self.names if n not in self.recent]
        if not candidates:
            last = self.recent[-1] if self.recent else None
            self.recent = [last] if last else []
            candidates = [n for n in self.names if n != last]
            if not candidates:
                candidates = self.names[:]
        name = random.choice(candidates)
        self.recent.append(name)
        if len(self.recent) > COOLDOWN:
            self.recent.pop(0)
        self.name_label.setText(name)


def main(parent=None):
    dlg = RollCallDialog(parent)
    dlg.exec()