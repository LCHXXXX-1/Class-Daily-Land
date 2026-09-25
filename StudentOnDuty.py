import os
from datetime import datetime

from paths import CONFIG_DIR
from storage import read_json, write_json, update_json

NAME_FILE = os.path.join(CONFIG_DIR, 'name.json')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

DEFAULT_DUTY = ['001', '002', '003', '004', '005']


class StudentOnDuty:
    def __init__(self):
        self.duty_list = self.load_duty_list()
        self.current_index = self.load_current_index()
        self.last_date = self.load_last_date()
        self.check_and_rotate()

    def load_duty_list(self):
        data = read_json(NAME_FILE)
        if isinstance(data, list) and data:
            return data
        self.save_duty_list(DEFAULT_DUTY)
        return DEFAULT_DUTY[:]

    def save_duty_list(self, data=None):
        if data is None:
            data = self.duty_list
        write_json(NAME_FILE, data)

    def load_current_index(self):
        data = read_json(CONFIG_FILE, default={})
        try:
            return int(data.get('current_index', 0))
        except (AttributeError, TypeError, ValueError):
            return 0

    def load_last_date(self):
        data = read_json(CONFIG_FILE, default={})
        if isinstance(data, dict):
            return data.get('last_date', '') or ''
        return ''

    def save_current_index(self):
        update_json(CONFIG_FILE, current_index=self.current_index,
                    last_date=self.last_date)

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
