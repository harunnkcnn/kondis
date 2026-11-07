from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from coaching.models import Client, Exercise, Membership, Program, ProgramDay, ProgramItem, SetEntry, Workout
from coaching.services import build_dashboard, create_program_from_template, epley_1rm, personal_records, previous_sets


class Base(TestCase):
    def setUp(self):
        User = get_user_model()
        self.coach = User.objects.create_user("coach", password="a-long-pass-123")
        self.other = User.objects.create_user("other", password="a-long-pass-123")
        self.client_obj = Client.objects.create(trainer=self.coach, full_name="Elif Yıldız", phone="+90 555 000 00 00")
        self.today = timezone.localdate()
        self.squat = Exercise.objects.get(slug="back-squat", trainer__isnull=True)
        self.plank = Exercise.objects.get(slug="plank", trainer__isnull=True)


class EpleyTests(TestCase):
    def test_single_rep_is_the_weight(self):
        self.assertEqual(epley_1rm(100, 1), Decimal("100.0"))

    def test_formula(self):
        self.assertEqual(epley_1rm(100, 5), Decimal("116.7"))

    def test_zero_load_or_reps(self):
        self.assertEqual(epley_1rm(0, 10), Decimal("0"))
        self.assertEqual(epley_1rm(80, 0), Decimal("0"))


class LibraryTests(TestCase):
    def test_library_is_loaded_in_both_languages(self):
        library = Exercise.objects.filter(trainer__isnull=True)
        self.assertGreaterEqual(library.count(), 50)
        self.assertFalse(library.filter(name_tr="").exists())
        self.assertFalse(library.filter(name_en="").exists())

    def test_every_template_exercise_exists(self):
        from coaching.services import TEMPLATES

        slugs = {slug for spec in TEMPLATES.values() for _, _, items in spec["days"] for slug, _, _ in items}
        found = set(Exercise.objects.filter(trainer__isnull=True, slug__in=slugs).values_list("slug", flat=True))
        self.assertEqual(slugs, found)


class MembershipTests(Base):
    def make(self, **kwargs):
        defaults = {"package_name": "12 PT", "starts_on": self.today - timedelta(days=10), "ends_on": self.today + timedelta(days=30)}
        defaults.update(kwargs)
        return Membership.objects.create(client=self.client_obj, **defaults)

    def test_statuses(self):
        self.assertEqual(self.make().status(), Membership.Status.ACTIVE)
        self.assertEqual(self.make(ends_on=self.today + timedelta(days=3)).status(), Membership.Status.EXPIRING)
        self.assertEqual(self.make(ends_on=self.today - timedelta(days=1)).status(), Membership.Status.EXPIRED)
        self.assertEqual(self.make(sessions_total=10, sessions_used=10).status(), Membership.Status.USED_UP)
        self.assertEqual(self.make(sessions_total=10, sessions_used=9).status(), Membership.Status.EXPIRING)
        self.assertEqual(self.make(starts_on=self.today + timedelta(days=2)).status(), Membership.Status.UPCOMING)

    def test_use_session_stops_at_limit(self):
        m = self.make(sessions_total=1)
        self.assertTrue(m.use_session())
        self.assertFalse(m.use_session())
        m.refresh_from_db()
        self.assertEqual(m.sessions_used, 1)

    def test_unlimited_package_never_runs_out(self):
        m = self.make(sessions_total=None)
        for _ in range(5):
            self.assertTrue(m.use_session())
        self.assertIsNone(m.sessions_left)


class ProgramTests(Base):
    def test_only_one_active_program(self):
        first = Program.objects.create(client=self.client_obj, title="One")
        second = Program.objects.create(client=self.client_obj, title="Two")
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(self.client_obj.active_program, second)

    def test_template_creates_days_and_items(self):
        program = create_program_from_template(self.client_obj, "upper_lower")
        self.assertEqual(program.days.count(), 4)
        self.assertTrue(all(day.items.exists() for day in program.days.all()))

    def test_suggested_day_prefers_weekday_then_rotation(self):
        program = Program.objects.create(client=self.client_obj, title="Rotation")
        a = ProgramDay.objects.create(program=program, title="A", order=0)
        b = ProgramDay.objects.create(program=program, title="B", order=1)
        self.assertEqual(program.suggested_day(), a)
        Workout.objects.create(client=self.client_obj, day=a, performed_on=self.today - timedelta(days=1))
        self.assertEqual(program.suggested_day(), b)
        b.weekday = self.today.weekday()
        b.save()
        a.weekday = (self.today.weekday() + 1) % 7
        a.save()
        self.assertEqual(program.suggested_day(), b)


class RecordsTests(Base):
    def test_best_set_and_previous_sets(self):
        old = Workout.objects.create(client=self.client_obj, performed_on=self.today - timedelta(days=3))
        SetEntry.objects.create(workout=old, exercise=self.squat, set_number=1, weight=80, reps=5)
        new = Workout.objects.create(client=self.client_obj, performed_on=self.today)
        SetEntry.objects.create(workout=new, exercise=self.squat, set_number=1, weight=90, reps=3)
        SetEntry.objects.create(workout=new, exercise=self.plank, set_number=1, weight=0, reps=45)

        records = {r.exercise.slug: r for r in personal_records(self.client_obj)}
        self.assertEqual(records["back-squat"].best_weight, Decimal("90"))
        self.assertEqual(records["plank"].best_reps, 45)
        self.assertEqual([s.weight for s in previous_sets(self.client_obj, self.squat, before=new)], [Decimal("80")])


class DashboardTests(Base):
    def test_quiet_and_expiring(self):
        Membership.objects.create(
            client=self.client_obj, package_name="1 ay", starts_on=self.today - timedelta(days=28), ends_on=self.today + timedelta(days=2)
        )
        board = build_dashboard(self.coach)
        self.assertEqual(board.active_clients, 1)
        self.assertIn(self.client_obj, board.quiet_clients)
        self.assertEqual(len(board.expiring), 1)
        Workout.objects.create(client=self.client_obj, performed_on=self.today)
        board = build_dashboard(self.coach)
        self.assertNotIn(self.client_obj, board.quiet_clients)
        self.assertEqual(len(board.trained_today), 1)

    def test_other_coaches_data_is_not_counted(self):
        Client.objects.create(trainer=self.other, full_name="Someone else")
        self.assertEqual(build_dashboard(self.coach).active_clients, 1)


class TrainerAccessTests(Base):
    def test_login_required(self):
        for name in ["coaching:dashboard", "coaching:client_list", "coaching:exercise_list"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("login"), response["Location"])

    def test_pages_render_for_owner(self):
        self.client.force_login(self.coach)
        program = create_program_from_template(self.client_obj, "full_body")
        for url in [
            reverse("coaching:dashboard"),
            reverse("coaching:client_list"),
            reverse("coaching:client_detail", args=[self.client_obj.pk]),
            reverse("coaching:program_builder", args=[program.pk]),
            reverse("coaching:exercise_list"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_cannot_open_another_coaches_client(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("coaching:client_detail", args=[self.client_obj.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("coaching:client_rotate_link", args=[self.client_obj.pk])).status_code, 404)

    def test_create_client_assigns_owner(self):
        self.client.force_login(self.coach)
        response = self.client.post(
            reverse("coaching:client_create"),
            {
                "full_name": "Mert Kaya",
                "goal": "strength",
                "level": "beginner",
                "days_per_week": "3",
                "session_minutes": "60",
                "equipment": "gym",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Client.objects.get(full_name="Mert Kaya").trainer, self.coach)

    def test_rotating_link_invalidates_old_one(self):
        self.client.force_login(self.coach)
        old = self.client_obj.access_token
        self.client.post(reverse("coaching:client_rotate_link", args=[self.client_obj.pk]))
        self.client_obj.refresh_from_db()
        self.assertNotEqual(old, self.client_obj.access_token)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("portal:home", args=[old])).status_code, 404)

    def test_add_program_item_via_htmx(self):
        self.client.force_login(self.coach)
        program = Program.objects.create(client=self.client_obj, title="P")
        day = ProgramDay.objects.create(program=program, title="A")
        response = self.client.post(
            reverse("coaching:program_item_add", args=[day.pk]),
            {"exercise": self.squat.pk, "sets": 4, "reps": "5", "rest_seconds": 120},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(day.items.get().sets, 4)


class PortalTests(Base):
    def setUp(self):
        super().setUp()
        self.program = Program.objects.create(client=self.client_obj, title="P")
        self.day = ProgramDay.objects.create(program=self.program, title="Legs")
        self.item = ProgramItem.objects.create(day=self.day, exercise=self.squat, sets=3, reps="5")
        self.token = self.client_obj.access_token

    def test_home_is_private_and_unindexed(self):
        response = self.client.get(reverse("portal:home", args=[self.token]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertContains(response, "Legs")

    def test_unknown_or_inactive_token_is_404(self):
        self.assertEqual(self.client.get(reverse("portal:home", args=["nope"])).status_code, 404)
        self.client_obj.is_active = False
        self.client_obj.save()
        self.assertEqual(self.client.get(reverse("portal:home", args=[self.token])).status_code, 404)

    def test_full_workout_flow(self):
        response = self.client.post(reverse("portal:start", args=[self.token, self.day.pk]))
        workout = Workout.objects.get()
        self.assertRedirects(response, reverse("portal:workout", args=[self.token, workout.pk]))

        add = reverse("portal:add_set", args=[self.token, workout.pk])
        for reps in (5, 5):
            self.assertEqual(
                self.client.post(add, {"exercise": self.squat.pk, "item": self.item.pk, "weight": "100", "reps": reps}).status_code, 200
            )
        self.assertEqual(list(workout.sets.values_list("set_number", flat=True)), [1, 2])

        self.client.post(reverse("portal:finish", args=[self.token, workout.pk]), {"body_weight": "70.5", "note": "İyi"})
        workout.refresh_from_db()
        self.assertTrue(workout.is_finished)
        self.assertEqual(workout.body_weight, Decimal("70.5"))
        self.assertEqual(self.client.post(add, {"exercise": self.squat.pk, "reps": 5}).status_code, 409)
        self.assertEqual(self.client.get(reverse("portal:summary", args=[self.token, workout.pk])).status_code, 200)

    def test_invalid_set_is_rejected(self):
        workout = Workout.objects.create(client=self.client_obj, day=self.day)
        add = reverse("portal:add_set", args=[self.token, workout.pk])
        self.assertEqual(self.client.post(add, {"exercise": self.squat.pk, "reps": 0}).status_code, 422)
        self.assertEqual(self.client.post(add, {"exercise": self.squat.pk, "reps": 5, "weight": "-5"}).status_code, 422)

    def test_cannot_touch_another_clients_workout(self):
        stranger = Client.objects.create(trainer=self.coach, full_name="Mert")
        theirs = Workout.objects.create(client=stranger)
        add = reverse("portal:add_set", args=[self.token, theirs.pk])
        self.assertEqual(self.client.post(add, {"exercise": self.squat.pk, "reps": 5}).status_code, 404)

    def test_cannot_log_another_coaches_private_exercise(self):
        private = Exercise.objects.create(
            trainer=self.other, slug="secret", name_tr="Gizli", name_en="Secret", muscle="core", equipment="other"
        )
        workout = Workout.objects.create(client=self.client_obj, day=self.day)
        add = reverse("portal:add_set", args=[self.token, workout.pk])
        self.assertEqual(self.client.post(add, {"exercise": private.pk, "reps": 5}).status_code, 404)

    def test_csrf_is_enforced_on_portal(self):
        from django.test import Client as HttpClient

        strict = HttpClient(enforce_csrf_checks=True)
        response = strict.post(reverse("portal:start", args=[self.token, self.day.pk]))
        self.assertEqual(response.status_code, 403)


class OpsTests(TestCase):
    def test_healthz_ignores_allowed_hosts(self):
        response = self.client.get("/healthz/", HTTP_HOST="10.0.0.7:8000")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_unknown_host_is_still_rejected_elsewhere(self):
        self.assertEqual(self.client.get("/login/", HTTP_HOST="evil.example").status_code, 400)


class DemoModeTests(TestCase):
    def test_seed_is_idempotent_with_if_empty(self):
        from django.core.management import call_command

        call_command("seed_demo", verbosity=0)
        call_command("seed_demo", "--if-empty", verbosity=0)
        self.assertEqual(Client.objects.filter(trainer__username="demo").count(), 5)

    def test_login_shows_demo_shortcuts_only_in_demo_mode(self):
        from django.core.management import call_command

        call_command("seed_demo", verbosity=0)
        self.assertNotContains(self.client.get(reverse("login")), "kondis-demo-2026")
        with self.settings(KONDIS_DEMO=True):
            response = self.client.get(reverse("login"))
            self.assertContains(response, "kondis-demo-2026")
            self.assertContains(response, response.context["demo_portal"])
            self.client.post(reverse("login"), {"username": "demo", "password": "kondis-demo-2026"})
            self.assertContains(self.client.get(reverse("coaching:dashboard")), "demo-note")
