from collections import Counter, defaultdict
from datetime import timedelta

from django.utils import timezone

from .models import Note


TIME_BUCKETS = [
    ('morning', 'ertalab', 5, 11, 'Ertalabgi vazifalar odatda aniqroq bajariladi. Muhim ishlarni 09:00–11:00 oralig‘iga qo‘yib ko‘ring.'),
    ('afternoon', 'kunduzi', 12, 16, 'Kunduzgi vazifalarni qisqa bloklarga bo‘lib rejalashtirsangiz, bajarish osonlashadi.'),
    ('evening', 'kechqurun', 17, 21, 'Sen ko‘pincha kechqurun qo‘yilgan vazifalarni bajarmayapsan. Yaxshisi ularni ertalabga ko‘chir.'),
    ('night', 'tunda', 22, 4, 'Tungi vazifalar ko‘p qolib ketyapti. Ularni ertaroq vaqtga yoki keyingi kun ertalabiga o‘tkaz.'),
]


class RuleBasedAIRecommendationEngine:
    """
    Hozircha oddiy rule-based tavsiya generatori.
    Keyinchalik OpenAI API yoki boshqa AI service ulash uchun shu class o'rniga
    LLMRecommendationEngine yozib, build_ai_recommendation ichida almashtirish mumkin.
    """

    window_days = 60

    def __init__(self):
        self.now = timezone.now()
        self.local_now = timezone.localtime(self.now)
        self.window_start = self.now - timedelta(days=self.window_days)

    def _bucket_for_hour(self, hour):
        for key, label, start, end, advice in TIME_BUCKETS:
            if start <= end:
                if start <= hour <= end:
                    return key, label, advice
            else:
                if hour >= start or hour <= end:
                    return key, label, advice
        return 'other', 'boshqa vaqt', 'Vazifalarni energiyangiz yuqori bo‘lgan vaqtga qo‘yib ko‘ring.'

    def _completion_rate(self, completed, total):
        return round((completed / total) * 100) if total else 0

    def _recommendation(self, title, text, icon='🤖', level='info', metric=''):
        return {
            'title': title,
            'text': text,
            'icon': icon,
            'level': level,
            'metric': metric,
        }

    def analyze(self):
        notes = list(
            Note.objects.filter(created_at__gte=self.window_start)
            .order_by('-created_at', '-id')
        )
        total_count = len(notes)

        if total_count == 0:
            return {
                'provider': 'rule_based',
                'generated_at': self.local_now.isoformat(),
                'generated_at_display': self.local_now.strftime('%d.%m.%Y %H:%M'),
                'is_empty': True,
                'level': 'empty',
                'score': 0,
                'summary': 'Tahlil uchun hali reminder yo‘q.',
                'primary_recommendation': 'Birinchi eslatmani yarating — keyin Smart Note odatlaringizga qarab tavsiya beradi.',
                'recommendations': [
                    self._recommendation(
                        'Boshlash uchun maslahat',
                        'Bugun uchun 1–2 ta kichik vazifa qo‘shing. Bir necha bajarilgan vazifadan keyin AI tavsiyalar aniqroq bo‘ladi.',
                        icon='🌱',
                        level='info',
                    )
                ],
                'metrics': {
                    'total_count': 0,
                    'completed_count': 0,
                    'overdue_count': 0,
                    'late_completed_count': 0,
                    'snoozed_total': 0,
                    'completion_rate': 0,
                    'window_days': self.window_days,
                },
                'can_upgrade_to_ai_service': True,
            }

        completed_notes = [note for note in notes if note.completed]
        overdue_notes = [note for note in notes if (not note.completed and note.remind_at and note.remind_at < self.now)]
        snoozed_notes = [note for note in notes if (note.snoozed_count or 0) > 0]
        late_completed_notes = [
            note for note in completed_notes
            if note.completed_at and note.remind_at and note.completed_at > note.remind_at + timedelta(minutes=30)
        ]

        completed_count = len(completed_notes)
        overdue_count = len(overdue_notes)
        late_completed_count = len(late_completed_notes)
        snoozed_total = sum(note.snoozed_count or 0 for note in notes)
        completion_rate = self._completion_rate(completed_count, total_count)
        overdue_rate = self._completion_rate(overdue_count, total_count)
        late_rate = self._completion_rate(late_completed_count, max(completed_count, 1)) if completed_count else 0
        snooze_rate = self._completion_rate(len(snoozed_notes), total_count)

        recommendations = []
        attention_points = 0

        if overdue_count >= 3 or overdue_rate >= 30:
            attention_points += 2
            recommendations.append(self._recommendation(
                'Kechikkan vazifalar ko‘paygan',
                'Kechikkan vazifalar soni ko‘p. Muhim vazifalarni 2–3 ta kichik qadamga bo‘lib, vaqtini biroz ertaroqqa qo‘ying.',
                icon='⚠️',
                level='warning',
                metric=f'{overdue_count} ta kechikkan · {overdue_rate}%'
            ))

        if late_completed_count >= 2 and late_rate >= 30:
            attention_points += 1
            recommendations.append(self._recommendation(
                'Vazifalar vaqtida tugamayapti',
                'Ba’zi vazifalar belgilangan vaqtdan keyin bajarilgan. Reminder vaqtini realroq tanlang yoki oldindan 10–15 daqiqalik signal qo‘ying.',
                icon='⏰',
                level='warning',
                metric=f'{late_completed_count} ta kech bajarilgan'
            ))

        if snoozed_total >= 4 or snooze_rate >= 25:
            attention_points += 1
            recommendations.append(self._recommendation(
                'Snooze ko‘p ishlatilmoqda',
                'Snooze ko‘p bosilayotgan bo‘lsa, vazifa vaqti noqulay bo‘lishi mumkin. Eng qiyin vazifalarni ertalab yoki energiyangiz yuqori paytga ko‘chiring.',
                icon='😴',
                level='warning',
                metric=f'{snoozed_total} marta snooze'
            ))

        bucket_stats = defaultdict(lambda: {'total': 0, 'completed': 0, 'overdue': 0, 'label': '', 'advice': ''})
        for note in notes:
            if not note.remind_at:
                continue
            local_remind_at = timezone.localtime(note.remind_at)
            bucket_key, bucket_label, bucket_advice = self._bucket_for_hour(local_remind_at.hour)
            bucket_stats[bucket_key]['total'] += 1
            bucket_stats[bucket_key]['label'] = bucket_label
            bucket_stats[bucket_key]['advice'] = bucket_advice
            if note.completed:
                bucket_stats[bucket_key]['completed'] += 1
            elif note.remind_at < self.now:
                bucket_stats[bucket_key]['overdue'] += 1

        weak_bucket = None
        for key, item in bucket_stats.items():
            if item['total'] < 3:
                continue
            bucket_completion = self._completion_rate(item['completed'], item['total'])
            bucket_problem_count = item['total'] - item['completed']
            candidate = {
                'key': key,
                'label': item['label'],
                'advice': item['advice'],
                'total': item['total'],
                'completed': item['completed'],
                'completion_rate': bucket_completion,
                'problem_count': bucket_problem_count,
            }
            if bucket_completion < 55 and (weak_bucket is None or bucket_completion < weak_bucket['completion_rate']):
                weak_bucket = candidate

        if weak_bucket:
            attention_points += 2
            recommendations.append(self._recommendation(
                f'{weak_bucket["label"].capitalize()} vazifalari qiyinroq bajarilmoqda',
                weak_bucket['advice'],
                icon='🕒',
                level='warning',
                metric=f'{weak_bucket["completed"]}/{weak_bucket["total"]} bajarilgan · {weak_bucket["completion_rate"]}%'
            ))

        category_counter = Counter()
        problem_notes_by_id = {note.id: note for note in overdue_notes}
        for note in notes:
            if not note.completed and note.sent:
                problem_notes_by_id[note.id] = note
        for note in problem_notes_by_id.values():
            category_counter[note.category] += 1
        if category_counter:
            category_key, category_count = category_counter.most_common(1)[0]
            category_label = dict(Note.CATEGORY_CHOICES).get(category_key, 'Shaxsiy')
            if category_count >= 2:
                attention_points += 1
                recommendations.append(self._recommendation(
                    f'{category_label} bo‘yicha e’tibor kerak',
                    f'{category_label} category’dagi vazifalar ko‘proq qolib ketmoqda. Shu category uchun alohida vaqt bloki ajrating.',
                    icon='🏷️',
                    level='info',
                    metric=f'{category_count} ta muammo'
                ))

        high_priority_problem = sum(1 for note in notes if note.priority in {'shoshilinch', 'muhim'} and not note.completed and note.remind_at < self.now)
        if high_priority_problem >= 1:
            attention_points += 1
            recommendations.append(self._recommendation(
                'Muhim vazifalarni birinchi qo‘ying',
                'Shoshilinch yoki muhim vazifalar kechikmasligi uchun ularni kun boshiga qo‘ying va mayda vazifalardan oldin bajaring.',
                icon='🔥',
                level='warning',
                metric=f'{high_priority_problem} ta muhim kechikkan'
            ))

        if not recommendations:
            recommendations.append(self._recommendation(
                'Yaxshi ritm saqlanyapti',
                'Hozircha odatlaringiz yaxshi ko‘rinmoqda. Bugungi vazifalarni ham vaqtida tugatsangiz, progress yanada mustahkam bo‘ladi.',
                icon='✅',
                level='success',
                metric=f'{completion_rate}% bajarilgan'
            ))

        if completion_rate >= 75 and overdue_count == 0:
            level = 'success'
            summary = 'Ajoyib! Vazifalar yaxshi nazoratda.'
            score = min(100, completion_rate)
        elif attention_points >= 3 or overdue_rate >= 35:
            level = 'warning'
            summary = 'Rejada biroz tartib kerak.'
            score = max(15, completion_rate - 10)
        else:
            level = 'info'
            summary = 'Smart Note odatlaringizni kuzatyapti.'
            score = max(20, completion_rate)

        primary_recommendation = recommendations[0]['text']

        return {
            'provider': 'rule_based',
            'generated_at': self.local_now.isoformat(),
            'generated_at_display': self.local_now.strftime('%d.%m.%Y %H:%M'),
            'is_empty': False,
            'level': level,
            'score': score,
            'summary': summary,
            'primary_recommendation': primary_recommendation,
            'recommendations': recommendations[:4],
            'metrics': {
                'total_count': total_count,
                'completed_count': completed_count,
                'overdue_count': overdue_count,
                'late_completed_count': late_completed_count,
                'snoozed_total': snoozed_total,
                'completion_rate': completion_rate,
                'overdue_rate': overdue_rate,
                'snooze_rate': snooze_rate,
                'window_days': self.window_days,
            },
            'time_bucket_problem': weak_bucket,
            'can_upgrade_to_ai_service': True,
        }


def build_ai_recommendation():
    """Dashboard va API uchun AI tavsiya ma'lumotlarini qaytaradi."""
    engine = RuleBasedAIRecommendationEngine()
    return engine.analyze()
