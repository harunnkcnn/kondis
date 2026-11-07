from django.conf import settings


def billing(request):
    if not settings.KONDIS_HOSTED or not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"KONDIS_HOSTED": settings.KONDIS_HOSTED, "KONDIS_TRIAL_DAYS": settings.KONDIS_TRIAL_DAYS}
    return {
        "KONDIS_HOSTED": True,
        "KONDIS_TRIAL_DAYS": settings.KONDIS_TRIAL_DAYS,
        "subscription": getattr(request.user, "subscription", None),
    }
