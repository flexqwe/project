from datetime import timedelta
import calendar

from django.db import models
from django.utils import timezone


class Note(models.Model):
    PRIORITY_CHOICES = [
        ('shoshilinch', 'Shoshilinch'),
        ('muhim', 'Muhim'),
        ('oddiy', 'Oddiy'),
        ('keyinroq', 'Keyinroq'),
    ]

    CATEGORY_CHOICES = [
        ('oqish', "O‘qish"),
        ('ish', 'Ish'),
        ('shaxsiy', 'Shaxsiy'),
        ('sport', 'Sport'),
        ('oilaviy', 'Oilaviy'),
        ('muhim', 'Muhim'),
    ]

    CATEGORY_META = {
        'oqish': {
            'label': "O‘qish",
            'icon': '📘',
            'color': 'blue',
            'class': 'category-oqish',
        },
        'ish': {
            'label': 'Ish',
            'icon': '💼',
            'color': 'purple',
            'class': 'category-ish',
        },
        'shaxsiy': {
            'label': 'Shaxsiy',
            'icon': '🌿',
            'color': 'green',
            'class': 'category-shaxsiy',
        },
        'sport': {
            'label': 'Sport',
            'icon': '🏃',
            'color': 'emerald',
            'class': 'category-sport',
        },
        'oilaviy': {
            'label': 'Oilaviy',
            'icon': '👨‍👩‍👧',
            'color': 'pink',
            'class': 'category-oilaviy',
        },
        'muhim': {
            'label': 'Muhim',
            'icon': '🔥',
            'color': 'red',
            'class': 'category-muhim',
        },
    }

    REPEAT_TYPE_CHOICES = [
        ('none', 'Takrorlanmaydi'),
        ('daily', 'Har kuni'),
        ('weekly', 'Har hafta'),
        ('monthly', 'Har oy'),
        ('mon_fri', 'Dushanba/Juma kunlari'),
        ('custom_days', 'Custom: har N kunda'),
        ('custom_weeks', 'Custom: har N haftada'),
    ]

    SNOOZE_CHOICES = [
        ('5m', '5 daqiqadan keyin'),
        ('15m', '15 daqiqadan keyin'),
        ('1h', '1 soatdan keyin'),
        ('evening', 'Bugun kechqurun'),
    ]

    text = models.TextField()
    description = models.TextField(blank=True, null=True)
    remind_at = models.DateTimeField()
    sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='oddiy'
    )

    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        default='shaxsiy'
    )

    repeat_type = models.CharField(
        max_length=20,
        choices=REPEAT_TYPE_CHOICES,
        default='none'
    )
    repeat_interval = models.PositiveIntegerField(default=1)
    next_reminder_date = models.DateTimeField(blank=True, null=True)

    # DB ustunlari talabdagi nom bilan yaratiladi: snoozedCount, lastSnoozedAt.
    # Python kodida esa qulay va toza nomlar ishlatiladi: snoozed_count, last_snoozed_at.
    snoozed_count = models.PositiveIntegerField(default=0, db_column='snoozedCount')
    last_snoozed_at = models.DateTimeField(blank=True, null=True, db_column='lastSnoozedAt')

    # Reminder bajarilganini saqlash uchun.
    # DB ustuni talabdagi camelCase nom bilan yaratiladi: completedAt.
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(blank=True, null=True, db_column='completedAt')

    def __str__(self):
        return self.text


    @property
    def category_meta(self):
        return self.CATEGORY_META.get(self.category, self.CATEGORY_META['shaxsiy'])

    @property
    def category_icon(self):
        return self.category_meta['icon']

    @property
    def category_class(self):
        return self.category_meta['class']

    @property
    def category_color(self):
        return self.category_meta['color']

    @property
    def is_repeating(self):
        return self.repeat_type != 'none'

    @property
    def is_completed(self):
        return self.completed

    @property
    def is_pending(self):
        return not self.sent and not self.completed

    @property
    def is_overdue(self):
        return (not self.completed) and self.remind_at and self.remind_at < timezone.now()

    @property
    def status_value(self):
        if self.completed:
            return 'completed'
        if self.is_overdue:
            return 'overdue'
        if self.sent:
            return 'sent'
        return 'pending'

    @property
    def status_label(self):
        status_labels = {
            'completed': 'Bajarildi',
            'overdue': 'Kechikkan',
            'sent': 'Yuborilgan',
            'pending': 'Kutilmoqda',
        }
        return status_labels.get(self.status_value, 'Kutilmoqda')

    # CamelCase aliaslar: template/API/logikada kerak bo'lsa ishlatish mumkin.
    @property
    def snoozedCount(self):
        return self.snoozed_count

    @property
    def lastSnoozedAt(self):
        return self.last_snoozed_at

    @property
    def completedAt(self):
        return self.completed_at

    def mark_completed(self):
        """Reminder statusini bajarildi holatiga o'tkazadi."""
        self.completed = True
        self.completed_at = timezone.now()
        # Bajarilgan reminder qayta yuborilmasligi uchun sent=True qilamiz.
        self.sent = True
        self.save(update_fields=['completed', 'completed_at', 'sent'])

    def mark_pending(self):
        """Reminderni qayta kutilmoqda holatiga qaytaradi."""
        self.completed = False
        self.completed_at = None
        self.sent = False
        self.save(update_fields=['completed', 'completed_at', 'sent'])

    def get_repeat_label(self):
        if self.repeat_type == 'custom_days':
            return f'Har {self.repeat_interval} kunda'
        if self.repeat_type == 'custom_weeks':
            return f'Har {self.repeat_interval} haftada'
        return self.get_repeat_type_display()

    def get_snooze_label(self, option):
        labels = dict(self.SNOOZE_CHOICES)
        return labels.get(option, labels['5m'])

    def _add_months(self, dt, months=1):
        month = dt.month - 1 + months
        year = dt.year + month // 12
        month = month % 12 + 1
        day = min(dt.day, calendar.monthrange(year, month)[1])
        return dt.replace(year=year, month=month, day=day)

    def calculate_next_reminder_date(self, from_date=None):
        """
        Reminder takrorlansa keyingi sanani hisoblaydi.
        Takrorlanmaydigan reminder uchun None qaytaradi.
        """
        if self.repeat_type == 'none':
            return None

        base_date = from_date or self.next_reminder_date or self.remind_at or timezone.localtime(timezone.now())
        interval = self.repeat_interval or 1
        if interval < 1:
            interval = 1

        if self.repeat_type == 'daily':
            return base_date + timedelta(days=1)

        if self.repeat_type == 'weekly':
            return base_date + timedelta(weeks=1)

        if self.repeat_type == 'monthly':
            return self._add_months(base_date, 1)

        if self.repeat_type == 'mon_fri':
            # Keyingi Dushanba yoki Juma kunini topadi.
            # Python weekday: Dushanba=0, Juma=4
            for days in range(1, 8):
                candidate = base_date + timedelta(days=days)
                if candidate.weekday() in (0, 4):
                    return candidate
            return base_date + timedelta(days=1)

        if self.repeat_type == 'custom_days':
            return base_date + timedelta(days=interval)

        if self.repeat_type == 'custom_weeks':
            return base_date + timedelta(weeks=interval)

        return None

    def calculate_snooze_until(self, option, now=None):
        """
        Snooze tanloviga qarab yangi reminder vaqtini hisoblaydi.
        evening: bugun 20:00. Agar 20:00 dan o'tgan bo'lsa, ertangi 20:00.
        """
        option = option or '5m'
        allowed_options = dict(self.SNOOZE_CHOICES)
        if option not in allowed_options:
            option = '5m'

        local_now = timezone.localtime(now or timezone.now())

        if option == '5m':
            return local_now + timedelta(minutes=5)

        if option == '15m':
            return local_now + timedelta(minutes=15)

        if option == '1h':
            return local_now + timedelta(hours=1)

        if option == 'evening':
            target = local_now.replace(hour=20, minute=0, second=0, microsecond=0)
            if target <= local_now:
                target = target + timedelta(days=1)
            return target

        return local_now + timedelta(minutes=5)

    def snooze(self, option):
        """
        Reminder vaqtini keyinga suradi va statusni kutilmoqda holatida qoldiradi.
        """
        new_remind_at = self.calculate_snooze_until(option)
        self.remind_at = new_remind_at
        self.next_reminder_date = new_remind_at
        self.sent = False
        self.completed = False
        self.completed_at = None
        self.snoozed_count = (self.snoozed_count or 0) + 1
        self.last_snoozed_at = timezone.now()
        self.save(update_fields=[
            'remind_at',
            'next_reminder_date',
            'sent',
            'completed',
            'completed_at',
            'snoozed_count',
            'last_snoozed_at',
        ])
        return new_remind_at



class Achievement(models.Model):
    """Smart Note motivatsion badge/yutuqlar jadvali."""

    ACHIEVEMENT_CHOICES = [
        ('streak_3_days', '3 kun ketma-ket vazifa bajardi'),
        ('completed_10_notes', '10 ta note yakunlandi'),
        ('week_discipline', '1 hafta intizomli ishladi'),
        ('today_all_done', 'Bugungi barcha vazifalarni tugatdi'),
    ]

    code = models.CharField(max_length=60, unique=True, choices=ACHIEVEMENT_CHOICES)
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=20, default='🏆')
    color = models.CharField(max_length=30, default='blue')
    unlocked = models.BooleanField(default=False)
    unlocked_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return self.title

    @property
    def color_class(self):
        return f'achievement-{self.color}'
