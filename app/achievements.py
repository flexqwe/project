from datetime import timedelta

from django.db import OperationalError, ProgrammingError
from django.utils import timezone

from .models import Achievement, Note


ACHIEVEMENT_DEFINITIONS = {
    'streak_3_days': {
        'title': '3 kunlik seriya',
        'description': '3 kun ketma-ket kamida bittadan vazifa bajardingiz.',
        'icon': '🔥',
        'color': 'orange',
        'target': 3,
    },
    'completed_10_notes': {
        'title': '10 ta note yakunlandi',
        'description': 'Jami 10 ta reminder/note bajarildi deb belgilandi.',
        'icon': '🏅',
        'color': 'purple',
        'target': 10,
    },
    'week_discipline': {
        'title': '1 hafta intizom',
        'description': '7 kun ketma-ket kamida bittadan vazifa bajardingiz.',
        'icon': '💎',
        'color': 'blue',
        'target': 7,
    },
    'today_all_done': {
        'title': 'Bugun 100%',
        'description': 'Bugungi barcha vazifalarni to‘liq tugatdingiz.',
        'icon': '✅',
        'color': 'green',
        'target': 1,
    },
}


def _safe_achievement_query(func, default=None):
    """Migration hali yurmagan holatlarda sahifa yiqilmasligi uchun helper."""
    try:
        return func()
    except (OperationalError, ProgrammingError):
        return default


def ensure_achievement_rows():
    """Badge definitionlari DB ichida borligini ta'minlaydi."""
    achievements = []
    for code, meta in ACHIEVEMENT_DEFINITIONS.items():
        achievement, created = Achievement.objects.get_or_create(
            code=code,
            defaults={
                'title': meta['title'],
                'description': meta['description'],
                'icon': meta['icon'],
                'color': meta['color'],
            }
        )
        changed = False
        for field in ('title', 'description', 'icon', 'color'):
            value = meta[field]
            if getattr(achievement, field) != value:
                setattr(achievement, field, value)
                changed = True
        if changed:
            achievement.save(update_fields=['title', 'description', 'icon', 'color'])
        achievements.append(achievement)
    return achievements


def completed_dates_set():
    """completed_at bo'yicha bajarilgan kunlar to'plamini qaytaradi."""
    dates = set()
    for value in Note.objects.filter(completed=True, completed_at__isnull=False).values_list('completed_at', flat=True):
        dates.add(timezone.localtime(value).date())
    return dates


def longest_completion_streak(dates=None):
    """Istalgan vaqtdagi eng uzun ketma-ket bajarilgan kunlar seriyasi."""
    dates = sorted(dates or completed_dates_set())
    if not dates:
        return 0

    best = 1
    current = 1
    for index in range(1, len(dates)):
        if dates[index] == dates[index - 1] + timedelta(days=1):
            current += 1
        elif dates[index] != dates[index - 1]:
            current = 1
        best = max(best, current)
    return best


def current_completion_streak(dates=None):
    """Bugundan yoki oxirgi bajarilgan kundan orqaga qarab aktiv seriyani hisoblaydi."""
    dates = dates or completed_dates_set()
    if not dates:
        return 0

    start_day = timezone.localtime(timezone.now()).date()
    if start_day not in dates:
        start_day = max(dates)

    streak = 0
    day = start_day
    while day in dates:
        streak += 1
        day -= timedelta(days=1)
    return streak


def get_today_note_counts():
    now = timezone.localtime(timezone.now())
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    today_qs = Note.objects.filter(remind_at__gte=start, remind_at__lt=end)
    total = today_qs.count()
    completed = today_qs.filter(completed=True).count()
    return total, completed


def build_achievement_progress():
    dates = completed_dates_set()
    longest_streak = longest_completion_streak(dates)
    active_streak = current_completion_streak(dates)
    completed_total = Note.objects.filter(completed=True).count()
    today_total, today_completed = get_today_note_counts()

    return {
        'streak_3_days': {
            'current': min(active_streak, 3),
            'target': 3,
            'raw_current': active_streak,
            'label': f'{active_streak}/3 kun',
            'eligible': longest_streak >= 3,
        },
        'completed_10_notes': {
            'current': min(completed_total, 10),
            'target': 10,
            'raw_current': completed_total,
            'label': f'{completed_total}/10 note',
            'eligible': completed_total >= 10,
        },
        'week_discipline': {
            'current': min(active_streak, 7),
            'target': 7,
            'raw_current': active_streak,
            'label': f'{active_streak}/7 kun',
            'eligible': longest_streak >= 7,
        },
        'today_all_done': {
            'current': today_completed if today_total else 0,
            'target': today_total if today_total else 1,
            'raw_current': today_completed,
            'label': f'{today_completed}/{today_total} bugungi vazifa' if today_total else 'Bugun vazifa yo‘q',
            'eligible': today_total > 0 and today_completed == today_total,
        },
    }


def check_and_unlock_achievements():
    """Vazifa bajarilgandan keyin yangi ochilgan achievementlarni qaytaradi."""
    def _check():
        ensure_achievement_rows()
        progress = build_achievement_progress()
        unlocked_now = []
        now = timezone.now()

        for code, progress_item in progress.items():
            if not progress_item.get('eligible'):
                continue

            achievement = Achievement.objects.get(code=code)
            if achievement.unlocked:
                continue

            achievement.unlocked = True
            achievement.unlocked_at = now
            achievement.save(update_fields=['unlocked', 'unlocked_at'])
            unlocked_now.append(achievement_to_dict(achievement, progress_item))

        return unlocked_now

    return _safe_achievement_query(_check, default=[])


def achievement_to_dict(achievement, progress_item=None):
    progress_item = progress_item or build_achievement_progress().get(achievement.code, {})
    unlocked_at = timezone.localtime(achievement.unlocked_at) if achievement.unlocked_at else None
    target = progress_item.get('target') or ACHIEVEMENT_DEFINITIONS.get(achievement.code, {}).get('target', 1)
    current = progress_item.get('current', 0)
    percent = round((current / target) * 100) if target else 0
    percent = max(0, min(percent, 100))

    return {
        'code': achievement.code,
        'title': achievement.title,
        'description': achievement.description,
        'icon': achievement.icon,
        'color': achievement.color,
        'color_class': achievement.color_class,
        'unlocked': achievement.unlocked,
        'unlocked_at': unlocked_at.isoformat() if unlocked_at else None,
        'unlocked_at_display': unlocked_at.strftime('%d.%m.%Y %H:%M') if unlocked_at else '',
        'progress_current': progress_item.get('raw_current', current),
        'progress_target': target,
        'progress_label': progress_item.get('label', f'{current}/{target}'),
        'progress_percent': percent,
    }


def get_achievements_data():
    """Achievements sahifasi va API uchun barcha badge ma'lumotlari."""
    def _build():
        achievements = ensure_achievement_rows()
        progress = build_achievement_progress()
        cards = [achievement_to_dict(item, progress.get(item.code)) for item in achievements]
        unlocked_count = sum(1 for item in cards if item['unlocked'])
        total_count = len(cards)
        percent = round((unlocked_count / total_count) * 100) if total_count else 0
        return {
            'achievements': cards,
            'unlocked_count': unlocked_count,
            'locked_count': max(total_count - unlocked_count, 0),
            'total_count': total_count,
            'progress_percent': percent,
            'is_empty': total_count == 0,
        }

    return _safe_achievement_query(_build, default={
        'achievements': [],
        'unlocked_count': 0,
        'locked_count': 0,
        'total_count': 0,
        'progress_percent': 0,
        'is_empty': True,
    })
