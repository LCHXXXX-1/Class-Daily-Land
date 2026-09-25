import os

from paths import CONFIG_DIR
from storage import read_json, write_json

HOMEWORK_FILE = os.path.join(CONFIG_DIR, 'homework.json')


class HomeworkManager:
    def __init__(self):
        self.homework_list = self.load_homework()

    def load_homework(self):
        data = read_json(HOMEWORK_FILE)
        if not isinstance(data, list):
            return []
        if data and isinstance(data[0], str):
            new_data = [{'subject': '未分类', 'content': item, 'date': ''}
                        for item in data]
            self.save_homework(new_data)
            return new_data
        for item in data:
            if isinstance(item, dict):
                item.setdefault('date', '')
        return [it for it in data if isinstance(it, dict)]

    def save_homework(self, data=None):
        if data is None:
            data = self.homework_list
        write_json(HOMEWORK_FILE, data)

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
