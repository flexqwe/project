# Generated manually for Smart Note category colors feature

from django.db import migrations, models


OLD_TO_DEFAULT = {
    '': 'shaxsiy',
    None: 'shaxsiy',
    'umumiy': 'shaxsiy',
    'soglik': 'shaxsiy',
    'moliya': 'shaxsiy',
}

VALID_CATEGORIES = {'oqish', 'ish', 'shaxsiy', 'sport', 'oilaviy', 'muhim'}


def normalize_old_categories(apps, schema_editor):
    Note = apps.get_model('app', 'Note')
    for note in Note.objects.all():
        category = getattr(note, 'category', None)
        new_category = OLD_TO_DEFAULT.get(category, category)
        if new_category not in VALID_CATEGORIES:
            new_category = 'shaxsiy'
        if category != new_category:
            note.category = new_category
            note.save(update_fields=['category'])


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0006_note_category'),
    ]

    operations = [
        migrations.RunPython(normalize_old_categories, migrations.RunPython.noop),
        migrations.AlterField(
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
