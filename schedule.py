# -*- coding: utf-8 -*-
"""课表管理：多课表、临时调课、提前提醒、恢复默认

另含课表的导入 / 导出（JSON 完整备份、CSV 供 Excel 编辑），
格式解析与校验都在本模块完成，界面只负责选文件和提示。
"""
import os
import io
import re
import csv
import json
import tempfile
from datetime import datetime, timedelta

from storage import write_json as _write_json

SCHEDULE_FILE = "schedule.json"
DEFAULT_NAME = "默认课表"

# ---------- 导入 / 导出格式 ----------
FORMAT_ID = "classboard.schedule"
FORMAT_VERSION = 1
DAY_KEYS = [str(i) for i in range(7)]
CSV_HEADERS = ["节次", "开始", "结束",
               "周一", "周二", "周三", "周四", "周五", "周六", "周日"]
# 完整备份包含的附加设置
EXTRA_KEYS = ("holidays", "makeup_days", "weekend",
              "advance_minutes", "time_offset_seconds", "temp_adjust")

_CN_DAY_INDEX = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5,
                 "日": 6, "天": 6}
_EN_DAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4,
                 "sat": 5, "sun": 6}
_HHMM_RE = re.compile(r'^([01]?\d|2[0-3]):([0-5]\d)$')

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


# ================= 导入 / 导出：格式与校验 =================
def valid_hhmm(t):
    """时间格式校验：HH:MM（00:00 ~ 23:59）。"""
    m = _HHMM_RE.match(str(t or '').strip())
    return bool(m)


def _day_key(k):
    """把各种写法的星期转成项目内部键（'0'=周一 … '6'=周日）。"""
    s = str(k or '').strip()
    if not s:
        return None
    if s.isdigit():
        n = int(s)
        if 0 <= n <= 6:
            return str(n)
        if n == 7:
            return '6'
        return None
    low = s.lower()
    if low in _EN_DAY_INDEX:
        return str(_EN_DAY_INDEX[low])
    for pref in ("周", "星期", "礼拜"):
        if s.startswith(pref) and len(s) > len(pref):
            ch = s[len(pref)]
            if ch in _CN_DAY_INDEX:
                return str(_CN_DAY_INDEX[ch])
    if s in ("日", "天"):
        return '6'
    return None


def normalize_timetable(obj):
    """校验并规范化单个课表。

    返回 `(ok, 规范化后的课表, 错误信息)`；错误信息为空表示通过。
    """
    if not isinstance(obj, dict):
        return False, None, "这看着不像一张课表（应该是个对象）"

    raw_periods = obj.get('periods')
    if not isinstance(raw_periods, list) or not raw_periods:
        return False, None, "少了节次信息（periods）"
    if len(raw_periods) > 40:
        return False, None, f"节次太多了（{len(raw_periods)} 节，最多 40 节）"

    periods = []
    for i, p in enumerate(raw_periods):
        if not isinstance(p, dict):
            return False, None, f"第 {i + 1} 节的格式不太对"
        name = str(p.get('name') or '').strip() or f"第{i + 1}节"
        start = str(p.get('start') or '').strip()
        end = str(p.get('end') or '').strip()
        if not valid_hhmm(start):
            return False, None, f"第 {i + 1} 节的开始时间不太对：{start or '（空的）'}"
        if not valid_hhmm(end):
            return False, None, f"第 {i + 1} 节的结束时间不太对：{end or '（空的）'}"
        periods.append({'name': name[:20], 'start': start, 'end': end})

    raw_tt = obj.get('timetable')
    if raw_tt is None:
        raw_tt = {}
    if not isinstance(raw_tt, dict):
        return False, None, "课程内容（timetable）格式不太对"

    timetable = {}
    for k, v in raw_tt.items():
        key = _day_key(k)
        if key is None:
            continue
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, (list, tuple)):
            continue
        courses = [(str(x).strip() if x is not None else '') for x in v]
        while courses and courses[-1] == '':
            courses.pop()
        if key in timetable and len(timetable[key]) >= len(courses):
            continue
        timetable[key] = [c[:30] for c in courses]
    for k in DAY_KEYS:
        timetable.setdefault(k, [])
    return True, {'periods': periods, 'timetable': timetable}, ''


def timetable_course_count(tt):
    """课表里非空课程的数量。"""
    try:
        return sum(1 for v in (tt or {}).get('timetable', {}).values()
                   for c in v if str(c).strip())
    except Exception:
        return 0


def timetable_to_csv(periods, timetable):
    """单张课表 -> CSV 文本（含表头，Excel 可直接打开编辑）。"""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator='\r\n')
    writer.writerow(CSV_HEADERS)
    for i, p in enumerate(periods or []):
        row = [str(p.get('name') or f"第{i + 1}节"),
               str(p.get('start') or ''), str(p.get('end') or '')]
        for d in DAY_KEYS:
            day = (timetable or {}).get(d) or []
            row.append(day[i] if i < len(day) else '')
        writer.writerow(row)
    return out.getvalue()


def csv_to_timetable(text):
    """CSV 文本 -> `(periods, timetable, warnings)`。

    兼容：带或不带表头、时间列缺失（回退到默认作息）、Excel 存 GBK / 带 BOM。
    """
    raw = (text or '').lstrip('\ufeff')
    rows = [r for r in csv.reader(io.StringIO(raw)) if any(str(c).strip() for c in r)]
    if not rows:
        raise ValueError("CSV 里啥都没有")

    warnings = []
    header = [str(c).strip().lower() for c in rows[0]]
    has_header = bool(header) and (
        header[0] in ("节次", "节", "序号", "period", "no", "no.", "#")
        or (len(header) > 1 and header[1] in ("开始", "开始时间", "start")))
    if has_header:
        rows = rows[1:]
    if not rows:
        raise ValueError("CSV 里一节课都没有")

    periods, timetable = [], {k: [] for k in DAY_KEYS}
    for i, r in enumerate(rows):
        cells = [str(c).strip() for c in r]
        while len(cells) < 10:
            cells.append('')
        name = cells[0] or f"第{i + 1}节"
        start, end = cells[1], cells[2]
        if not valid_hhmm(start) or not valid_hhmm(end):
            if i < len(DEFAULT_PERIODS):
                start = start if valid_hhmm(start) else DEFAULT_PERIODS[i]['start']
                end = end if valid_hhmm(end) else DEFAULT_PERIODS[i]['end']
                warnings.append(f"第 {i + 1} 节时间缺了或格式不对，先用默认作息 {start}-{end}")
            else:
                start, end = "08:00", "08:45"
                warnings.append(f"第 {i + 1} 节没写时间，先填上 08:00-08:45")
        periods.append({'name': name[:20], 'start': start, 'end': end})
        for d, key in enumerate(DAY_KEYS):
            timetable[key].append(cells[3 + d][:30])
    for key in DAY_KEYS:
        while timetable[key] and timetable[key][-1] == '':
            timetable[key].pop()
    return periods, timetable, warnings


def detect_format(text):
    """按内容猜格式：'json' 或 'csv'。"""
    s = (text or '').lstrip('\ufeff').lstrip()
    if s.startswith(('{', '[')):
        return 'json'
    return 'csv'


def read_text_file(path):
    """读文本文件（兼容 UTF-8 BOM / GBK 的 Excel 导出）。"""
    with open(path, 'rb') as f:
        raw = f.read()
    for enc in ('utf-8-sig', 'utf-8', 'gbk'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'replace')


def _atomic_write_text(path, text, encoding='utf-8-sig'):
    """文本原子写：先写临时文件再替换，避免中断留下半个文件。"""
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding=encoding, newline='') as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise


def _clean_extras(raw):
    """从导入数据里挑出附加设置（假期 / 调休 / 周末 / 提前提醒等）。"""
    extras, warnings = {}, []
    if not isinstance(raw, dict):
        return extras, warnings

    holidays = raw.get('holidays')
    if isinstance(holidays, list):
        good = []
        for h in holidays:
            if isinstance(h, dict) and h.get('start') and h.get('end'):
                good.append({'start': str(h['start']), 'end': str(h['end']),
                             'name': str(h.get('name') or '')})
        extras['holidays'] = good
        if len(good) != len(holidays):
            warnings.append(f"有 {len(holidays) - len(good)} 条假期记录格式不对，跳过了")

    makeup = raw.get('makeup_days')
    if isinstance(makeup, list):
        good = []
        for m in makeup:
            if isinstance(m, dict) and m.get('date'):
                good.append({'date': str(m['date']),
                             'as_weekday': int(m.get('as_weekday') or 0) % 7})
        extras['makeup_days'] = good
        if len(good) != len(makeup):
            warnings.append(f"有 {len(makeup) - len(good)} 条调休记录格式不对，跳过了")

    weekend = raw.get('weekend')
    if isinstance(weekend, dict):
        extras['weekend'] = {
            'morning_split': str(weekend.get('morning_split') or '12:00'),
            'afternoon_periods': [dict(p) for p in
                                  (weekend.get('afternoon_periods') or [])
                                  if isinstance(p, dict)],
            'courses': [str(c) for c in (weekend.get('courses') or [])],
        }

    for key in ('advance_minutes', 'time_offset_seconds'):
        if key in raw:
            try:
                extras[key] = int(raw[key])
            except (TypeError, ValueError):
                warnings.append(f"有个无效的 {key}，跳过了")
            else:
                if key == 'advance_minutes':
                    extras[key] = max(0, min(60, extras[key]))

    ta = raw.get('temp_adjust')
    if isinstance(ta, dict):
        extras['temp_adjust'] = {
            'date': str(ta.get('date') or ''),
            'courses': [str(c) for c in (ta.get('courses') or [])],
        }
    return extras, warnings


def parse_document(text, filename=""):
    """把文件内容解析成统一结构（纯函数，便于测试）。

    返回 `{'format', 'kind', 'timetables', 'extras', 'warnings'}`，
    其中 `kind` 为 `'full'`（含附加设置）或 `'timetables'`。
    """
    if not str(text or '').strip():
        raise ValueError("文件是空的")
    fmt = detect_format(text)
    stem = os.path.splitext(os.path.basename(filename or ""))[0]

    if fmt == 'csv':
        periods, timetable, warnings = csv_to_timetable(text)
        name = stem or "从文件导入的课表"
        return {'format': 'csv', 'kind': 'timetables',
                'timetables': {name: {'periods': periods, 'timetable': timetable}},
                'extras': {}, 'warnings': warnings}

    try:
        raw = json.loads(text.lstrip('\ufeff'))
    except Exception as e:
        raise ValueError(f"这不是合法的 JSON：{e}")

    warnings = []
    timetables, extras = {}, {}
    active = ''

    if isinstance(raw, list):
        # 宽容：允许直接给 [课表对象, ...]
        for i, item in enumerate(raw):
            ok, norm, err = normalize_timetable(item)
            if not ok:
                warnings.append(f"第 {i + 1} 项跳过了：{err}")
                continue
            nm = str((item or {}).get('name') or '').strip() \
                or f"{stem or '从文件导入的课表'}{i + 1 if len(raw) > 1 else ''}"
            timetables[nm] = norm
    elif isinstance(raw, dict) and isinstance(raw.get('timetables'), dict):
        for nm, obj in raw['timetables'].items():
            ok, norm, err = normalize_timetable(obj)
            if not ok:
                warnings.append(f"课表「{nm}」跳过了：{err}")
                continue
            timetables[str(nm)] = norm
        extras, w2 = _clean_extras(raw)
        warnings.extend(w2)
        active = str(raw.get('active') or '')
    elif isinstance(raw, dict) and ('periods' in raw or 'timetable' in raw):
        ok, norm, err = normalize_timetable(raw)
        if not ok:
            raise ValueError(f"课表数据有点问题：{err}")
        nm = str(raw.get('name') or '').strip() or (stem or "从文件导入的课表")
        timetables[nm] = norm
    elif isinstance(raw, dict):
        raise ValueError("没在文件里找到课表数据（少了 timetables / periods）")
    else:
        raise ValueError("认不出这个文件的结构")

    if not timetables:
        raise ValueError("文件里没有能用的课表" + (f"（{warnings[0]}）" if warnings else ""))

    kind = 'full' if extras else 'timetables'
    return {'format': 'json', 'kind': kind, 'timetables': timetables,
            'extras': extras, 'warnings': warnings, 'active': active}


def unique_name(existing, name):
    """给课表取一个不冲突的名字：`X` -> `X (导入)` -> `X (导入2)`。"""
    if name not in existing:
        return name
    first = f"{name} (导入)"
    if first not in existing:
        return first
    i = 2
    while f"{name} (导入{i})" in existing:
        i += 1
    return f"{name} (导入{i})"


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
        _write_json(self.path, self.data)

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

    # ---------- 导出 ----------
    def export_payload(self, names=None, include_extras=False):
        """构造可移植的导出数据。

        - `names=None`：单表导出时取当前课表；完整备份（include_extras=True）
          时导出**全部课表**（否则备份会悄悄丢掉非当前课表）。
        - 给列表则导出这些课表。
        - `include_extras=True` 时附带假期 / 调休 / 周末作息 / 提前提醒等设置
          （即\"完整备份\"）。
        """
        if names is None:
            names = (list(self.data['timetables']) if include_extras
                     else [self.data['active']])
        else:
            names = [str(n) for n in names]
        picked = {}
        for n in names:
            tt = self.data['timetables'].get(n)
            if not tt:
                continue
            ok, norm, err = normalize_timetable(tt)
            if ok:
                picked[n] = norm
        if not picked:
            raise ValueError("没有可导出的课表")

        payload = {
            "format": FORMAT_ID,
            "version": FORMAT_VERSION,
            "app": "Class Daily Land",
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "kind": "full" if include_extras else "timetables",
            "timetables": picked,
        }
        if include_extras:
            payload['timetables'] = {
                n: self.data['timetables'][n] for n in picked}
            payload['active'] = self.data['active']
            for key in EXTRA_KEYS:
                if key in self.data:
                    payload[key] = self.data[key]
        else:
            payload['active'] = names[0] if len(names) == 1 else next(iter(picked))
        return payload

    def export_text(self, fmt='json', names=None, include_extras=False):
        """导出为文本：`fmt` 为 'json' 或 'csv'。"""
        fmt = (fmt or 'json').strip().lower()
        payload = self.export_payload(names=names, include_extras=include_extras)
        if fmt == 'csv':
            if len(payload['timetables']) != 1:
                raise ValueError("CSV 一次只能导出 1 张课表，"
                                 "如需多张请用 JSON（或先选中要导出的课表）")
            tt = next(iter(payload['timetables'].values()))
            return timetable_to_csv(tt['periods'], tt['timetable'])
        if fmt != 'json':
            raise ValueError(f"不支持的导出格式：{fmt}")
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def write_export(self, path, fmt='json', names=None,
                     include_extras=False):
        """导出到文件（原子写）。返回写入的绝对路径。"""
        fmt = (fmt or 'json').strip().lower()
        text = self.export_text(fmt=fmt, names=names,
                                include_extras=include_extras)
        if fmt == 'csv':
            # BOM + CRLF：Excel 双击打开不乱码
            _atomic_write_text(path, text, encoding='utf-8-sig')
        else:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
        return os.path.abspath(path)

    def export_filename(self, fmt='json', names=None, include_extras=False):
        """给导出文件起个默认名。"""
        stamp = datetime.now().strftime("%Y%m%d")
        if (fmt or 'json').lower() == 'csv':
            name = (names[0] if names else self.data['active'])
            safe = re.sub(r'[\\/:*?"<>|]', '_', str(name)).strip() or "课表"
            return f"{safe}-{stamp}.csv"
        if include_extras:
            return f"ClassDailyLand课表备份-{stamp}.json"
        name = (names[0] if names else self.data['active'])
        safe = re.sub(r'[\\/:*?"<>|]', '_', str(name)).strip() or "课表"
        return f"{safe}-{stamp}.json"

    # ---------- 导入 ----------
    def preview_import(self, text, filename=""):
        """解析但不写入，返回给用户看的摘要。"""
        doc = parse_document(text, filename)
        names = []
        for nm, tt in doc['timetables'].items():
            names.append({
                'name': nm,
                'periods': len(tt.get('periods', [])),
                'courses': timetable_course_count(tt),
                'exists': nm in self.data['timetables'],
            })
        ex = doc['extras']
        return {
            'format': doc['format'],
            'kind': doc['kind'],
            'timetables': names,
            'warnings': list(doc['warnings']),
            'extras': {
                'holidays': len(ex.get('holidays') or []),
                'makeup_days': len(ex.get('makeup_days') or []),
                'weekend': bool(ex.get('weekend')),
                'advance_minutes': ex.get('advance_minutes'),
                'time_offset_seconds': ex.get('time_offset_seconds'),
            },
            'can_replace_full': doc['kind'] == 'full',
        }

    def import_text(self, text, mode='merge', filename=""):
        """导入课表文本。

        - `mode='merge'`：全部追加为新课表，同名自动改成 `xxx (导入)`；
        - `mode='replace'`：完整备份 → 整体恢复（课表 + 假期 / 周末等设置）；
          单表文件 → 只替换同名课表（没有同名则新增）。
        """
        doc = parse_document(text, filename)
        mode = 'replace' if str(mode).lower() == 'replace' else 'merge'
        added, replaced, renamed = [], [], []

        if mode == 'replace' and doc['kind'] == 'full' and doc['extras']:
            old_names = set(self.data['timetables'])
            self.data['timetables'] = {nm: tt for nm, tt in
                                       doc['timetables'].items()}
            self.data.update(doc['extras'])
            active = str(doc.get('active') or '')
            self.data['active'] = (active if active in self.data['timetables']
                                   else next(iter(self.data['timetables'])))
            replaced = list(self.data['timetables'])
            added = [n for n in replaced if n not in old_names]
            self.save()
            return {'mode': 'replace/full', 'added': added,
                    'replaced': replaced,
                    'renamed': renamed, 'removed': sorted(old_names - set(replaced)),
                    'active': self.data['active'],
                    'warnings': list(doc['warnings'])}

        for nm, tt in doc['timetables'].items():
            if mode == 'replace' and nm in self.data['timetables']:
                self.data['timetables'][nm] = tt
                replaced.append(nm)
                continue
            target = nm
            if target in self.data['timetables']:
                target = unique_name(self.data['timetables'], nm)
                renamed.append([nm, target])
            self.data['timetables'][target] = tt
            added.append(target)

        if not added and not replaced:
            raise ValueError("没有可以导入的课表")
        # 导入单表时若当前没有课表，顺带设为当前
        if self.data['active'] not in self.data['timetables']:
            self.data['active'] = next(iter(self.data['timetables']))
        self.save()
        return {'mode': f'{mode}/timetables', 'added': added,
                'replaced': replaced, 'renamed': renamed, 'removed': [],
                'active': self.data['active'],
                'warnings': list(doc['warnings'])}

    def import_file(self, path, mode='merge'):
        """从文件导入（自动识别 JSON / CSV，兼容 UTF-8 / GBK）。"""
        return self.import_text(read_text_file(path), mode=mode,
                                filename=path)

    def preview_file(self, path):
        return self.preview_import(read_text_file(path), filename=path)

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
                raw_start = self._to_dt(period['start'], now)
                raw_end = self._to_dt(period['end'], now)
                if raw_end <= raw_start:
                    raw_end += timedelta(days=1)   # 跨午夜课程
                # 提前提醒：上课侧整体提前 advance，结束时间不变
                start = raw_start + offset - advance
                end = raw_end + offset
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