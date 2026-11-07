from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("subscription/", views.subscription, name="subscription"),
]
