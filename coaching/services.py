"""Training logic kept free of HTTP so it can be tested on its own."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from .models import Client, Exercise, Membership, Program, ProgramDay, ProgramItem, SetEntry, Workout

QUANT = Decimal("0.1")


def epley_1rm(weight: Decimal | float | int, reps: int) -> Decimal:
    """Estimated one-rep max (Epley). A single rep is its own max; zero load stays zero."""
    weight = Decimal(str(weight))
    if reps <= 0 or weight <= 0:
        return Decimal("0")
    if reps == 1:
        return weight.quantize(QUANT, rounding=ROUND_HALF_UP)
    return (weight * (1 + Decimal(reps) / 30)).quantize(QUANT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PersonalRecord:
    exercise: Exercise
    best_weight: Decimal
    best_reps: int
    estimated_1rm: Decimal
    performed_on: date


def personal_records(client: Client, limit: int | None = None) -> list[PersonalRecord]:
    """Best estimated 1RM per exercise; bodyweight moves ranked by reps."""
    best: dict[int, tuple[SetEntry, Decimal]] = {}
    entries = SetEntry.objects.filter(workout__client=client).select_related("exercise", "workout")
    for entry in entries:
        score = Decimal(entry.reps) if entry.exercise.is_bodyweight else entry.estimated_1rm
        current = best.get(entry.exercise_id)
        if current is None or score > current[1]:
            best[entry.exercise_id] = (entry, score)
    records = [
        PersonalRecord(
            exercise=e.exercise,
            best_weight=e.weight,
            best_reps=e.reps,
            estimated_1rm=e.estimated_1rm,
            performed_on=e.workout.performed_on,
        )
        for e, _ in best.values()
    ]
    records.sort(key=lambda r: r.performed_on, reverse=True)
    return records[:limit] if limit else records


def previous_sets(client: Client, exercise: Exercise, before: Workout | None = None) -> list[SetEntry]:
    """Sets from the last earlier workout that included this exercise."""
    qs = Workout.objects.filter(client=client, sets__exercise=exercise)
    if before is not None:
        qs = qs.exclude(pk=before.pk).filter(
            Q(performed_on__lt=before.performed_on) | Q(performed_on=before.performed_on, created_at__lt=before.created_at)
        )
    last = qs.order_by("-performed_on", "-created_at").distinct().first()
    if last is None:
        return []
    return list(last.sets.filter(exercise=exercise).order_by("set_number"))


@dataclass(frozen=True)
class Dashboard:
    trained_today: list[Workout]
    expiring: list[Membership]
    quiet_clients: list[Client]
    active_clients: int
    workouts_this_week: int


def build_dashboard(trainer, today: date | None = None, quiet_after_days: int = 7) -> Dashboard:
    today = today or timezone.localdate()
    clients = Client.objects.filter(trainer=trainer, is_active=True)
    trained_today = list(Workout.objects.filter(client__in=clients, performed_on=today).select_related("client", "day"))
    latest_memberships = Membership.objects.filter(client__in=clients).select_related("client").order_by("client_id", "-ends_on")
    seen: set[int] = set()
    expiring: list[Membership] = []
    for membership in latest_memberships:
        if membership.client_id in seen:
            continue
        seen.add(membership.client_id)
        if membership.status(today) in {Membership.Status.EXPIRING, Membership.Status.EXPIRED, Membership.Status.USED_UP}:
            expiring.append(membership)
    expiring.sort(key=lambda m: m.ends_on)

    cutoff = today - timedelta(days=quiet_after_days)
    quiet = list(
        clients.annotate(last_seen=Max("workouts__performed_on"))
        .filter(Q(last_seen__lt=cutoff) | Q(last_seen__isnull=True))
        .order_by("last_seen")
    )
    week_start = today - timedelta(days=today.weekday())
    return Dashboard(
        trained_today=trained_today,
        expiring=expiring,
        quiet_clients=quiet,
        active_clients=clients.count(),
        workouts_this_week=Workout.objects.filter(client__in=clients, performed_on__gte=week_start).count(),
    )


# Starter programs a trainer can load and then edit. Slugs refer to the shared library.
TEMPLATES: dict[str, dict] = {
    "full_body": {
        "title": "Full Body 3x",
        "days": [
            ("A", 0, [("back-squat", 3, "5-8"), ("bench-press", 3, "6-8"), ("seated-cable-row", 3, "8-10"), ("plank", 3, "30-45 sn")]),
            (
                "B",
                2,
                [("romanian-deadlift", 3, "6-8"), ("overhead-press", 3, "6-8"), ("lat-pulldown", 3, "8-12"), ("walking-lunge", 2, "10")],
            ),
            (
                "C",
                4,
                [
                    ("leg-press", 3, "10-12"),
                    ("incline-dumbbell-press", 3, "8-10"),
                    ("dumbbell-row", 3, "10"),
                    ("hanging-knee-raise", 3, "12"),
                ],
            ),
        ],
    },
    "upper_lower": {
        "title": "Upper / Lower",
        "days": [
            ("Upper A", 0, [("bench-press", 4, "5-6"), ("barbell-row", 4, "6-8"), ("overhead-press", 3, "8"), ("biceps-curl", 3, "10-12")]),
            (
                "Lower A",
                1,
                [("back-squat", 4, "5"), ("romanian-deadlift", 3, "8"), ("leg-curl", 3, "10-12"), ("standing-calf-raise", 3, "12-15")],
            ),
            (
                "Upper B",
                3,
                [
                    ("incline-dumbbell-press", 3, "8-10"),
                    ("pull-up", 3, "6-10"),
                    ("lateral-raise", 3, "12-15"),
                    ("triceps-pushdown", 3, "10-12"),
                ],
            ),
            ("Lower B", 4, [("deadlift", 3, "3-5"), ("leg-press", 3, "10"), ("hip-thrust", 3, "8-10"), ("plank", 3, "45 sn")]),
        ],
    },
    "push_pull_legs": {
        "title": "Push / Pull / Legs",
        "days": [
            (
                "Push",
                0,
                [("bench-press", 4, "6-8"), ("overhead-press", 3, "8"), ("incline-dumbbell-press", 3, "10"), ("triceps-pushdown", 3, "12")],
            ),
            ("Pull", 2, [("deadlift", 3, "5"), ("pull-up", 3, "8"), ("seated-cable-row", 3, "10"), ("biceps-curl", 3, "12")]),
            (
                "Legs",
                4,
                [("back-squat", 4, "6-8"), ("romanian-deadlift", 3, "8-10"), ("leg-extension", 3, "12"), ("standing-calf-raise", 4, "15")],
            ),
        ],
    },
}


@transaction.atomic
def create_program_from_template(client: Client, key: str) -> Program:
    spec = TEMPLATES[key]
    library = {e.slug: e for e in Exercise.objects.filter(trainer__isnull=True)}
    program = Program.objects.create(client=client, title=spec["title"], is_active=True)
    for day_order, (title, weekday, items) in enumerate(spec["days"]):
        day = ProgramDay.objects.create(program=program, title=title, weekday=weekday, order=day_order)
        for item_order, (slug, sets, reps) in enumerate(items):
            exercise = library.get(slug)
            if exercise is None:
                continue
            ProgramItem.objects.create(day=day, exercise=exercise, sets=sets, reps=reps, order=item_order)
    return program
