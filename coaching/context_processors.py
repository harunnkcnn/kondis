from django.conf import settings


def kondis(request):
    return {
        "KONDIS_EDITION": "pro" if "kondis_pro" in settings.INSTALLED_APPS else "community",
    }
