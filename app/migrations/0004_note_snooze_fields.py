# Generated manually for Smart Note snooze reminder feature

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0003_note_repeat_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='snoozed_count',
            field=models.PositiveIntegerField(default=0, db_column='snoozedCount'),
        ),
        migrations.AddField(
            model_name='note',
            name='last_snoozed_at',
            field=models.DateTimeField(blank=True, null=True, db_column='lastSnoozedAt'),
        ),
    ]
