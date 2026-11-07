from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from coaching.generator import Plan, design, generate_another_version, generate_program, split_for
from coaching.models import Client, Program


def exercise_ids(week):
    return [[i["exercise"].pk for i in day["items"]] for day in week]


class GeneratorTests(TestCase):
    def setUp(self):
        translation.activate("tr")
        self.coach = get_user_model().objects.create_user("coach", password="a-long-pass-123")
        self.clients = [Client.objects.create(trainer=self.coach, full_name=f"Client {n}") for n in range(6)]

    def test_split_matches_days_per_week(self):
        for days in range(2, 7):
            week = design(self.clients[0], Plan(days_per_week=days))
            self.assertEqual(len(week), days)
            self.assertEqual(len({d["weekday"] for d in week}), days)

    def test_session_length_sets_exercise_count(self):
        short = design(self.clients[0], Plan(session_minutes=30))
        long = design(self.clients[0], Plan(session_minutes=75))
        self.assertTrue(all(len(d["items"]) == 4 for d in short))
        self.assertTrue(all(len(d["items"]) == 7 for d in long))

    def test_same_profile_different_clients_get_different_programs(self):
        plan = Plan(goal="muscle", level="intermediate", days_per_week=4)
        programs = {tuple(map(tuple, exercise_ids(design(c, plan)))) for c in self.clients}
        self.assertGreaterEqual(len(programs), 5)

    def test_deterministic_for_same_client_and_variant(self):
        plan = Plan(goal="strength", days_per_week=3)
        self.assertEqual(exercise_ids(design(self.clients[0], plan, 0)), exercise_ids(design(self.clients[0], plan, 0)))
        self.assertNotEqual(exercise_ids(design(self.clients[0], plan, 0)), exercise_ids(design(self.clients[0], plan, 1)))

    def test_no_duplicate_exercise_within_a_day(self):
        for client in self.clients:
            for day in design(client, Plan(days_per_week=6, session_minutes=90)):
                ids = [i["exercise"].pk for i in day["items"]]
                self.assertEqual(len(ids), len(set(ids)))

    def test_protected_joints_are_respected(self):
        plan = Plan(days_per_week=5, session_minutes=75, limitations=["knee", "lower_back"])
        for client in self.clients:
            for day in design(client, plan):
                for item in day["items"]:
                    stresses = set(item["exercise"].stresses.split(","))
                    self.assertFalse(stresses & {"knee", "lower_back"}, item["exercise"].slug)

    def test_equipment_is_respected(self):
        for equipment, allowed in [
            ("home", {"bodyweight", "band", "other"}),
            ("dumbbells", {"dumbbell", "kettlebell", "bodyweight", "band", "other"}),
        ]:
            for day in design(self.clients[1], Plan(equipment=equipment, days_per_week=4)):
                for item in day["items"]:
                    self.assertIn(item["exercise"].equipment, allowed)

    def test_home_program_still_fills_sessions(self):
        week = design(self.clients[2], Plan(goal="fat_loss", equipment="home", limitations=["knee"], session_minutes=45))
        for day in week:
            self.assertGreaterEqual(len(day["items"]), 4)
            self.assertEqual(day["items"][-1]["exercise"].pattern, "conditioning")

    def test_goal_shapes_the_dose(self):
        strength = design(self.clients[0], Plan(goal="strength", level="intermediate"))[0]["items"][0]
        fat_loss = design(self.clients[0], Plan(goal="fat_loss", level="intermediate"))[0]["items"][0]
        self.assertEqual((strength["reps"], strength["rest"]), ("3-5", 180))
        self.assertLess(fat_loss["rest"], strength["rest"])
        mobility = design(self.clients[0], Plan(goal="mobility"))[0]["items"][0]
        self.assertEqual(mobility["exercise"].pattern, "mobility")

    def test_advanced_muscle_three_days_uses_push_pull_legs(self):
        self.assertEqual(split_for(Plan(goal="muscle", level="advanced", days_per_week=3)), ["push", "pull", "legs"])
        self.assertEqual(split_for(Plan(goal="muscle", level="beginner", days_per_week=3))[0], "full_a")

    def test_generate_and_regenerate(self):
        client = self.clients[0]
        first = generate_program(client, Plan(goal="muscle", days_per_week=4))
        self.assertTrue(first.is_active)
        self.assertEqual(first.days.count(), 4)
        self.assertIn("4", first.notes)
        second = generate_another_version(first)
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(second.variant, 1)
        self.assertEqual(Program.objects.filter(client=client).count(), 2)


class GeneratorViewTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user("coach", password="a-long-pass-123")
        self.other = get_user_model().objects.create_user("other", password="a-long-pass-123")
        self.client_obj = Client.objects.create(trainer=self.coach, full_name="Deniz")
        self.client.force_login(self.coach)

    def post_auto(self, **extra):
        data = {
            "mode": "auto",
            "goal": "strength",
            "level": "intermediate",
            "equipment": "dumbbells",
            "days_per_week": "4",
            "session_minutes": "45",
            "limitations": ["shoulder"],
            "title": "",
            "notes": "",
        }
        data.update(extra)
        return self.client.post(reverse("coaching:program_create", args=[self.client_obj.pk]), data)

    def test_create_page_renders(self):
        self.assertEqual(self.client.get(reverse("coaching:program_create", args=[self.client_obj.pk])).status_code, 200)

    def test_auto_mode_saves_profile_and_generates(self):
        response = self.post_auto()
        program = Program.objects.get()
        self.assertRedirects(response, reverse("coaching:program_builder", args=[program.pk]))
        self.client_obj.refresh_from_db()
        self.assertEqual(
            (self.client_obj.days_per_week, self.client_obj.equipment, self.client_obj.limitations), (4, "dumbbells", "shoulder")
        )
        self.assertEqual(program.days.count(), 4)
        self.assertEqual(program.generator["limitations"], ["shoulder"])

    def test_regenerate_button(self):
        self.post_auto()
        program = Program.objects.get()
        response = self.client.post(reverse("coaching:program_regenerate", args=[program.pk]))
        self.assertEqual(Program.objects.count(), 2)
        self.assertRedirects(response, reverse("coaching:program_builder", args=[Program.objects.get(is_active=True).pk]))

    def test_regenerate_is_owner_only(self):
        self.post_auto()
        program = Program.objects.get()
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("coaching:program_regenerate", args=[program.pk])).status_code, 404)

    def test_empty_mode_needs_title(self):
        response = self.client.post(
            reverse("coaching:program_create", args=[self.client_obj.pk]),
            {"mode": "empty", "goal": "general", "level": "beginner", "equipment": "gym", "days_per_week": "3", "session_minutes": "60"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Program.objects.exists())

    def test_template_mode_still_works(self):
        self.client.post(
            reverse("coaching:program_create", args=[self.client_obj.pk]),
            {
                "mode": "template",
                "template": "upper_lower",
                "goal": "general",
                "level": "beginner",
                "equipment": "gym",
                "days_per_week": "3",
                "session_minutes": "60",
            },
        )
        self.assertEqual(Program.objects.get().days.count(), 4)
