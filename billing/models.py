from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Subscription(models.Model):
    """A coach's access to the hosted service. Only enforced when KONDIS_HOSTED is on."""

    class Status(models.TextChoices):
        TRIAL = "trial", _("Free trial")
        ACTIVE = "active", _("Active")
        CANCELED = "canceled", _("Canceled")

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription")
    status = models.CharField(_("status"), max_length=12, choices=Status.choices, default=Status.TRIAL)
    gym_name = models.CharField(_("gym or studio"), max_length=120, blank=True)
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    paid_until = models.DateTimeField(_("access until"))
    note = models.CharField(_("note"), max_length=200, blank=True, help_text=_("Payment reference, invoice number..."))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["paid_until"]

    def __str__(self) -> str:
        return f"{self.user} ({self.get_status_display()})"

    @classmethod
    def start_trial(cls, user, **fields) -> Subscription:
        days = settings.KONDIS_TRIAL_DAYS
        return cls.objects.create(user=user, status=cls.Status.TRIAL, paid_until=timezone.now() + timedelta(days=days), **fields)

    @property
    def has_access(self) -> bool:
        return self.status != self.Status.CANCELED and self.paid_until > timezone.now()

    @property
    def days_left(self) -> int:
        remaining = self.paid_until - timezone.now()
        return max(remaining.days + (1 if remaining.seconds else 0), 0)

    @property
    def is_trial(self) -> bool:
        return self.status == self.Status.TRIAL

    def extend(self, days: int) -> None:
        """Record a payment: access continues from today or from the current end, whichever is later."""
        start = max(self.paid_until, timezone.now())
        self.paid_until = start + timedelta(days=days)
        self.status = self.Status.ACTIVE
        self.save(update_fields=["paid_until", "status"])


def has_access(user) -> bool:
    """True when the hosted paywall should let this user in."""
    if not settings.KONDIS_HOSTED:
        return True
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    subscription = getattr(user, "subscription", None)
    return bool(subscription and subscription.has_access)
