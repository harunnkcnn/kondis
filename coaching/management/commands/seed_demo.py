"""Fill an empty instance with a believable coach, clients and three weeks of training."""

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from coaching.models import Client, Membership, SetEntry, Workout
from coaching.services import create_program_from_template

CLIENTS = [
    ("Elif Yıldız", "fat_loss", "full_body", 68.4, -0.15, "12 PT seansı", 12, 9),
    ("Mert Kaya", "strength", "upper_lower", 82.0, 0.05, "3 aylık üyelik", None, 0),
    ("Zeynep Arslan", "muscle", "push_pull_legs", 57.2, 0.04, "8 PT seansı", 8, 7),
    ("Burak Demir", "general", "full_body", 91.5, -0.2, "1 aylık üyelik", None, 0),
    ("Selin Aydın", "mobility", "full_body", 61.0, 0.0, "10 PT seansı", 10, 3),
]


class Command(BaseCommand):
    help = "Create a demo coach (demo / kondis-demo-2026) with clients, programs and logged workouts."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="kondis-demo-2026")
        parser.add_argument("--seed", type=int, default=7)
        parser.add_argument("--if-empty", action="store_true", help="Do nothing when the demo user already exists.")

    @transaction.atomic
    def handle(self, *args, **opts):
        rng = random.Random(opts["seed"])
        User = get_user_model()
        if User.objects.filter(username="demo").exists():
            if opts["if_empty"]:
                self.stdout.write("Demo data already present, skipping.")
                return
            raise CommandError("A 'demo' user already exists.")
        coach = User.objects.create_user("demo", password=opts["password"], first_name="Harun", last_name="Koç")
        today = timezone.localdate()

        for i, (name, goal, template, weight, drift, package, total, used) in enumerate(CLIENTS):
            client = Client.objects.create(
                trainer=coach,
                full_name=name,
                phone=f"+90 555 010 {10 + i:02d} {20 + i:02d}",
                goal=goal,
                target_weight=Decimal(str(round(weight - 4, 1))) if drift < 0 else None,
            )
            ends = today + timedelta(days=[4, 40, 12, -2, 25][i])
            Membership.objects.create(
                client=client,
                package_name=package,
                starts_on=ends - timedelta(days=60),
                ends_on=ends,
                sessions_total=total,
                sessions_used=used,
                price=Decimal(["9600", "4500", "6800", "1500", "8000"][i]),
            )
            program = create_program_from_template(client, template)
            days = list(program.days.prefetch_related("items__exercise"))
            if i == 3:
                continue  # Burak has gone quiet: no workouts in the last weeks.
            base = {item.exercise_id: rng.choice([20, 30, 40, 50, 60, 70]) for d in days for item in d.items.all()}
            session = 0
            for back in range(20, -1, -1):
                date = today - timedelta(days=back)
                if date.weekday() not in {d.weekday for d in days}:
                    continue
                day = next(d for d in days if d.weekday == date.weekday())
                session += 1
                workout = Workout.objects.create(
                    client=client,
                    day=day,
                    performed_on=date,
                    body_weight=Decimal(str(round(weight + drift * session, 1))),
                    finished_at=None if back == 0 and i == 0 else timezone.now(),
                    note=rng.choice(["", "", "Sol omuz biraz hassastı.", "Çok iyi hissettim!", "Uykusuzdum, tempoyu düşürdüm."]),
                )
                for item in day.items.all():
                    load = Decimal(base[item.exercise_id] + session * 2.5) if not item.exercise.is_bodyweight else Decimal("0")
                    for n in range(1, item.sets + 1):
                        SetEntry.objects.create(
                            workout=workout,
                            exercise=item.exercise,
                            item=item,
                            set_number=n,
                            weight=load,
                            reps=rng.choice([6, 8, 8, 10, 12]),
                        )
        self.stdout.write(self.style.SUCCESS("Demo ready. Sign in as demo / " + opts["password"]))
