from django.db import migrations, models


ACHIEVEMENTS = {
    'streak_3_days': {
        'title': '3 kunlik seriya',
        'description': '3 kun ketma-ket kamida bittadan vazifa bajardingiz.',
        'icon': '🔥',
        'color': 'orange',
    },
    'completed_10_notes': {
        'title': '10 ta note yakunlandi',
        'description': 'Jami 10 ta reminder/note bajarildi deb belgilandi.',
        'icon': '🏅',
        'color': 'purple',
    },
    'week_discipline': {
        'title': '1 hafta intizom',
        'description': '7 kun ketma-ket kamida bittadan vazifa bajardingiz.',
        'icon': '💎',
        'color': 'blue',
    },
    'today_all_done': {
        'title': 'Bugun 100%',
        'description': 'Bugungi barcha vazifalarni to‘liq tugatdingiz.',
        'icon': '✅',
        'color': 'green',
    },
}


def create_default_achievements(apps, schema_editor):
    Achievement = apps.get_model('app', 'Achievement')
    for code, meta in ACHIEVEMENTS.items():
        Achievement.objects.get_or_create(
            code=code,
            defaults={
                'title': meta['title'],
                'description': meta['description'],
                'icon': meta['icon'],
                'color': meta['color'],
            }
        )


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0007_update_note_categories'),
    ]

    operations = [
        migrations.CreateModel(
            name='Achievement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(choices=[('streak_3_days', '3 kun ketma-ket vazifa bajardi'), ('completed_10_notes', '10 ta note yakunlandi'), ('week_discipline', '1 hafta intizomli ishladi'), ('today_all_done', 'Bugungi barcha vazifalarni tugatdi')], max_length=60, unique=True)),
                ('title', models.CharField(max_length=120)),
                ('description', models.TextField(blank=True)),
                ('icon', models.CharField(default='🏆', max_length=20)),
                ('color', models.CharField(default='blue', max_length=30)),
                ('unlocked', models.BooleanField(default=False)),
                ('unlocked_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.RunPython(create_default_achievements, migrations.RunPython.noop),
    ]
