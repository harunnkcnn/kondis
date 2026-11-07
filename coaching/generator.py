"""Rule-based program generator.

Builds a weekly program from a client's goal, level, days per week, session length,
equipment and the joints to protect. Exercise choice is seeded per client and per
variant, so two clients with the same profile get different programs and a coach can
ask for another version at any time. No external service is involved.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from .models import Client, Exercise, Program, ProgramDay, ProgramItem

COMPOUND = {"squat", "lunge", "hinge", "h_push", "v_push", "h_pull", "v_pull", "glute", "carry"}
TIMED = {"plank", "side-plank", "wall-sit"}
PER_SIDE = {"dead-bug", "bird-dog", "single-leg-glute-bridge", "single-leg-rdl", "side-plank"}
STRONG_BODYWEIGHT = {"pull-up", "chin-up", "dip"}
# Fill compound slots but are dosed like accessories.
ACCESSORY_LIKE = {"cable-kickback", "band-lateral-walk", "glute-bridge", "single-leg-glute-bridge", "back-extension"}
LOADED_EQUIPMENT = {"barbell", "dumbbell", "machine", "cable", "kettlebell"}

EQUIPMENT_ALLOWED = {
    Client.Equipment.GYM: None,  # everything
    Client.Equipment.DUMBBELLS: {"dumbbell", "kettlebell", "bodyweight", "band", "other"},
    Client.Equipment.HOME: {"bodyweight", "band", "other"},
}

# Slots per session type, most important first. A shorter session keeps the first N.
DAY_SLOTS: dict[str, list[str]] = {
    "full_a": ["squat", "h_push", "h_pull", "hinge", "iso_shoulder", "core", "iso_biceps", "calves"],
    "full_b": ["hinge", "v_push", "v_pull", "lunge", "iso_triceps", "core", "glute", "iso_shoulder"],
    "full_c": ["lunge", "h_push", "h_pull", "glute", "iso_shoulder", "core", "iso_biceps", "iso_triceps"],
    "upper_a": ["h_push", "h_pull", "v_push", "v_pull", "iso_shoulder", "iso_biceps", "iso_triceps", "core"],
    "upper_b": ["v_push", "v_pull", "h_push", "h_pull", "iso_chest", "iso_triceps", "iso_biceps", "iso_shoulder"],
    "lower_a": ["squat", "hinge", "lunge", "iso_ham", "calves", "core", "iso_quad", "glute"],
    "lower_b": ["hinge", "squat", "glute", "iso_quad", "calves", "core", "lunge", "iso_ham"],
    "push": ["h_push", "v_push", "h_push", "iso_shoulder", "iso_triceps", "iso_chest", "core", "iso_triceps"],
    "pull": ["v_pull", "h_pull", "hinge", "h_pull", "iso_shoulder", "iso_biceps", "core", "iso_biceps"],
    "legs": ["squat", "hinge", "lunge", "iso_quad", "iso_ham", "calves", "core", "glute"],
}

DAY_TITLES = {
    "full_a": lambda: _("Full body A"),
    "full_b": lambda: _("Full body B"),
    "full_c": lambda: _("Full body C"),
    "upper_a": lambda: _("Upper body A"),
    "upper_b": lambda: _("Upper body B"),
    "lower_a": lambda: _("Lower body A"),
    "lower_b": lambda: _("Lower body B"),
    "push": lambda: _("Push"),
    "pull": lambda: _("Pull"),
    "legs": lambda: _("Legs"),
}

WEEKDAYS = {2: [0, 3], 3: [0, 2, 4], 4: [0, 1, 3, 4], 5: [0, 1, 2, 4, 5], 6: [0, 1, 2, 3, 4, 5]}
EXERCISES_PER_SESSION = {30: 4, 45: 5, 60: 6, 75: 7, 90: 8}

# (sets, reps, rest seconds) for the day's first compound, other compounds, and isolation work.
DOSE = {
    Client.Goal.STRENGTH: {"main": (5, "3-5", 180), "compound": (4, "5-6", 150), "iso": (3, "8-10", 90)},
    Client.Goal.MUSCLE: {"main": (4, "6-8", 120), "compound": (3, "8-12", 90), "iso": (3, "10-15", 60)},
    Client.Goal.FAT_LOSS: {"main": (3, "10-12", 75), "compound": (3, "12", 60), "iso": (2, "15", 45)},
    Client.Goal.MOBILITY: {"main": (3, "8-10", 75), "compound": (2, "10-12", 60), "iso": (2, "12-15", 45)},
    Client.Goal.GENERAL: {"main": (3, "6-8", 120), "compound": (3, "8-10", 90), "iso": (2, "12-15", 60)},
}


@dataclass
class Plan:
    goal: str = Client.Goal.GENERAL
    level: str = Client.Level.BEGINNER
    days_per_week: int = 3
    session_minutes: int = 60
    equipment: str = Client.Equipment.GYM
    limitations: list[str] = field(default_factory=list)

    @classmethod
    def for_client(cls, client: Client) -> Plan:
        return cls(
            goal=client.goal,
            level=client.level,
            days_per_week=client.days_per_week,
            session_minutes=client.session_minutes,
            equipment=client.equipment,
            limitations=client.limitation_list,
        )

    def normalized(self) -> Plan:
        days = min(max(int(self.days_per_week), 2), 6)
        minutes = min(EXERCISES_PER_SESSION, key=lambda m: abs(m - int(self.session_minutes)))
        return Plan(self.goal, self.level, days, minutes, self.equipment, sorted(set(self.limitations)))


def split_for(plan: Plan) -> list[str]:
    days = plan.days_per_week
    if days == 2:
        return ["full_a", "full_b"]
    if days == 3:
        if plan.level == Client.Level.ADVANCED and plan.goal in {Client.Goal.MUSCLE, Client.Goal.STRENGTH}:
            return ["push", "pull", "legs"]
        return ["full_a", "full_b", "full_c"]
    if days == 4:
        return ["upper_a", "lower_a", "upper_b", "lower_b"]
    if days == 5:
        return ["upper_a", "lower_a", "push", "pull", "legs"]
    return ["push", "pull", "legs", "push", "pull", "legs"]


def candidates(trainer, plan: Plan) -> dict[str, list[Exercise]]:
    allowed = EQUIPMENT_ALLOWED[plan.equipment]
    qs = Exercise.objects.filter(Q(trainer__isnull=True) | Q(trainer=trainer)).exclude(pattern="")
    if allowed is not None:
        qs = qs.filter(equipment__in=allowed)
    pool: dict[str, list[Exercise]] = {}
    for exercise in qs.order_by("slug"):
        stresses = set(filter(None, exercise.stresses.split(",")))
        if stresses & set(plan.limitations):
            continue
        pool.setdefault(exercise.pattern, []).append(exercise)
    return pool


def _weight(exercise: Exercise, plan: Plan, used_this_week: set[int], is_main: bool) -> float:
    weight = 1.0
    if exercise.pk in used_this_week:
        weight *= 0.08  # strongly prefer variety across the week
    loaded = exercise.equipment in LOADED_EQUIPMENT
    if plan.equipment == Client.Equipment.GYM and exercise.pattern not in {"core", "mobility", "conditioning"}:
        # In a full gym, bands and easy bodyweight variants are fallbacks, not first picks.
        if exercise.equipment == "band":
            weight *= 0.03
        elif exercise.equipment == "bodyweight" and not (exercise.slug in STRONG_BODYWEIGHT and plan.level != Client.Level.BEGINNER):
            weight *= 0.3
    if is_main and plan.goal in {Client.Goal.STRENGTH, Client.Goal.MUSCLE}:
        weight *= 3 if exercise.equipment == "barbell" else (2 if loaded else 0.1)
    if is_main and exercise.slug in ACCESSORY_LIKE:
        weight *= 0.05
    if plan.goal in {Client.Goal.FAT_LOSS, Client.Goal.MOBILITY} and exercise.equipment in {"barbell", "machine"}:
        weight *= 0.4
    if plan.level == Client.Level.BEGINNER:
        if exercise.equipment == "barbell":
            weight *= 0.5
        if exercise.slug in {"pull-up", "chin-up", "dip", "pike-push-up", "deadlift", "front-squat", "skull-crusher"}:
            weight *= 0.25
    return weight


def _dose(plan: Plan, exercise: Exercise, role: str) -> tuple[int, str, int]:
    if exercise.pattern == "mobility":
        return 2, "8/taraf" if plan_language_tr() else "8/side", 30
    if exercise.pattern == "conditioning":
        return 4, "30 sn" if plan_language_tr() else "30 sec", 30
    sets, reps, rest = DOSE[Client.Goal(plan.goal)][role]
    if exercise.pattern == "core" or exercise.slug in TIMED:
        sets, rest = 3, 45
        if exercise.slug in TIMED:
            reps = "30-45 sn" if plan_language_tr() else "30-45 sec"
        else:
            reps = "10-12"
    if exercise.slug in PER_SIDE and exercise.slug not in TIMED:
        reps = "8/taraf" if plan_language_tr() else "8/side"
    if exercise.pattern == "carry":
        reps = "30 m"
    if plan.level == Client.Level.BEGINNER:
        sets = max(sets - 1, 2)
    elif plan.level == Client.Level.ADVANCED and role == "main":
        sets += 1
    return sets, reps, rest


def plan_language_tr() -> bool:
    from django.utils.translation import get_language

    return (get_language() or "tr").startswith("tr")


@dataclass
class _Session:
    """One training day being filled slot by slot."""

    plan: Plan
    pool: dict[str, list[Exercise]]
    rng: random.Random
    used_this_week: set[int]
    items: list[dict] = field(default_factory=list)
    used_today: set[int] = field(default_factory=set)
    has_compound: bool = False

    def pick(self, pattern: str) -> bool:
        options = [e for e in self.pool.get(pattern, []) if e.pk not in self.used_today]
        if not options:
            return False
        is_main = pattern in COMPOUND and not self.has_compound
        weights = [_weight(e, self.plan, self.used_this_week, is_main) for e in options]
        exercise = self.rng.choices(options, weights=weights, k=1)[0]
        self.used_today.add(exercise.pk)
        self.used_this_week.add(exercise.pk)
        compound = pattern in COMPOUND and exercise.slug not in ACCESSORY_LIKE
        role = "main" if is_main and compound else ("compound" if compound else "iso")
        self.has_compound = self.has_compound or compound
        sets, reps, rest = _dose(self.plan, exercise, role)
        self.items.append({"exercise": exercise, "sets": sets, "reps": reps, "rest": rest, "role": role})
        return True

    def ordered(self) -> list[dict]:
        """Mobility first, then the main lift, other compounds, isolation, core and the finisher."""

        def rank(item: dict) -> int:
            pattern = item["exercise"].pattern
            if pattern == "mobility":
                return 0
            if pattern == "conditioning":
                return 5
            if pattern == "core":
                return 4
            return {"main": 1, "compound": 2, "iso": 3}[item["role"]]

        return sorted(self.items, key=rank)


def design(client: Client, plan: Plan, variant: int = 0) -> list[dict]:
    """Return the program as plain data: [{title, weekday, items: [{exercise, sets, reps, rest}]}]."""
    plan = plan.normalized()
    rng = random.Random(f"kondis:{client.pk}:{variant}:{asdict(plan)}")
    pool = candidates(client.trainer, plan)
    per_session = EXERCISES_PER_SESSION[plan.session_minutes]
    used_this_week: set[int] = set()
    week = []

    for day_key, weekday in zip(split_for(plan), WEEKDAYS[plan.days_per_week], strict=True):
        target, prefix, extras = per_session, [], []
        if plan.goal == Client.Goal.FAT_LOSS:
            target, extras = per_session - 1, ["conditioning"]
        elif plan.goal == Client.Goal.MOBILITY:
            target, prefix = per_session - 1, ["mobility"]

        session = _Session(plan, pool, rng, used_this_week)
        for pattern in prefix:
            session.pick(pattern)
        start = len(session.items)
        # Walk the slots in priority order; a slot with no safe option (equipment or a
        # protected joint) is skipped and the next one takes its place.
        for pattern in DAY_SLOTS[day_key]:
            if len(session.items) - start >= target:
                break
            session.pick(pattern)
        for pattern in extras:
            session.pick(pattern)
        week.append({"title": DAY_TITLES[day_key](), "weekday": weekday, "items": session.ordered()})
    return week


def summary(plan: Plan) -> str:
    plan = plan.normalized()
    parts = [
        str(Client.Goal(plan.goal).label),
        _("%(n)s days a week") % {"n": plan.days_per_week},
        _("%(n)s min sessions") % {"n": plan.session_minutes},
        str(Client.Level(plan.level).label),
        str(Client.Equipment(plan.equipment).label),
    ]
    if plan.limitations:
        protected = ", ".join(str(Client.Limitation(v).label) for v in plan.limitations)
        parts.append(_("protecting: %(areas)s") % {"areas": protected})
    return ". ".join(parts) + "."


PROGRESSION_NOTE = {
    Client.Goal.STRENGTH: lambda: _("When every set reaches the top of the rep range, add 2.5 kg to the main lifts."),
    Client.Goal.MUSCLE: lambda: _("When you hit the top of the rep range on all sets, go up one weight step next time."),
    Client.Goal.FAT_LOSS: lambda: _("Keep rests short. Once a session feels easy, add one round to the finisher."),
    Client.Goal.MOBILITY: lambda: _("Move slowly and without pain. Add load only when the full range feels easy."),
    Client.Goal.GENERAL: lambda: _("Leave one or two reps in reserve. Add weight when the last set feels easy."),
}


@transaction.atomic
def generate_program(client: Client, plan: Plan | None = None, variant: int = 0, title: str = "") -> Program:
    plan = (plan or Plan.for_client(client)).normalized()
    week = design(client, plan, variant)
    program = Program.objects.create(
        client=client,
        title=title or _("%(goal)s, %(n)s days") % {"goal": Client.Goal(plan.goal).label, "n": plan.days_per_week},
        notes=f"{summary(plan)} {PROGRESSION_NOTE[Client.Goal(plan.goal)]()}",
        is_active=True,
        generator=asdict(plan),
        variant=variant,
    )
    for order, day in enumerate(week):
        program_day = ProgramDay.objects.create(program=program, title=day["title"], weekday=day["weekday"], order=order)
        ProgramItem.objects.bulk_create(
            ProgramItem(day=program_day, exercise=i["exercise"], sets=i["sets"], reps=i["reps"], rest_seconds=i["rest"], order=n)
            for n, i in enumerate(day["items"])
        )
    return program


def generate_another_version(program: Program) -> Program:
    """A fresh variant with the same inputs; the previous program is kept but deactivated."""
    if not program.generator:
        raise ValueError("Program was not generated automatically.")
    plan = Plan(**program.generator)
    latest = program.client.programs.filter(generator__isnull=False).order_by("-variant").first()
    next_variant = (latest.variant if latest else program.variant) + 1
    return generate_program(program.client, plan, variant=next_variant)
