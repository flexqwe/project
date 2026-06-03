import json
import re
from datetime import datetime, timedelta, time as dt_time

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .achievements import check_and_unlock_achievements, get_achievements_data
from .ai_recommendations import build_ai_recommendation
from .models import Note


ALLOWED_PRIORITIES = {value for value, _ in Note.PRIORITY_CHOICES}
ALLOWED_CATEGORIES = {value for value, _ in Note.CATEGORY_CHOICES}
ALLOWED_REPEAT_TYPES = {value for value, _ in Note.REPEAT_TYPE_CHOICES}
ALLOWED_SNOOZE_OPTIONS = {value for value, _ in Note.SNOOZE_CHOICES}
ALLOWED_STATUS_FILTERS = {'pending', 'sent', 'completed', 'overdue'}
ALLOWED_COMPLETED_FILTERS = {'true', 'false', '1', '0', 'yes', 'no'}

STATUS_CHOICES = [
    ('pending', '⏳ Kutilmoqda'),
    ('sent', '📨 Yuborilgan'),
    ('overdue', '⚠️ Kechikkan'),
    ('completed', '✅ Bajarilgan'),
]

COMPLETED_CHOICES = [
    ('false', 'Bajarilmagan'),
    ('true', 'Bajarilgan'),
]

UZ_MONTHS = {
    'yanvar': 1, 'fevral': 2, 'mart': 3, 'aprel': 4, 'may': 5,
    'iyun': 6, 'iyul': 7, 'avgust': 8, 'sentabr': 9, 'sentyabr': 9,
    'oktabr': 10, 'oktyabr': 10, 'noyabr': 11, 'dekabr': 12,
}

UZ_WEEKDAYS = {
    'dushanba': 0,
    'seshanba': 1,
    'chorshanba': 2,
    'payshanba': 3,
    'juma': 4,
    'shanba': 5,
    'yakshanba': 6,
}

VOICE_FILLER_WORDS = [
    'menga', 'meni', 'iltimos', 'iltimoski', 'reminder', 'remaynder',
    'eslatma', 'eslatmani', 'eslat', 'eslatgin', 'eslating', 'qilib',
    'yarat', 'yaratib', 'qo‘y', 'qoy', 'qo\'y', 'kerak', 'kerek',
]


def _today_local_date():
    return timezone.localtime(timezone.now()).date()


def _time_to_input(value):
    return value.strftime('%H:%M') if value else ''


def _date_to_input(value):
    return value.strftime('%Y-%m-%d') if value else ''


def get_today_bounds():
    """Bugungi kunning lokal boshlanishi va tugash vaqtini qaytaradi."""
    local_now = timezone.localtime(timezone.now())
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    return today_start, tomorrow_start


def infer_category_from_text(text):
    t = (text or '').lower()
    if any(word in t for word in ['dars', 'matematika', 'kitob', 'o‘qish', "o'qish", 'imtihon', 'uy vazifa', 'maktab', 'universitet']):
        return 'oqish'
    if any(word in t for word in ['ish', 'ofis', 'mijoz', 'meeting', 'uchrashuv', 'loyiha', 'hisobot']):
        return 'ish'
    if any(word in t for word in ['sport', 'mashq', 'zal', 'yugur', 'futbol', 'trenirovka']):
        return 'sport'
    if any(word in t for word in ['oila', 'oilaviy', 'ona', 'ota', 'aka', 'uka', 'singil']):
        return 'oilaviy'
    if any(word in t for word in ['muhim', 'shoshilinch', 'tez', 'zarur']):
        return 'muhim'
    return 'shaxsiy'


def infer_priority_from_text(text):
    t = (text or '').lower()
    if any(word in t for word in ['shoshilinch', 'tez', 'zudlik', 'urgent']):
        return 'shoshilinch'
    if any(word in t for word in ['muhim', 'zarur', 'important']):
        return 'muhim'
    if any(word in t for word in ['keyinroq', 'bo‘sh vaqtda', "bo'sh vaqtda"]):
        return 'keyinroq'
    return 'oddiy'


def extract_voice_date(text):
    """O'zbekcha natural textdan sanani topishga harakat qiladi."""
    raw = text or ''
    t = raw.lower().replace('’', "'").replace('ʻ', "'").replace('`', "'")
    today = _today_local_date()

    if re.search(r'\bbugun\b', t):
        return today, 'bugun'
    if re.search(r'\bertaga\b', t):
        return today + timedelta(days=1), 'ertaga'
    if re.search(r'\b(indin|indinga|ertadan keyin)\b', t):
        return today + timedelta(days=2), 'indin'

    iso_match = re.search(r'\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b', t)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        try:
            return datetime(year, month, day).date(), iso_match.group(0)
        except ValueError:
            pass

    dot_match = re.search(r'\b(\d{1,2})[-/.](\d{1,2})(?:[-/.](20\d{2}))?\b', t)
    if dot_match:
        day = int(dot_match.group(1))
        month = int(dot_match.group(2))
        year = int(dot_match.group(3) or today.year)
        try:
            parsed = datetime(year, month, day).date()
            if not dot_match.group(3) and parsed < today:
                parsed = datetime(year + 1, month, day).date()
            return parsed, dot_match.group(0)
        except ValueError:
            pass

    for month_name, month_number in UZ_MONTHS.items():
        month_match = re.search(rf'\b(\d{{1,2}})\s*[- ]?\s*{month_name}\b', t)
        if month_match:
            day = int(month_match.group(1))
            year = today.year
            try:
                parsed = datetime(year, month_number, day).date()
                if parsed < today:
                    parsed = datetime(year + 1, month_number, day).date()
                return parsed, month_match.group(0)
            except ValueError:
                pass

    for weekday_name, weekday_number in UZ_WEEKDAYS.items():
        if re.search(rf'\b{weekday_name}\b', t):
            days_ahead = (weekday_number - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead), weekday_name

    return None, ''


def extract_voice_time(text):
    """O'zbekcha natural textdan vaqtni topishga harakat qiladi."""
    raw = text or ''
    t = raw.lower().replace('’', "'").replace('ʻ', "'").replace('`', "'")

    named_times = {
        'ertalab': dt_time(hour=9, minute=0),
        'tushda': dt_time(hour=12, minute=0),
        'kechqurun': dt_time(hour=18, minute=0),
        'kechki': dt_time(hour=18, minute=0),
        'tunda': dt_time(hour=21, minute=0),
    }

    soat_match = re.search(r'\bsoat\s*(\d{1,2})(?:\s*[:.]\s*(\d{2}))?(?:\s*(?:da|ga))?\b', t)
    if soat_match:
        hour = int(soat_match.group(1))
        minute = int(soat_match.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return dt_time(hour=hour, minute=minute), soat_match.group(0)

    colon_match = re.search(r'\b([01]?\d|2[0-3])\s*[:.]\s*([0-5]\d)\b', t)
    if colon_match:
        hour = int(colon_match.group(1))
        minute = int(colon_match.group(2))
        return dt_time(hour=hour, minute=minute), colon_match.group(0)

    da_match = re.search(r'\b([01]?\d|2[0-3])\s*(?:da|ga)\b', t)
    if da_match:
        hour = int(da_match.group(1))
        return dt_time(hour=hour, minute=0), da_match.group(0)

    for name, parsed_time in named_times.items():
        if re.search(rf'\b{name}\b', t):
            return parsed_time, name

    return None, ''


def clean_voice_title(text, date_token='', time_token=''):
    title = (text or '').strip()
    title = re.sub(r'[.!?]+$', '', title)

    for token in [date_token, time_token]:
        if token:
            title = re.sub(re.escape(token), ' ', title, flags=re.IGNORECASE)

    title = re.sub(r'\bsoat\s*\d{1,2}(?:\s*[:.]\s*\d{2})?\s*(?:da|ga)?\b', ' ', title, flags=re.IGNORECASE)
    title = re.sub(r'\b\d{1,2}\s*(?:da|ga)\b', ' ', title, flags=re.IGNORECASE)
    title = re.sub(r'\b(bugun|ertaga|indin|indinga|ertadan keyin)\b', ' ', title, flags=re.IGNORECASE)
    title = re.sub(r'\b(dushanba|seshanba|chorshanba|payshanba|juma|shanba|yakshanba)\b', ' ', title, flags=re.IGNORECASE)

    for word in VOICE_FILLER_WORDS:
        title = re.sub(rf'\b{re.escape(word)}\b', ' ', title, flags=re.IGNORECASE)

    title = re.sub(r'\s+', ' ', title).strip(' ,.-–—')
    return title[:1].upper() + title[1:] if title else ''


def parse_voice_reminder_text(text):
    """
    Browser speechdan kelgan matndan title, date va time ajratadi.
    Sana/vaqt topilmasa frontend qo'lda tanlashni so'raydi.
    """
    normalized_text = (text or '').strip()
    parsed_date, date_token = extract_voice_date(normalized_text)
    parsed_time, time_token = extract_voice_time(normalized_text)
    title = clean_voice_title(normalized_text, date_token, time_token)

    missing = []
    if not title:
        missing.append('title')
    if not parsed_date:
        missing.append('date')
    if not parsed_time:
        missing.append('time')

    return {
        'raw_text': normalized_text,
        'title': title,
        'date': _date_to_input(parsed_date) if parsed_date else '',
        'time': _time_to_input(parsed_time) if parsed_time else '',
        'priority': infer_priority_from_text(normalized_text),
        'category': infer_category_from_text(normalized_text),
        'missing': missing,
        'can_create': not missing,
        'message': 'Ovozli eslatma tayyor.' if not missing else 'Sana yoki vaqt aniq topilmadi. Iltimos, qo‘lda tanlang.',
    }


def parse_remind_at(date, time):
    remind_at_str = f"{date} {time}"

    formats = [
        "%d.%m.%Y %H:%M",    # 11.05.2026 16:00
        "%Y-%m-%d %H:%M",    # 2026-05-11 16:00
        "%Y-%m-%dT%H:%M",    # 2026-05-11T16:00
    ]

    for fmt in formats:
        try:
            remind_at = datetime.strptime(remind_at_str, fmt)
            if timezone.is_naive(remind_at):
                remind_at = timezone.make_aware(remind_at)
            return remind_at
        except ValueError:
            continue

    return None


def parse_positive_int(value, default=1):
    try:
        number = int(value)
        return number if number > 0 else default
    except (TypeError, ValueError):
        return default


def normalize_snooze_option(option):
    option = option or '5m'
    return option if option in ALLOWED_SNOOZE_OPTIONS else '5m'


def normalize_category(category):
    category = category or 'shaxsiy'
    return category if category in ALLOWED_CATEGORIES else 'shaxsiy'


def parse_filter_date(date_value):
    """Filter date inputidan YYYY-MM-DD sanani olib, lokal kun oralig'ini qaytaradi."""
    if not date_value:
        return None, None

    try:
        parsed_date = datetime.strptime(date_value, "%Y-%m-%d").date()
    except ValueError:
        return None, None

    start = datetime.combine(parsed_date, dt_time.min)
    end = datetime.combine(parsed_date + timedelta(days=1), dt_time.min)

    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    if timezone.is_naive(end):
        end = timezone.make_aware(end)

    return start, end


def normalize_filter_params(params):
    """GET query parameterlarni xavfsiz qilib bitta dictga yig'adi."""
    search = (params.get('search') or '').strip()
    status = (params.get('status') or '').strip()
    priority = (params.get('priority') or '').strip()
    category = (params.get('category') or '').strip()
    date_value = (params.get('date') or '').strip()
    completed = (params.get('completed') or '').strip().lower()

    return {
        'search': search,
        'status': status if status in ALLOWED_STATUS_FILTERS else '',
        'priority': priority if priority in ALLOWED_PRIORITIES else '',
        'category': category if category in ALLOWED_CATEGORIES else '',
        'date': date_value,
        'completed': completed if completed in ALLOWED_COMPLETED_FILTERS else '',
    }


def apply_note_filters(queryset, params):
    """
    Search va filterlarni bitta querysetga qo'llaydi.
    Backend API quyidagi query parameterlarni qabul qiladi:
    search, status, priority, category, date, completed.
    """
    filters = normalize_filter_params(params)
    now = timezone.now()

    if filters['search']:
        queryset = queryset.filter(text__icontains=filters['search'])

    if filters['priority']:
        queryset = queryset.filter(priority=filters['priority'])

    if filters['category']:
        queryset = queryset.filter(category=filters['category'])

    if filters['date']:
        date_start, date_end = parse_filter_date(filters['date'])
        if date_start and date_end:
            queryset = queryset.filter(remind_at__gte=date_start, remind_at__lt=date_end)

    if filters['completed']:
        completed_value = filters['completed'] in {'true', '1', 'yes'}
        queryset = queryset.filter(completed=completed_value)

    if filters['status'] == 'completed':
        queryset = queryset.filter(completed=True)
    elif filters['status'] == 'overdue':
        queryset = queryset.filter(completed=False, remind_at__lt=now)
    elif filters['status'] == 'sent':
        queryset = queryset.filter(completed=False, sent=True)
    elif filters['status'] == 'pending':
        queryset = queryset.filter(completed=False, sent=False, remind_at__gte=now)

    return queryset, filters


def get_notes_queryset(params=None, limit=80):
    queryset = Note.objects.all()
    filters = normalize_filter_params(params or {})

    if params:
        queryset, filters = apply_note_filters(queryset, params)

    # Kutilayotgan/yuborilgan reminderlar tepada, bajarilganlari pastroqda chiqadi.
    queryset = queryset.order_by('completed', 'remind_at', '-id')
    return queryset[:limit], filters


def build_dashboard_stats():
    """
    Dashboard statistikalarini real database ma'lumotlaridan hisoblaydi.
    Frontend ham, API ham bitta helperdan foydalanadi.
    """
    now = timezone.now()
    today_start, tomorrow_start = get_today_bounds()

    total_count = Note.objects.count()
    today_count = Note.objects.filter(
        remind_at__gte=today_start,
        remind_at__lt=tomorrow_start,
    ).count()
    completed_count = Note.objects.filter(completed=True).count()
    overdue_count = Note.objects.filter(
        completed=False,
        remind_at__lt=now,
    ).count()

    nearest_note = Note.objects.filter(
        completed=False,
        remind_at__gte=now,
    ).order_by('remind_at').first()

    nearest_data = None
    if nearest_note:
        nearest_local_time = timezone.localtime(nearest_note.remind_at)
        nearest_data = {
            'id': nearest_note.id,
            'title': nearest_note.text,
            'time': nearest_local_time.isoformat(),
            'time_display': nearest_local_time.strftime('%d.%m.%Y %H:%M'),
        }

    return {
        'today_count': today_count,
        'completed_count': completed_count,
        'pending_count': max(total_count - completed_count, 0),
        'overdue_count': overdue_count,
        'total_count': total_count,
        'nearest': nearest_data,
        'is_empty': total_count == 0,
    }


def build_index_context(extra=None, request=None):
    notes, active_filters = get_notes_queryset(request.GET if request else None)
    completed_count = Note.objects.filter(completed=True).count()
    context = {
        'notes': notes,
        'snooze_choices': Note.SNOOZE_CHOICES,
        'priority_choices': Note.PRIORITY_CHOICES,
        'category_choices': Note.CATEGORY_CHOICES,
        'repeat_type_choices': Note.REPEAT_TYPE_CHOICES,
        'status_choices': STATUS_CHOICES,
        'completed_choices': COMPLETED_CHOICES,
        'active_filters': active_filters,
        'filtered_count': len(notes),
        'pending_count': Note.objects.filter(completed=False).count(),
        'completed_count': completed_count,
        'dashboard_stats': build_dashboard_stats(),
        'ai_recommendation': build_ai_recommendation(),
    }
    if extra:
        context.update(extra)
    return context


def note_to_api_dict(note):
    remind_at = timezone.localtime(note.remind_at) if note.remind_at else None
    last_snoozed_at = timezone.localtime(note.last_snoozed_at) if note.last_snoozed_at else None
    completed_at = timezone.localtime(note.completed_at) if note.completed_at else None

    status_value = note.status_value
    status_class = status_value

    return {
        'id': note.id,
        'text': note.text,
        'description': note.description,
        'description_display': note.description or "Izoh qo'shilmagan",
        'remind_at': remind_at.isoformat() if remind_at else None,
        'remind_at_display': remind_at.strftime('%d.%m.%Y %H:%M') if remind_at else None,
        'sent': note.sent,
        'completed': note.completed,
        'completedAt': completed_at.isoformat() if completed_at else None,
        'completedAtDisplay': completed_at.strftime('%d.%m.%Y %H:%M') if completed_at else None,
        'status': note.status_label,
        'status_value': status_value,
        'status_class': status_class,
        'priority': note.priority,
        'priority_display': note.get_priority_display(),
        'category': note.category,
        'category_display': note.get_category_display(),
        'category_icon': note.category_icon,
        'category_class': note.category_class,
        'category_color': note.category_color,
        'edit_date': remind_at.strftime('%Y-%m-%d') if remind_at else '',
        'edit_time': remind_at.strftime('%H:%M') if remind_at else '',
        'repeat_type': note.repeat_type,
        'repeat_interval': note.repeat_interval,
        'repeat_label': note.get_repeat_label(),
        'snoozedCount': note.snoozed_count,
        'lastSnoozedAt': last_snoozed_at.isoformat() if last_snoozed_at else None,
        'lastSnoozedAtDisplay': last_snoozed_at.strftime('%d.%m.%Y %H:%M') if last_snoozed_at else None,
    }



def build_today_plan_data():
    """
    Bugungi reminderlarni status bo'yicha guruhlaydi va progress hisoblaydi.
    Progress: bajarilgan bugungi vazifalar / umumiy bugungi vazifalar * 100.
    """
    now = timezone.now()
    today_start, tomorrow_start = get_today_bounds()

    today_notes = list(
        Note.objects.filter(
            remind_at__gte=today_start,
            remind_at__lt=tomorrow_start,
        ).order_by('completed', 'remind_at', '-id')
    )

    pending_notes = []
    completed_notes = []
    overdue_notes = []

    for note in today_notes:
        if note.completed:
            completed_notes.append(note)
        elif note.remind_at < now:
            overdue_notes.append(note)
        else:
            pending_notes.append(note)

    total_count = len(today_notes)
    completed_count = len(completed_notes)
    progress_percent = round((completed_count / total_count) * 100) if total_count else 0

    return {
        'today_date': timezone.localtime(now).strftime('%d.%m.%Y'),
        'today_date_iso': timezone.localtime(now).strftime('%Y-%m-%d'),
        'total_count': total_count,
        'completed_count': completed_count,
        'pending_count': len(pending_notes),
        'overdue_count': len(overdue_notes),
        'progress_percent': progress_percent,
        'progress_text': f'{total_count} ta vazifadan {completed_count} tasi bajarildi — {progress_percent}%',
        'is_empty': total_count == 0,
        'groups': {
            'pending': pending_notes,
            'overdue': overdue_notes,
            'completed': completed_notes,
        },
        'groups_api': {
            'pending': [note_to_api_dict(note) for note in pending_notes],
            'overdue': [note_to_api_dict(note) for note in overdue_notes],
            'completed': [note_to_api_dict(note) for note in completed_notes],
        },
    }


def today_plan(request):
    """Alohida Bugun rejasi sahifasi."""
    return render(request, 'today_plan.html', {
        'today_plan': build_today_plan_data(),
        'snooze_choices': Note.SNOOZE_CHOICES,
    })


def achievements_page(request):
    """Badge/yutuqlar sahifasi."""
    return render(request, 'achievements.html', {
        'achievements_data': get_achievements_data(),
    })


@require_GET
def api_achievements(request):
    """Achievement kartochkalari uchun JSON API."""
    return JsonResponse({
        'ok': True,
        'achievements_data': get_achievements_data(),
    })


@require_GET
def api_today_plan(request):
    """Bugun rejasi sahifasi uchun refreshsiz yangilanish API endpointi."""
    plan = build_today_plan_data()
    return JsonResponse({
        'ok': True,
        'today_plan': {
            'today_date': plan['today_date'],
            'today_date_iso': plan['today_date_iso'],
            'total_count': plan['total_count'],
            'completed_count': plan['completed_count'],
            'pending_count': plan['pending_count'],
            'overdue_count': plan['overdue_count'],
            'progress_percent': plan['progress_percent'],
            'progress_text': plan['progress_text'],
            'is_empty': plan['is_empty'],
            'groups': plan['groups_api'],
        },
    })


def index(request):
    if request.method == "POST":
        text = request.POST.get("text", "").strip()
        description = request.POST.get("description", "").strip()
        date = request.POST.get("date")
        time = request.POST.get("time")

        priority = request.POST.get("priority") or "oddiy"
        if priority not in ALLOWED_PRIORITIES:
            priority = "oddiy"

        category = normalize_category(request.POST.get("category"))

        repeat_type = request.POST.get("repeat_type") or "none"
        if repeat_type not in ALLOWED_REPEAT_TYPES:
            repeat_type = "none"

        repeat_interval = parse_positive_int(request.POST.get("repeat_interval"), 1)
        if repeat_type not in {"custom_days", "custom_weeks"}:
            repeat_interval = 1

        if text and date and time:
            remind_at = parse_remind_at(date, time)

            if remind_at is None:
                return render(request, "index.html", build_index_context({
                    "error": "Неверный формат даты. Пример: 11.05.2026 16:00"
                }, request=request))

            Note.objects.create(
                text=text,
                description=description,
                remind_at=remind_at,
                next_reminder_date=remind_at,
                priority=priority,
                category=category,
                repeat_type=repeat_type,
                repeat_interval=repeat_interval,
                sent=False,
                completed=False,
                completed_at=None,
            )
            messages.success(request, "Eslatma saqlandi va rejalashtirildi.")

        return redirect("home")

    return render(request, "index.html", build_index_context(request=request))


def get_note_payload_value(request, key, default=None):
    """FormData yoki JSON body ichidan bitta qiymatni xavfsiz oladi."""
    if key in request.POST:
        return request.POST.get(key)

    if not hasattr(request, '_cached_json_payload'):
        try:
            request._cached_json_payload = json.loads(request.body.decode('utf-8') or '{}')
        except (json.JSONDecodeError, UnicodeDecodeError):
            request._cached_json_payload = {}

    return request._cached_json_payload.get(key, default)



def create_note_from_payload(payload):
    """Form yoki JSON payload asosida yangi reminder yaratadi."""
    text = (payload.get('text') or payload.get('title') or '').strip()
    description = (payload.get('description') or '').strip()
    date = payload.get('date') or ''
    time = payload.get('time') or ''

    if not text:
        return None, 'Sarlavha topilmadi. Iltimos, title kiriting.'
    if not date or not time:
        return None, 'Sana yoki vaqt topilmadi. Iltimos, qo‘lda tanlang.'

    remind_at = parse_remind_at(date, time)
    if remind_at is None:
        return None, 'Sana yoki vaqt formati noto‘g‘ri. Masalan: 2026-05-22 09:00'

    priority = payload.get('priority') or 'oddiy'
    if priority not in ALLOWED_PRIORITIES:
        priority = 'oddiy'

    category = normalize_category(payload.get('category'))

    repeat_type = payload.get('repeat_type') or 'none'
    if repeat_type not in ALLOWED_REPEAT_TYPES:
        repeat_type = 'none'

    repeat_interval = parse_positive_int(payload.get('repeat_interval'), 1)
    if repeat_type not in {'custom_days', 'custom_weeks'}:
        repeat_interval = 1

    note = Note.objects.create(
        text=text,
        description=description,
        remind_at=remind_at,
        next_reminder_date=remind_at,
        priority=priority,
        category=category,
        repeat_type=repeat_type,
        repeat_interval=repeat_interval,
        sent=False,
        completed=False,
        completed_at=None,
    )
    return note, 'Eslatma saqlandi va rejalashtirildi.'


def get_request_payload(request):
    """API uchun FormData yoki JSON body'ni bitta dict qilib beradi."""
    if request.POST:
        return request.POST.dict()
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def update_note_from_request(note, request):
    """Edit API uchun note maydonlarini yangilaydi."""
    text = (get_note_payload_value(request, 'text', note.text) or '').strip()
    description = (get_note_payload_value(request, 'description', note.description or '') or '').strip()
    date = get_note_payload_value(request, 'date', '')
    time = get_note_payload_value(request, 'time', '')
    priority = get_note_payload_value(request, 'priority', note.priority) or note.priority
    category = normalize_category(get_note_payload_value(request, 'category', note.category))
    repeat_type = get_note_payload_value(request, 'repeat_type', note.repeat_type) or note.repeat_type
    repeat_interval = parse_positive_int(get_note_payload_value(request, 'repeat_interval', note.repeat_interval), 1)

    if not text:
        return False, 'Sarlavha bo‘sh bo‘lmasligi kerak.'

    if priority not in ALLOWED_PRIORITIES:
        priority = 'oddiy'

    if repeat_type not in ALLOWED_REPEAT_TYPES:
        repeat_type = 'none'

    if repeat_type not in {'custom_days', 'custom_weeks'}:
        repeat_interval = 1

    remind_at = note.remind_at
    if date and time:
        remind_at = parse_remind_at(date, time)
        if remind_at is None:
            return False, 'Sana yoki vaqt formati noto‘g‘ri.'

    note.text = text
    note.description = description
    note.remind_at = remind_at
    note.next_reminder_date = remind_at
    note.priority = priority
    note.category = category
    note.repeat_type = repeat_type
    note.repeat_interval = repeat_interval

    # Edit qilinganda, agar reminder hali bajarilmagan bo‘lsa, qayta kutilmoqda holatiga qaytariladi.
    if not note.completed:
        note.sent = False

    note.save(update_fields=[
        'text',
        'description',
        'remind_at',
        'next_reminder_date',
        'priority',
        'category',
        'repeat_type',
        'repeat_interval',
        'sent',
    ])
    return True, 'Eslatma yangilandi.'


@require_POST
def snooze_note(request, note_id):
    note = get_object_or_404(Note, id=note_id)
    option = normalize_snooze_option(request.POST.get("snooze_option"))
    new_time = note.snooze(option)

    messages.success(
        request,
        f"'{note.text}' eslatmasi {timezone.localtime(new_time).strftime('%d.%m.%Y %H:%M')} vaqtiga surildi."
    )
    return redirect("home")


@require_GET
def api_dashboard_stats(request):
    """Dashboard statistikalarini JSON formatda qaytaradi."""
    return JsonResponse({
        'ok': True,
        'stats': build_dashboard_stats(),
    })


@require_GET
def api_ai_recommendation(request):
    """Foydalanuvchi odatlariga qarab rule-based AI tavsiya qaytaradi."""
    return JsonResponse({
        'ok': True,
        'ai_recommendation': build_ai_recommendation(),
    })


@csrf_exempt
def api_notes_list(request):
    """
    GET: search/filter qilingan reminderlarni JSON formatda qaytaradi.
    POST: oddiy note yaratish API — voice note ham shu endpoint orqali saqlanadi.
    """
    if request.method == 'GET':
        queryset, filters = get_notes_queryset(request.GET, limit=200)
        notes = list(queryset)

        return JsonResponse({
            'ok': True,
            'filters': filters,
            'count': len(notes),
            'notes': [note_to_api_dict(note) for note in notes],
        })

    if request.method == 'POST':
        payload = get_request_payload(request)
        note, message = create_note_from_payload(payload)
        if note is None:
            return JsonResponse({'ok': False, 'message': message}, status=400)

        return JsonResponse({
            'ok': True,
            'message': message,
            'note': note_to_api_dict(note),
            'stats': build_dashboard_stats(),
            'ai_recommendation': build_ai_recommendation(),
        }, status=201)

    return JsonResponse({'ok': False, 'message': 'Method not allowed'}, status=405)


@csrf_exempt
def api_voice_note_parse(request):
    """Ovozdan olingan natural matnni title/date/time maydonlariga ajratadi."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'message': 'Method not allowed'}, status=405)

    payload = get_request_payload(request)
    voice_text = (payload.get('text') or payload.get('voice_text') or '').strip()
    if not voice_text:
        return JsonResponse({
            'ok': False,
            'message': 'Ovoz matni bo‘sh. Qayta gapirib ko‘ring.',
        }, status=400)

    parsed = parse_voice_reminder_text(voice_text)
    return JsonResponse({
        'ok': True,
        'parsed': parsed,
    })


@csrf_exempt
def api_note_detail(request, note_id):
    """Bitta noteni olish yoki edit qilish uchun API."""
    note = get_object_or_404(Note, id=note_id)

    if request.method == 'GET':
        return JsonResponse({
            'ok': True,
            'note': note_to_api_dict(note),
        })

    if request.method == 'POST':
        ok, message = update_note_from_request(note, request)
        if not ok:
            return JsonResponse({'ok': False, 'message': message}, status=400)
        note.refresh_from_db()
        return JsonResponse({
            'ok': True,
            'message': message,
            'note': note_to_api_dict(note),
        })

    return JsonResponse({'ok': False, 'message': 'Method not allowed'}, status=405)


@csrf_exempt
@require_POST
def api_snooze_note(request, note_id):
    """
    Frontend/API uchun snooze endpoint.
    JSON yuborish mumkin: {"snooze_option": "15m"}
    FormData yuborish ham mumkin: snooze_option=15m
    """
    note = get_object_or_404(Note, id=note_id)

    option = request.POST.get("snooze_option")

    if not option:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
            option = payload.get("snooze_option") or payload.get("option")
        except json.JSONDecodeError:
            option = None

    option = normalize_snooze_option(option)
    note.snooze(option)
    note.refresh_from_db()

    return JsonResponse({
        'ok': True,
        'message': 'Reminder snooze qilindi va kutilmoqda holatida qoldi.',
        'note': note_to_api_dict(note),
    })


@csrf_exempt
@require_POST
def api_mark_completed_note(request, note_id):
    """Reminderni bajarildi holatiga o'tkazadi va achievementlarni tekshiradi."""
    note = get_object_or_404(Note, id=note_id)
    note.mark_completed()
    note.refresh_from_db()
    unlocked_achievements = check_and_unlock_achievements()

    return JsonResponse({
        'ok': True,
        'message': 'Reminder bajarildi deb belgilandi.',
        'note': note_to_api_dict(note),
        'achievements_unlocked': unlocked_achievements,
        'ai_recommendation': build_ai_recommendation(),
    })


@csrf_exempt
@require_POST
def api_mark_pending_note(request, note_id):
    """Bajarilgan reminderni qayta kutilmoqda holatiga qaytaradi."""
    note = get_object_or_404(Note, id=note_id)
    note.mark_pending()
    note.refresh_from_db()

    return JsonResponse({
        'ok': True,
        'message': 'Reminder kutilmoqda holatiga qaytarildi.',
        'note': note_to_api_dict(note),
        'ai_recommendation': build_ai_recommendation(),
    })


def delete_note(request, note_id):
    note = get_object_or_404(Note, id=note_id)

    if request.method == "POST":
        note.delete()
        messages.success(request, "Eslatma o'chirildi.")

    return redirect("home")
