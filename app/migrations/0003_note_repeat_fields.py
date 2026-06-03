# Generated manually for Smart Note repeat reminder feature

from django.db import migrations, models


def fill_next_reminder_date(apps, schema_editor):
    Note = apps.get_model('app', 'Note')
    for note in Note.objects.all():
        if note.next_reminder_date is None:
            note.next_reminder_date = note.remind_at
            note.save(update_fields=['next_reminder_date'])


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0002_note_priority'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='repeat_type',
            field=models.CharField(
                choices=[
                    ('none', 'Takrorlanmaydi'),
                    ('daily', 'Har kuni'),
                    ('weekly', 'Har hafta'),
                    ('monthly', 'Har oy'),
                    ('mon_fri', 'Dushanba/Juma kunlari'),
                    ('custom_days', 'Custom: har N kunda'),
                    ('custom_weeks', 'Custom: har N haftada'),
                ],
                default='none',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='note',
            name='repeat_interval',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='note',
            name='next_reminder_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(fill_next_reminder_date, migrations.RunPython.noop),
    ]
