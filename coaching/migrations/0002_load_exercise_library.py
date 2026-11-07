from django.db import migrations


def load(apps, schema_editor):
    from coaching.library import EXERCISES

    Exercise = apps.get_model("coaching", "Exercise")
    for slug, name_tr, name_en, muscle, equipment, cue in EXERCISES:
        Exercise.objects.update_or_create(
            trainer=None,
            slug=slug,
            defaults={"name_tr": name_tr, "name_en": name_en, "muscle": muscle, "equipment": equipment, "cue": cue},
        )


def unload(apps, schema_editor):
    apps.get_model("coaching", "Exercise").objects.filter(trainer__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("coaching", "0001_initial")]
    operations = [migrations.RunPython(load, unload)]
