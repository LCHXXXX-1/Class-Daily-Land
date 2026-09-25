import os
import json
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                               QTextEdit, QPushButton)
from PySide6.QtCore import Qt
from utils import set_window_icon

AGREEMENT_FILE = "agreement.json"

AGREEMENT_TEXT = """
欢迎使用“Class Daily Land”软件（以下简称“本软件”）。

在使用本软件前，请您仔细阅读以下条款：

1. 本软件为免费软件，仅供个人学习、班级管理使用。
2. 您承诺不将本软件用于任何非法或违反道德的活动。
3. 本软件作者不对因使用本软件产生的任何数据丢失或损坏负责。
4. 您的使用数据（如值日名单、作业记录）仅保存在本地，不会上传至任何服务器。
5. 软件更新时会自动检查新版本，有新版本时您可自主选择更新。

如您同意以上条款，请点击“同意”继续使用；否则请点击“不同意”退出。

（本协议最终解释权归作者所有）
"""


def get_agreement_path(config_dir):
    return os.path.join(config_dir, AGREEMENT_FILE)


def load_agreement_status(config_dir):
    path = get_agreement_path(config_dir)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f).get('agreed', False)
        except Exception:
            return False
    return False


def save_agreement_status(config_dir, agreed):
    path = get_agreement_path(config_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'agreed': agreed}, f, ensure_ascii=False, indent=2)


class AgreementDialog(QDialog):
    def __init__(self, config_dir, parent=None):
        super().__init__(parent)
        self.config_dir = config_dir
        self.setWindowTitle("用户协议")
        self.resize(500, 400)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        set_window_icon(self)

        layout = QVBoxLayout(self)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(AGREEMENT_TEXT)
        layout.addWidget(self.text)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        agree = QPushButton("同意")
        agree.clicked.connect(self._on_agree)
        disagree = QPushButton("不同意")
        disagree.clicked.connect(self.reject)
        btn_layout.addWidget(agree)
        btn_layout.addWidget(disagree)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _on_agree(self):
        save_agreement_status(self.config_dir, True)
        self.accept()


def check_agreement(config_dir, parent=None):
    if load_agreement_status(config_dir):
        return True
    dlg = AgreementDialog(config_dir, parent)
    return dlg.exec() == QDialog.Accepted