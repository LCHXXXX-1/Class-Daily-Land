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
        "time_offset_seconds": 0,
        "holidays": [],
        "makeup_days": [],
        "weekend": {"morning_split": "12:00", "afternoon_periods": [],
                    "courses": []},
    }


def _as_date(d):
    if d is None:
        return datetime.now().date()
    if isinstance(d, datetime):
        return d.date()
    return d


def _hhmm_before(t, split):
    try:
        th, tm = (int(x) for x in str(t).split(':')[:2])
        sh, sm = (int(x) for x in str(split).split(':')[:2])
        return (th, tm) < (sh, sm)
    except Exception:
        return False


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
        if ('time_offset_seconds' not in self.data
                and 'time_offset_minutes' in self.data):
            try:
                self.data['time_offset_seconds'] = (
                    int(self.data['time_offset_minutes']) * 60)
            except (TypeError, ValueError):
                self.data['time_offset_seconds'] = 0
        self.data.pop('time_offset_minutes', None)
        self.data.setdefault('time_offset_seconds', 0)
        self.data.setdefault('holidays', [])
        self.data.setdefault('makeup_days', [])
        if not isinstance(self.data.get('weekend'), dict):
            self.data['weekend'] = {"morning_split": "12:00",
                                    "afternoon_periods": [], "courses": []}
        else:
            self.data['weekend'].setdefault('morning_split', '12:00')
            self.data['weekend'].setdefault('afternoon_periods', [])
            self.data['weekend'].setdefault('courses', [])

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

    # ---------- 时间偏移（秒） ----------
    @property
    def time_offset_seconds(self):
        try:
            return int(self.data.get('time_offset_seconds', 0))
        except (TypeError, ValueError):
            return 0

    def set_time_offset_seconds(self, n):
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = 0
        self.data['time_offset_seconds'] = max(-1800, min(1800, n))
        self.save()

    def offset_time_str(self, t):
        """按时间偏移把 "HH:MM" 换算为新的 "HH:MM"。"""
        if not self.time_offset_seconds:
            return t
        try:
            h, m = str(t).split(':')
            base = datetime.now().replace(hour=int(h), minute=int(m),
                                          second=0, microsecond=0)
        except Exception:
            return t
        shifted = base + timedelta(seconds=self.time_offset_seconds)
        return shifted.strftime('%H:%M')

    # ---------- 假期 / 调休 ----------
    def list_holidays(self):
        return list(self.data.get('holidays', []))

    def add_holiday(self, start, end, name=''):
        start = str(start).strip()
        end = str(end).strip() or start
        if end < start:
            start, end = end, start
        self.data.setdefault('holidays', []).append(
            {"start": start, "end": end, "name": str(name).strip()})
        self.save()

    def remove_holiday(self, index):
        hs = self.data.get('holidays', [])
        if 0 <= index < len(hs):
            del hs[index]
            self.save()
            return True
        return False

    def get_holiday(self, d=None):
        ds = _as_date(d).strftime('%Y-%m-%d')
        for h in self.data.get('holidays', []):
            if str(h.get('start', '')) <= ds <= str(h.get('end', '')):
                return h
        return None

    def is_holiday(self, d=None):
        return self.get_holiday(d) is not None

    def list_makeups(self):
        return list(self.data.get('makeup_days', []))

    def add_makeup(self, date, as_weekday):
        try:
            as_weekday = int(as_weekday)
        except (TypeError, ValueError):
            as_weekday = 0
        self.data.setdefault('makeup_days', []).append(
            {"date": str(date).strip(), "as_weekday": max(0, min(6, as_weekday))})
        self.save()

    def remove_makeup(self, index):
        ms = self.data.get('makeup_days', [])
        if 0 <= index < len(ms):
            del ms[index]
            self.save()
            return True
        return False

    def makeup_weekday(self, d=None):
        ds = _as_date(d).strftime('%Y-%m-%d')
        for m in self.data.get('makeup_days', []):
            if str(m.get('date', '')) == ds:
                try:
                    return int(m.get('as_weekday', 0))
                except (TypeError, ValueError):
                    return 0
        return None

    # ---------- 周末作息 ----------
    def get_weekend(self):
        return dict(self.data.get('weekend', {}))

    def set_weekend(self, morning_split, afternoon_periods, courses):
        self.data['weekend'] = {
            "morning_split": str(morning_split or "12:00"),
            "afternoon_periods": list(afternoon_periods or []),
            "courses": list(courses or []),
        }
        self.save()

    def morning_periods(self):
        split = self.data.get('weekend', {}).get('morning_split', '12:00')
        return [dict(p) for p in self.periods
                if _hhmm_before(p.get('start', ''), split)]

    def _weekend_periods(self):
        return self.morning_periods() + [
            dict(p) for p in self.data.get('weekend', {}).get(
                'afternoon_periods', [])]

    # ---------- 当天有效作息 / 课程 ----------
    def periods_for(self, d=None):
        d = _as_date(d)
        if self.makeup_weekday(d) is not None:
            return list(self.periods)
        if self.is_holiday(d):
            return []
        if d.weekday() >= 5:
            return self._weekend_periods()
        return list(self.periods)

    def courses_for(self, d=None):
        d = _as_date(d)
        wd = self.makeup_weekday(d)
        if wd is not None:
            return list(self.timetable.get(str(wd), []))
        if self.is_holiday(d):
            return []
        if d.weekday() >= 5:
            return list(self.data.get('weekend', {}).get('courses', []))
        return list(self.timetable.get(str(d.weekday()), []))

    def next_class_date(self, d, limit=20):
        d = _as_date(d)
        for i in range(1, limit + 1):
            nd = d + timedelta(days=i)
            if self.makeup_weekday(nd) is not None:
                return nd
            if self.is_holiday(nd):
                continue
            if nd.weekday() < 5:
                return nd
        return None

    def next_holiday_start(self, d, limit=20):
        d = _as_date(d)
        for i in range(1, limit + 1):
            nd = d + timedelta(days=i)
            if self.is_holiday(nd) and self.makeup_weekday(nd) is None:
                return nd
        return None

    def is_last_school_day_before_holiday(self, d=None):
        d = _as_date(d)
        if self.makeup_weekday(d) is None and self.is_holiday(d):
            return False
        nh = self.next_holiday_start(d)
        if nh is None:
            return False
        nc = self.next_class_date(d)
        return nc is None or nh < nc

    def last_course_end_today(self, now=None):
        """今天最后一节非空课程的下课时间（datetime），无课返回 None。"""
        now = now or datetime.now()
        courses = self.get_today_courses(now)
        periods = self.periods_for(now)
        last = None
        for i, c in enumerate(courses):
            if c and c.strip() and i < len(periods):
                try:
                    last = self._to_dt(periods[i]['end'], now)
                except Exception:
                    continue
        if last is None:
            return None
        return last + timedelta(seconds=self.time_offset_seconds)

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

    def get_today_courses(self, now=None):
        now = now or datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        ta = self.data.get('temp_adjust', {})
        if ta.get('date') == today_str:
            return list(ta.get('courses', []))
        return self.courses_for(now)

    def get_today(self, now=None):
        return self.get_today_courses(now)

    def get_status(self, now=None, advance_minutes=None, offset_seconds=None):
        now = now or datetime.now()
        if advance_minutes is None:
            advance_minutes = self.advance_minutes
        if offset_seconds is None:
            offset_seconds = self.time_offset_seconds

        ta = self.data.get('temp_adjust', {})
        temp_today = ta.get('date') == now.strftime('%Y-%m-%d')
        if (not temp_today and self.makeup_weekday(now) is None
                and self.is_holiday(now)):
            h = self.get_holiday(now) or {}
            return {'status': 'holiday', 'name': h.get('name', '')}

        courses = self.get_today_courses(now)
        periods = self.periods_for(now)

        if not any(c and c.strip() for c in courses):
            return {'status': 'none'}

        advance_sec = int(advance_minutes) * 60
        advance = timedelta(minutes=int(advance_minutes))

        for i, period in enumerate(periods):
            course = courses[i] if i < len(courses) else ""
            if not course or not course.strip():
                continue
            try:
                offset = timedelta(seconds=offset_seconds)
                # 提前提醒：上课侧整体提前 advance，结束时间不变
                start = self._to_dt(period['start'], now) + offset - advance
                end = self._to_dt(period['end'], now) + offset
            except Exception:
                continue

            # 已上课且未下课 → 上课中（以上课时刻为界）
            if start <= now <= end:
                remain_sec = max(0, int((end - now).total_seconds()))
                remain_min = max(1, (remain_sec + 59) // 60)
                duration_sec = max(1, int((end - start).total_seconds()))
                return {
                    'status': 'ongoing',
                    'course': course,
                    'period': period['name'],
                    'start': period['start'],
                    'end': period['end'],
                    'remain_sec': remain_sec,
                    'remain_min': remain_min,
                    'duration_sec': duration_sec,
                    'index': i,
                }

            # 未到上课时刻 → 下节（until 指向真正的上课时刻）
            if now < start:
                until_sec = max(0, int((start - now).total_seconds()))
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