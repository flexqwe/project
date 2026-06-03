# Generated manually for Smart Note completed reminder feature

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0004_note_snooze_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='completed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='note',
            name='completed_at',
            field=models.DateTimeField(blank=True, null=True, db_column='completedAt'),
        ),
    ]
