from django.http import HttpResponse


class HealthCheckMiddleware:
    """Answer /healthz/ before host validation, so load balancers and container checks
    that call the app by IP don't trip ALLOWED_HOSTS."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz/":
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
