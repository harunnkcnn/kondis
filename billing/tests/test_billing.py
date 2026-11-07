from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from billing.models import Subscription, has_access
from coaching.models import Client

SIGNUP = {
    "full_name": "Ayşe Demir",
    "gym_name": "Demir PT Stüdyo",
    "email": "Ayse@Example.com",
    "phone": "+90 555 000 11 22",
    "password": "kare-mavi-plaka-42",
    "accept": "on",
}


@override_settings(KONDIS_HOSTED=True, KONDIS_TRIAL_DAYS=7)
class HostedTests(TestCase):
    def test_signup_starts_a_seven_day_trial_and_logs_in(self):
        response = self.client.post(reverse("billing:signup"), SIGNUP)
        self.assertRedirects(response, reverse("coaching:dashboard"))
        user = get_user_model().objects.get(username="ayse@example.com")
        sub = user.subscription
        self.assertEqual(sub.status, Subscription.Status.TRIAL)
        self.assertEqual(sub.days_left, 7)
        self.assertEqual(sub.gym_name, "Demir PT Stüdyo")
        dashboard = self.client.get(reverse("coaching:dashboard"))
        self.assertContains(dashboard, "trial-note")

    def test_duplicate_email_and_weak_password_are_rejected(self):
        self.client.post(reverse("billing:signup"), SIGNUP)
        self.client.logout()
        response = self.client.post(reverse("billing:signup"), {**SIGNUP, "email": "ayse@example.com"})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("billing:signup"), {**SIGNUP, "email": "new@example.com", "password": "123"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_terms_must_be_accepted(self):
        data = {k: v for k, v in SIGNUP.items() if k != "accept"}
        self.client.post(reverse("billing:signup"), data)
        self.assertFalse(get_user_model().objects.exists())

    def expire(self, user):
        user.subscription.paid_until = timezone.now() - timedelta(minutes=1)
        user.subscription.save()

    def test_expired_trial_hits_the_paywall_but_data_is_kept(self):
        self.client.post(reverse("billing:signup"), SIGNUP)
        user = get_user_model().objects.get()
        Client.objects.create(trainer=user, full_name="Mert")
        self.expire(user)
        self.assertRedirects(self.client.get(reverse("coaching:client_list")), reverse("billing:subscription"))
        self.assertEqual(self.client.get(reverse("billing:subscription")).status_code, 200)
        self.assertEqual(Client.objects.count(), 1)

    def test_clients_portal_pauses_and_resumes(self):
        self.client.post(reverse("billing:signup"), SIGNUP)
        user = get_user_model().objects.get()
        member = Client.objects.create(trainer=user, full_name="Mert")
        self.client.logout()
        url = reverse("portal:home", args=[member.access_token])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.expire(user)
        self.assertEqual(self.client.get(url).status_code, 402)
        user.subscription.extend(30)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_extend_counts_from_the_later_of_today_and_current_end(self):
        user = get_user_model().objects.create_user("c@example.com", password="x-long-pass-1")
        sub = Subscription.start_trial(user)
        sub.extend(30)
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.days_left, 37)
        sub.paid_until = timezone.now() - timedelta(days=10)
        sub.extend(30)
        self.assertEqual(sub.days_left, 30)

    def test_canceled_and_missing_subscriptions_have_no_access(self):
        user = get_user_model().objects.create_user("c@example.com", password="x-long-pass-1")
        self.assertFalse(has_access(user))
        sub = Subscription.start_trial(user)
        user.refresh_from_db()
        self.assertTrue(has_access(user))
        sub.status = Subscription.Status.CANCELED
        sub.save()
        user.refresh_from_db()
        self.assertFalse(has_access(user))

    def test_staff_is_never_blocked(self):
        admin = get_user_model().objects.create_user("owner", password="x-long-pass-1", is_staff=True)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("coaching:dashboard")).status_code, 200)

    def test_login_page_offers_signup(self):
        self.assertContains(self.client.get(reverse("login")), reverse("billing:signup"))


class SelfHostedTests(TestCase):
    def test_no_signup_and_no_paywall_when_not_hosted(self):
        self.assertEqual(self.client.get("/signup/").status_code, 404)
        user = get_user_model().objects.create_user("coach", password="x-long-pass-1")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("coaching:dashboard")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("login"), follow=True), "/signup/")
