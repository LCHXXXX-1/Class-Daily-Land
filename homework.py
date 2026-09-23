import os
import json
import sys


def get_app_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_ROOT = get_app_root()
CONFIG_DIR = os.path.join(APP_ROOT, 'settings')
HOMEWORK_FILE = os.path.join(CONFIG_DIR, 'homework.json')
os.makedirs(CONFIG_DIR, exist_ok=True)


class HomeworkManager:
    def __init__(self):
        self.homework_list = self.load_homework()

    def load_homework(self):
        if os.path.exists(HOMEWORK_FILE):
            with open(HOMEWORK_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                if data and isinstance(data[0], str):
                    new_data = [{'subject': '未分类', 'content': item, 'date': ''}
                                for item in data]
                    self.save_homework(new_data)
                    return new_data
                for item in data:
                    item.setdefault('date', '')
                return data
        return []

    def save_homework(self, data=None):
        if data is None:
            data = self.homework_list
        with open(HOMEWORK_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_all_homework(self):
        return self.homework_list[:]

    def get_grouped_homework(self):
        grouped = {}
        for idx, item in enumerate(self.homework_list):
            subject = item.get('subject', '未分类')
            if subject not in grouped:
                grouped[subject] = {
                    'contents': [],
                    'indices': [],
                    'date': item.get('date', ''),
                }
            grouped[subject]['contents'].append(item.get('content', ''))
            grouped[subject]['indices'].append(idx)
            if not grouped[subject]['date'] and item.get('date'):
                grouped[subject]['date'] = item['date']
        return grouped

    def add_homework(self, subject, content, date=None):
        if subject.strip() and content.strip():
            self.homework_list.append({
                'subject': subject.strip(),
                'content': content.strip(),
                'date': date or '',
            })
            self.save_homework()
            return True
        return False

    def remove_homework(self, index):
        if 0 <= index < len(self.homework_list):
            del self.homework_list[index]
            self.save_homework()
            return True
        return False

    def update_homework(self, index, subject, content, date):
        if 0 <= index < len(self.homework_list):
            item = self.homework_list[index]
            item['subject'] = subject.strip()
            item['content'] = content.strip()
            item['date'] = date
            self.save_homework()
            return True
        return False