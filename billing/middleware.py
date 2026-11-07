from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse

from .models import has_access

# Paths a coach without an active subscription can still reach.
OPEN_PREFIXES = ("/login/", "/logout/", "/signup/", "/subscription/", "/i18n/", "/admin/", "/static/", "/healthz/")


class PaywallMiddleware:
    """Hosted mode only: after the trial, coaches land on the subscription page and
    their clients' workout links show a short notice instead of the program."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.KONDIS_HOSTED or request.path.startswith(OPEN_PREFIXES):
            return self.get_response(request)

        if request.path.startswith("/c/"):
            return self.get_response(request)  # checked per client in the portal view

        if request.user.is_authenticated and not has_access(request.user):
            return redirect(reverse("billing:subscription"))
        return self.get_response(request)


def portal_paused_response(request, client):
    return render(request, "billing/portal_paused.html", {"client": client}, status=402)
