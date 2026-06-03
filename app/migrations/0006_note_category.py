# Generated manually for Smart Note search/filter category feature

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0005_note_completed_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='category',
            field=models.CharField(
                choices=[
                    ('oqish', 'O‘qish'),
                    ('ish', 'Ish'),
                    ('shaxsiy', 'Shaxsiy'),
                    ('sport', 'Sport'),
                    ('oilaviy', 'Oilaviy'),
                    ('muhim', 'Muhim'),
                ],
                default='shaxsiy',
                max_length=30,
            ),
        ),
    ]
