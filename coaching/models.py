from __future__ import annotations

import secrets
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

EXPIRING_SOON_DAYS = 7


def new_access_token() -> str:
    return secrets.token_urlsafe(24)


class Client(models.Model):
    class Goal(models.TextChoices):
        STRENGTH = "strength", _("Strength")
        MUSCLE = "muscle", _("Muscle gain")
        FAT_LOSS = "fat_loss", _("Fat loss")
        MOBILITY = "mobility", _("Mobility and rehab")
        GENERAL = "general", _("General fitness")

    class Level(models.TextChoices):
        BEGINNER = "beginner", _("Beginner")
        INTERMEDIATE = "intermediate", _("Intermediate")
        ADVANCED = "advanced", _("Advanced")

    class Equipment(models.TextChoices):
        GYM = "gym", _("Full gym")
        DUMBBELLS = "dumbbells", _("Dumbbells and bands")
        HOME = "home", _("Bodyweight only")

    class Limitation(models.TextChoices):
        KNEE = "knee", _("Knee")
        SHOULDER = "shoulder", _("Shoulder")
        LOWER_BACK = "lower_back", _("Lower back")

    trainer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="clients")
    full_name = models.CharField(_("full name"), max_length=120)
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    email = models.EmailField(_("email"), blank=True)
    goal = models.CharField(_("goal"), max_length=16, choices=Goal.choices, default=Goal.GENERAL)
    target_weight = models.DecimalField(_("target body weight (kg)"), max_digits=5, decimal_places=1, null=True, blank=True)
    notes = models.TextField(_("notes"), blank=True, help_text=_("Injuries, preferences, anything worth remembering."))
    level = models.CharField(_("training level"), max_length=16, choices=Level.choices, default=Level.BEGINNER)
    days_per_week = models.PositiveSmallIntegerField(_("training days per week"), default=3)
    session_minutes = models.PositiveSmallIntegerField(_("session length (min)"), default=60)
    equipment = models.CharField(_("equipment"), max_length=16, choices=Equipment.choices, default=Equipment.GYM)
    limitations = models.CharField(_("areas to protect"), max_length=64, blank=True)
    access_token = models.CharField(max_length=64, unique=True, default=new_access_token, editable=False)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self) -> str:
        return self.full_name

    def get_absolute_url(self) -> str:
        return reverse("coaching:client_detail", args=[self.pk])

    def portal_path(self) -> str:
        return reverse("portal:home", args=[self.access_token])

    def rotate_token(self) -> None:
        self.access_token = new_access_token()
        self.save(update_fields=["access_token"])

    @property
    def limitation_list(self) -> list[str]:
        return [v for v in self.limitations.split(",") if v]

    @property
    def initials(self) -> str:
        parts = self.full_name.split()
        return "".join(p[0] for p in parts[:2]).upper() or "?"

    @property
    def active_program(self) -> Program | None:
        return self.programs.filter(is_active=True).first()

    @property
    def current_membership(self) -> Membership | None:
        return self.memberships.order_by("-ends_on").first()

    @property
    def last_workout(self) -> Workout | None:
        return self.workouts.order_by("-performed_on", "-created_at").first()


class Membership(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        EXPIRING = "expiring", _("Ending soon")
        EXPIRED = "expired", _("Ended")
        USED_UP = "used_up", _("No sessions left")
        UPCOMING = "upcoming", _("Starts later")

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="memberships")
    package_name = models.CharField(_("package"), max_length=80, help_text=_("e.g. 12 PT sessions, 3 months"))
    starts_on = models.DateField(_("starts on"), default=date.today)
    ends_on = models.DateField(_("ends on"))
    sessions_total = models.PositiveSmallIntegerField(
        _("sessions included"), null=True, blank=True, help_text=_("Leave empty for unlimited.")
    )
    sessions_used = models.PositiveSmallIntegerField(_("sessions used"), default=0)
    price = models.DecimalField(_("price"), max_digits=10, decimal_places=2, null=True, blank=True)
    note = models.CharField(_("note"), max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ends_on"]

    def __str__(self) -> str:
        return f"{self.client} / {self.package_name}"

    def days_left(self, today: date | None = None) -> int:
        today = today or timezone.localdate()
        return (self.ends_on - today).days

    @property
    def sessions_left(self) -> int | None:
        if self.sessions_total is None:
            return None
        return max(self.sessions_total - self.sessions_used, 0)

    def status(self, today: date | None = None) -> str:
        today = today or timezone.localdate()
        if self.starts_on > today:
            return self.Status.UPCOMING
        if self.ends_on < today:
            return self.Status.EXPIRED
        if self.sessions_left == 0:
            return self.Status.USED_UP
        if self.days_left(today) <= EXPIRING_SOON_DAYS or (self.sessions_left is not None and self.sessions_left <= 2):
            return self.Status.EXPIRING
        return self.Status.ACTIVE

    @property
    def status_label(self) -> str:
        return self.Status(self.status()).label

    def use_session(self) -> bool:
        """Count one session. Returns False when nothing is left to use."""
        with transaction.atomic():
            locked = Membership.objects.select_for_update().get(pk=self.pk)
            if locked.sessions_total is not None and locked.sessions_used >= locked.sessions_total:
                return False
            locked.sessions_used += 1
            locked.save(update_fields=["sessions_used"])
            self.sessions_used = locked.sessions_used
        return True


class Exercise(models.Model):
    class Muscle(models.TextChoices):
        CHEST = "chest", _("Chest")
        BACK = "back", _("Back")
        SHOULDERS = "shoulders", _("Shoulders")
        ARMS = "arms", _("Arms")
        LEGS = "legs", _("Legs")
        GLUTES = "glutes", _("Glutes")
        CORE = "core", _("Core")
        FULL_BODY = "full_body", _("Full body")
        CARDIO = "cardio", _("Cardio")

    class Equipment(models.TextChoices):
        BARBELL = "barbell", _("Barbell")
        DUMBBELL = "dumbbell", _("Dumbbell")
        MACHINE = "machine", _("Machine")
        CABLE = "cable", _("Cable")
        BODYWEIGHT = "bodyweight", _("Bodyweight")
        KETTLEBELL = "kettlebell", _("Kettlebell")
        BAND = "band", _("Band")
        OTHER = "other", _("Other")

    # Null trainer = shared library entry shipped with Kondis.
    trainer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="exercises")
    slug = models.SlugField(max_length=80)
    name_tr = models.CharField(_("name (Turkish)"), max_length=100)
    name_en = models.CharField(_("name (English)"), max_length=100)
    muscle = models.CharField(_("muscle group"), max_length=16, choices=Muscle.choices)
    equipment = models.CharField(_("equipment"), max_length=16, choices=Equipment.choices)
    cue = models.CharField(_("coaching cue"), max_length=200, blank=True)
    # Movement pattern the program generator fills slots with; empty = never auto-picked.
    pattern = models.CharField(max_length=16, blank=True, db_index=True)
    # Comma-separated joints this exercise loads: knee, shoulder, lower_back.
    stresses = models.CharField(max_length=48, blank=True)

    class Meta:
        ordering = ["muscle", "name_en"]
        constraints = [models.UniqueConstraint(fields=["trainer", "slug"], name="uniq_exercise_slug_per_trainer")]

    def __str__(self) -> str:
        return self.name

    @property
    def name(self) -> str:
        return self.name_tr if translation.get_language() == "tr" else self.name_en

    @property
    def is_bodyweight(self) -> bool:
        return self.equipment == self.Equipment.BODYWEIGHT

    @classmethod
    def available_to(cls, user) -> models.QuerySet[Exercise]:
        return cls.objects.filter(models.Q(trainer__isnull=True) | models.Q(trainer=user))


class Program(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="programs")
    title = models.CharField(_("title"), max_length=100)
    notes = models.TextField(_("notes for the client"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    # Inputs used by the program generator, so a different version can be made later.
    generator = models.JSONField(null=True, blank=True, editable=False)
    variant = models.PositiveSmallIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "-created_at"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs) -> None:
        with transaction.atomic():
            super().save(*args, **kwargs)
            if self.is_active:
                Program.objects.filter(client=self.client, is_active=True).exclude(pk=self.pk).update(is_active=False)

    def get_absolute_url(self) -> str:
        return reverse("coaching:program_builder", args=[self.pk])

    def suggested_day(self, today: date | None = None) -> ProgramDay | None:
        """Today's weekday plan if there is one, otherwise the day after the last one trained."""
        today = today or timezone.localdate()
        days = list(self.days.all())
        if not days:
            return None
        for day in days:
            if day.weekday == today.weekday():
                return day
        last = self.client.workouts.filter(day__program=self).order_by("-performed_on", "-created_at").first()
        if last and last.day in days:
            return days[(days.index(last.day) + 1) % len(days)]
        return days[0]


class ProgramDay(models.Model):
    class Weekday(models.IntegerChoices):
        MON = 0, _("Monday")
        TUE = 1, _("Tuesday")
        WED = 2, _("Wednesday")
        THU = 3, _("Thursday")
        FRI = 4, _("Friday")
        SAT = 5, _("Saturday")
        SUN = 6, _("Sunday")

    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="days")
    title = models.CharField(_("day title"), max_length=60)
    weekday = models.PositiveSmallIntegerField(_("weekday"), choices=Weekday.choices, null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self) -> str:
        return self.title


class ProgramItem(models.Model):
    day = models.ForeignKey(ProgramDay, on_delete=models.CASCADE, related_name="items")
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="+")
    sets = models.PositiveSmallIntegerField(_("sets"), default=3)
    reps = models.CharField(_("reps"), max_length=16, default="8-10", help_text=_("e.g. 5, 8-10, 30 sec"))
    target_weight = models.DecimalField(_("weight (kg)"), max_digits=6, decimal_places=2, null=True, blank=True)
    rest_seconds = models.PositiveSmallIntegerField(_("rest (sec)"), default=90)
    note = models.CharField(_("note"), max_length=160, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self) -> str:
        return f"{self.exercise} {self.sets}x{self.reps}"


class Workout(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="workouts")
    day = models.ForeignKey(ProgramDay, on_delete=models.SET_NULL, null=True, blank=True, related_name="workouts")
    performed_on = models.DateField(_("date"), default=date.today)
    body_weight = models.DecimalField(_("body weight (kg)"), max_digits=5, decimal_places=1, null=True, blank=True)
    note = models.CharField(_("how did it go?"), max_length=300, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-performed_on", "-created_at"]

    def __str__(self) -> str:
        return f"{self.client} {self.performed_on}"

    @property
    def title(self) -> str:
        return self.day.title if self.day else str(_("Free session"))

    @property
    def is_finished(self) -> bool:
        return self.finished_at is not None

    @property
    def volume(self) -> Decimal:
        return sum((s.weight * s.reps for s in self.sets.all()), Decimal("0"))


class SetEntry(models.Model):
    workout = models.ForeignKey(Workout, on_delete=models.CASCADE, related_name="sets")
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="+")
    item = models.ForeignKey(ProgramItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    set_number = models.PositiveSmallIntegerField()
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    reps = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["exercise_id", "set_number"]

    def __str__(self) -> str:
        return f"{self.exercise} {self.weight}x{self.reps}"

    @property
    def estimated_1rm(self) -> Decimal:
        from .services import epley_1rm

        return epley_1rm(self.weight, self.reps)
