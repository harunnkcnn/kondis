from django.db import migrations

BASE_FIELDS = ("name_tr", "name_en", "muscle", "equipment", "cue")


def load(apps, schema_editor):
    from coaching.library import EXERCISES

    Exercise = apps.get_model("coaching", "Exercise")
    for entry in EXERCISES:
        Exercise.objects.update_or_create(trainer=None, slug=entry["slug"], defaults={k: entry[k] for k in BASE_FIELDS})


def unload(apps, schema_editor):
    apps.get_model("coaching", "Exercise").objects.filter(trainer__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("coaching", "0001_initial")]
    operations = [migrations.RunPython(load, unload)]
