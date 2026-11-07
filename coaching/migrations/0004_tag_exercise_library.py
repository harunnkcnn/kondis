from django.db import migrations

FIELDS = ("name_tr", "name_en", "muscle", "equipment", "cue", "pattern", "stresses")


def tag(apps, schema_editor):
    from coaching.library import EXERCISES

    Exercise = apps.get_model("coaching", "Exercise")
    for entry in EXERCISES:
        Exercise.objects.update_or_create(trainer=None, slug=entry["slug"], defaults={k: entry[k] for k in FIELDS})


class Migration(migrations.Migration):
    dependencies = [("coaching", "0003_training_profile_and_generator")]
    operations = [migrations.RunPython(tag, migrations.RunPython.noop)]
