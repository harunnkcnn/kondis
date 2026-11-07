from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model, login, password_validation
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from .models import Subscription


class SignupForm(forms.Form):
    full_name = forms.CharField(label=_("Your name"), max_length=120)
    gym_name = forms.CharField(label=_("Gym or studio"), max_length=120, required=False)
    email = forms.EmailField(label=_("Email"))
    phone = forms.CharField(label=_("Phone"), max_length=32, required=False, help_text=_("We use it only for your subscription."))
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput, help_text=_("At least 10 characters."))
    accept = forms.BooleanField(label=_("I accept the terms of use and privacy notice."))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(username__iexact=email).exists():
            raise forms.ValidationError(_("An account with this email already exists. Sign in instead."))
        return email

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("email"):
            candidate = get_user_model()(username=data["email"], email=data["email"], first_name=data.get("full_name", ""))
            try:
                password_validation.validate_password(data["password"], candidate)
            except forms.ValidationError as error:
                self.add_error("password", error)
        return data


def _hosted_only():
    if not settings.KONDIS_HOSTED:
        raise Http404


@require_http_methods(["GET", "POST"])
def signup(request: HttpRequest) -> HttpResponse:
    _hosted_only()
    if request.user.is_authenticated:
        return redirect("coaching:dashboard")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        first, _sep, last = data["full_name"].strip().partition(" ")
        with transaction.atomic():
            user = get_user_model().objects.create_user(
                username=data["email"], email=data["email"], password=data["password"], first_name=first, last_name=last
            )
            Subscription.start_trial(user, gym_name=data["gym_name"], phone=data["phone"])
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("coaching:dashboard")
    return render(request, "billing/signup.html", {"form": form, "trial_days": settings.KONDIS_TRIAL_DAYS})


@login_required
def subscription(request: HttpRequest) -> HttpResponse:
    _hosted_only()
    sub = getattr(request.user, "subscription", None)
    return render(
        request,
        "billing/subscription.html",
        {
            "sub": sub,
            "price_monthly": settings.KONDIS_PRICE_MONTHLY,
            "price_yearly": settings.KONDIS_PRICE_YEARLY,
            "pay_monthly_url": settings.KONDIS_PAY_MONTHLY_URL,
            "pay_yearly_url": settings.KONDIS_PAY_YEARLY_URL,
            "support_whatsapp": settings.KONDIS_SUPPORT_WHATSAPP,
            "nav": "subscription",
        },
    )
