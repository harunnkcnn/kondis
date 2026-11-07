from datetime import timedelta

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Client, Exercise, Membership, ProgramDay, ProgramItem, Workout
from .services import TEMPLATES

DAYS_CHOICES = [(n, str(n)) for n in range(2, 7)]
MINUTES_CHOICES = [(m, f"{m}") for m in (30, 45, 60, 75, 90)]


class TrainingProfileMixin(forms.Form):
    """Shared fields for a client's training profile, used by the program generator."""

    days_per_week = forms.TypedChoiceField(label=_("Training days per week"), choices=DAYS_CHOICES, coerce=int, initial=3)
    session_minutes = forms.TypedChoiceField(label=_("Session length (min)"), choices=MINUTES_CHOICES, coerce=int, initial=60)
    limitations = forms.MultipleChoiceField(
        label=_("Areas to protect"),
        choices=Client.Limitation.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Exercises that load these joints are left out of generated programs."),
    )


class ClientForm(TrainingProfileMixin, forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "full_name",
            "phone",
            "email",
            "goal",
            "level",
            "days_per_week",
            "session_minutes",
            "equipment",
            "limitations",
            "target_weight",
            "notes",
            "is_active",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["limitations"] = self.instance.limitation_list

    def clean_limitations(self):
        return ",".join(self.cleaned_data["limitations"])


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


class ProgramForm(TrainingProfileMixin, forms.Form):
    AUTO, TEMPLATE, EMPTY = "auto", "template", "empty"

    mode = forms.ChoiceField(
        label=_("How do you want to start?"),
        choices=[
            (AUTO, _("Generate a program for this client")),
            (TEMPLATE, _("Start from a ready-made template")),
            (EMPTY, _("Start empty and write it myself")),
        ],
        initial=AUTO,
        widget=forms.RadioSelect,
    )
    goal = forms.ChoiceField(label=_("Goal"), choices=Client.Goal.choices)
    level = forms.ChoiceField(label=_("Training level"), choices=Client.Level.choices)
    equipment = forms.ChoiceField(label=_("Equipment"), choices=Client.Equipment.choices)
    template = forms.ChoiceField(label=_("Template"), required=False, choices=[(key, spec["title"]) for key, spec in TEMPLATES.items()])
    title = forms.CharField(
        label=_("Title"), max_length=100, required=False, help_text=_("Optional. A title is suggested if you leave it empty.")
    )
    notes = forms.CharField(label=_("Notes for the client"), required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, client: Client, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("goal", "level", "equipment", "days_per_week", "session_minutes"):
            self.initial.setdefault(name, getattr(client, name))
        self.initial.setdefault("limitations", client.limitation_list)

    def clean(self):
        data = super().clean()
        if data.get("mode") == self.EMPTY and not data.get("title"):
            self.add_error("title", _("Give the empty program a title."))
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
