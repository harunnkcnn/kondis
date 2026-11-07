from datetime import timedelta

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Client, Exercise, Membership, Program, ProgramDay, ProgramItem, Workout
from .services import TEMPLATES


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["full_name", "phone", "email", "goal", "target_weight", "notes", "is_active"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class MembershipForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = ["package_name", "starts_on", "ends_on", "sessions_total", "price", "note"]
        widgets = {
            "starts_on": forms.DateInput(attrs={"type": "date"}),
            "ends_on": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            today = timezone.localdate()
            self.initial.setdefault("starts_on", today)
            self.initial.setdefault("ends_on", today + timedelta(days=30))

    def clean(self):
        data = super().clean()
        starts, ends = data.get("starts_on"), data.get("ends_on")
        if starts and ends and ends < starts:
            self.add_error("ends_on", _("The end date can't be before the start date."))
        return data


class ProgramForm(forms.ModelForm):
    template = forms.ChoiceField(
        label=_("Start from"),
        required=False,
        choices=[("", _("An empty program"))] + [(key, spec["title"]) for key, spec in TEMPLATES.items()],
    )

    class Meta:
        model = Program
        fields = ["title", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = False

    def clean(self):
        data = super().clean()
        if not data.get("title") and not data.get("template"):
            self.add_error("title", _("Give the program a title or pick a starter."))
        return data


class ProgramDayForm(forms.ModelForm):
    class Meta:
        model = ProgramDay
        fields = ["title", "weekday"]


class ProgramItemForm(forms.ModelForm):
    class Meta:
        model = ProgramItem
        fields = ["exercise", "sets", "reps", "target_weight", "rest_seconds", "note"]

    def __init__(self, *args, trainer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["exercise"].queryset = Exercise.available_to(trainer)
        self.fields["exercise"].label_from_instance = lambda e: e.name


class ExerciseForm(forms.ModelForm):
    class Meta:
        model = Exercise
        fields = ["name_tr", "name_en", "muscle", "equipment", "cue"]


class SetEntryForm(forms.Form):
    exercise = forms.IntegerField(widget=forms.HiddenInput)
    item = forms.IntegerField(widget=forms.HiddenInput, required=False)
    weight = forms.DecimalField(min_value=0, max_value=1000, decimal_places=2, required=False)
    reps = forms.IntegerField(min_value=1, max_value=500)


class FinishWorkoutForm(forms.ModelForm):
    class Meta:
        model = Workout
        fields = ["body_weight", "note"]
        widgets = {"note": forms.TextInput(attrs={"placeholder": _("Energy, pain, anything your coach should know")})}
