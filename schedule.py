# -*- coding: utf-8 -*-
"""课表管理：多课表、临时调课、提前提醒、恢复默认"""
import os
import json
from datetime import datetime, timedelta

SCHEDULE_FILE = "schedule.json"
DEFAULT_NAME = "默认课表"

DEFAULT_PERIODS = [
    {"name": "第1节", "start": "08:00", "end": "08:45"},
    {"name": "第2节", "start": "08:55", "end": "09:40"},
    {"name": "第3节", "start": "10:00", "end": "10:45"},
    {"name": "第4节", "start": "10:55", "end": "11:40"},
    {"name": "第5节", "start": "14:00", "end": "14:45"},
    {"name": "第6节", "start": "14:55", "end": "15:40"},
    {"name": "第7节", "start": "16:00", "end": "16:45"},
    {"name": "第8节", "start": "16:55", "end": "17:40"},
]

DEFAULT_TIMETABLE = {
    "0": ["语文", "数学", "英语", "物理", "化学", "生物", "体育", "自习"],
    "1": ["数学", "英语", "语文", "化学", "物理", "体育", "自习", ""],
    "2": ["英语", "语文", "数学", "生物", "化学", "物理", "自习", ""],
    "3": ["物理", "化学", "数学", "语文", "英语", "生物", "体育", ""],
    "4": ["化学", "物理", "英语", "数学", "语文", "自习", "", ""],
    "5": [],
    "6": [],
}


def _default_data():
    return {
        "timetables": {
            DEFAULT_NAME: {
                "periods": [dict(p) for p in DEFAULT_PERIODS],
                "timetable": {k: list(v) for k, v in DEFAULT_TIMETABLE.items()},
            }
        },
        "active": DEFAULT_NAME,
        "temp_adjust": {"date": "", "courses": []},
        "advance_minutes": 2,
    }


class ScheduleManager:
    def __init__(self, config_dir):
        self.path = os.path.join(config_dir, SCHEDULE_FILE)
        self.data = _default_data()
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            self.save()
            return
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except Exception:
            self.data = _default_data()
            return

        if 'timetables' not in raw:
            self.data = _default_data()
            self.save()
            return

        self.data = raw
        self.data.setdefault('timetables', {})
        self.data.setdefault('active', DEFAULT_NAME)
        self.data.setdefault('temp_adjust', {"date": "", "courses": []})
        self.data.setdefault('advance_minutes', 2)

        if not self.data['timetables']:
            self.data['timetables'][DEFAULT_NAME] = {
                "periods": [dict(p) for p in DEFAULT_PERIODS],
                "timetable": {k: list(v) for k, v in DEFAULT_TIMETABLE.items()},
            }
        if self.data['active'] not in self.data['timetables']:
            self.data['active'] = next(iter(self.data['timetables']))

    def save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # ---------- 课表管理 ----------
    def list_timetables(self):
        return list(self.data['timetables'].keys())

    @property
    def active_name(self):
        return self.data['active']

    @property
    def periods(self):
        return self.data['timetables'][self.data['active']].get('periods', [])

    @property
    def timetable(self):
        return self.data['timetables'][self.data['active']].get('timetable', {})

    def get_timetable(self, name):
        return self.data['timetables'].get(name)

    def switch_timetable(self, name):
        if name in self.data['timetables']:
            self.data['active'] = name
            self.save()
            return True
        return False

    def create_timetable(self, name, copy_from=None):
        name = name.strip()
        if not name or name in self.data['timetables']:
            return False
        if copy_from and copy_from in self.data['timetables']:
            src = self.data['timetables'][copy_from]
            self.data['timetables'][name] = {
                "periods": [dict(p) for p in src.get('periods', [])],
                "timetable": {k: list(v) for k, v in src.get('timetable', {}).items()},
            }
        else:
            self.data['timetables'][name] = {
                "periods": [dict(p) for p in DEFAULT_PERIODS],
                "timetable": {k: list(v) for k, v in DEFAULT_TIMETABLE.items()},
            }
        self.save()
        return True

    def delete_timetable(self, name):
        if name == DEFAULT_NAME:
            return False
        if name not in self.data['timetables'] or len(self.data['timetables']) <= 1:
            return False
        del self.data['timetables'][name]
        if self.data['active'] == name:
            self.data['active'] = next(iter(self.data['timetables']))
        self.save()
        return True

    def rename_timetable(self, old, new):
        new = new.strip()
        if (old not in self.data['timetables'] or not new
                or new in self.data['timetables']):
            return False
        self.data['timetables'][new] = self.data['timetables'].pop(old)
        if self.data['active'] == old:
            self.data['active'] = new
        self.save()
        return True

    def update_timetable(self, name, periods, timetable):
        if name not in self.data['timetables']:
            return False
        self.data['timetables'][name] = {
            "periods": periods,
            "timetable": timetable,
        }
        self.save()
        return True

    def update(self, periods, timetable):
        return self.update_timetable(self.data['active'], periods, timetable)

    # ---------- 临时调课 ----------
    def get_temp_adjust(self):
        return dict(self.data.get('temp_adjust', {"date": "", "courses": []}))

    def set_temp_adjust(self, date_str, courses):
        self.data['temp_adjust'] = {"date": date_str, "courses": list(courses)}
        self.save()

    def clear_temp_adjust(self):
        self.data['temp_adjust'] = {"date": "", "courses": []}
        self.save()

    # ---------- 提前分钟 ----------
    @property
    def advance_minutes(self):
        return int(self.data.get('advance_minutes', 2))

    def set_advance_minutes(self, n):
        self.data['advance_minutes'] = max(0, min(60, int(n)))
        self.save()

    # ---------- 恢复默认 ----------
    def restore_default(self):
        self.data = _default_data()
        self.save()

    # ---------- 课程 ----------
    @staticmethod
    def _to_dt(t, base):
        h, m = t.split(':')
        return base.replace(hour=int(h), minute=int(m),
                            second=0, microsecond=0)

    def get_today_courses(self):
        today_str = datetime.now().strftime('%Y-%m-%d')
        ta = self.data.get('temp_adjust', {})
        if ta.get('date') == today_str:
            return list(ta.get('courses', []))
        weekday = str(datetime.now().weekday())
        return list(self.timetable.get(weekday, []))

    def get_today(self):
        return self.get_today_courses()

    def get_status(self):
        now = datetime.now()
        courses = self.get_today_courses()
        periods = self.periods

        if not any(c and c.strip() for c in courses):
            return {'status': 'none'}

        advance_sec = self.advance_minutes * 60

        for i, period in enumerate(periods):
            course = courses[i] if i < len(courses) else ""
            if not course or not course.strip():
                continue
            try:
                start = self._to_dt(period['start'], now)
                end = self._to_dt(period['end'], now)
            except Exception:
                continue

            target = start - timedelta(seconds=advance_sec)

            # 已到"目标时刻"且未下课 → 上课中
            if target <= now <= end:
                remain_sec = max(0, int((end - now).total_seconds()))
                remain_min = max(1, (remain_sec + 59) // 60)
                return {
                    'status': 'ongoing',
                    'course': course,
                    'period': period['name'],
                    'start': period['start'],
                    'end': period['end'],
                    'remain_sec': remain_sec,
                    'remain_min': remain_min,
                    'index': i,
                }

            # 未到目标时刻 → 下节
            if now < target:
                until_sec = max(0, int((target - now).total_seconds()))
                return {
                    'status': 'upcoming',
                    'course': course,
                    'period': period['name'],
                    'start': period['start'],
                    'until_sec': until_sec,
                    'until_min': max(1, (until_sec + 59) // 60),
                    'advance_sec': advance_sec,
                    'index': i,
                }

        return {'status': 'done'}