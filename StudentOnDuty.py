import os
import json
import sys
from datetime import datetime


def get_app_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_ROOT = get_app_root()
CONFIG_DIR = os.path.join(APP_ROOT, 'settings')
NAME_FILE = os.path.join(CONFIG_DIR, 'name.json')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
os.makedirs(CONFIG_DIR, exist_ok=True)

DEFAULT_DUTY = ['001', '002', '003', '004', '005']


class StudentOnDuty:
    def __init__(self):
        self.duty_list = self.load_duty_list()
        self.current_index = self.load_current_index()
        self.last_date = self.load_last_date()
        self.check_and_rotate()

    def load_duty_list(self):
        if os.path.exists(NAME_FILE):
            with open(NAME_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
        self.save_duty_list(DEFAULT_DUTY)
        return DEFAULT_DUTY[:]

    def save_duty_list(self, data=None):
        if data is None:
            data = self.duty_list
        with open(NAME_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_current_index(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('current_index', 0)
        return 0

    def load_last_date(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('last_date', '')
        return ''

    def save_current_index(self):
        data = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        data['current_index'] = self.current_index
        data['last_date'] = self.last_date
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def check_and_rotate(self):
        today = datetime.now().strftime('%Y-%m-%d')
        if self.last_date != today:
            if self.duty_list:
                self.current_index = (self.current_index + 1) % len(self.duty_list)
            self.last_date = today
            self.save_current_index()

    def get_current_duty(self):
        return self.duty_list[self.current_index] if self.duty_list else "无"

    def next_duty(self):
        if not self.duty_list:
            return
        self.current_index = (self.current_index + 1) % len(self.duty_list)
        self.last_date = datetime.now().strftime('%Y-%m-%d')
        self.save_current_index()
        return self.get_current_duty()

    def previous_duty(self):
        if not self.duty_list:
            return
        self.current_index = (self.current_index - 1) % len(self.duty_list)
        self.last_date = datetime.now().strftime('%Y-%m-%d')
        self.save_current_index()
        return self.get_current_duty()

    def add_duty(self, name):
        self.duty_list.append(name)
        self.save_duty_list()

    def add_duties(self, names):
        for name in names:
            if name.strip():
                self.duty_list.append(name.strip())
        self.save_duty_list()

    def remove_duty(self, index):
        if 0 <= index < len(self.duty_list):
            del self.duty_list[index]
            self.save_duty_list()
            if self.current_index >= len(self.duty_list):
                self.current_index = 0
                self.save_current_index()