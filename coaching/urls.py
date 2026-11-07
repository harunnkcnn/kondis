from django.urls import path

from . import views

app_name = "coaching"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("clients/", views.client_list, name="client_list"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clients/<int:pk>/", views.client_detail, name="client_detail"),
    path("clients/<int:pk>/edit/", views.client_edit, name="client_edit"),
    path("clients/<int:pk>/rotate-link/", views.client_rotate_link, name="client_rotate_link"),
    path("clients/<int:pk>/packages/new/", views.membership_create, name="membership_create"),
    path("clients/<int:pk>/programs/new/", views.program_create, name="program_create"),
    path("packages/<int:pk>/use-session/", views.membership_use_session, name="membership_use_session"),
    path("programs/<int:pk>/", views.program_builder, name="program_builder"),
    path("programs/<int:pk>/days/", views.program_day_add, name="program_day_add"),
    path("days/<int:pk>/delete/", views.program_day_delete, name="program_day_delete"),
    path("days/<int:pk>/items/", views.program_item_add, name="program_item_add"),
    path("items/<int:pk>/delete/", views.program_item_delete, name="program_item_delete"),
    path("workouts/<int:pk>/", views.workout_detail, name="workout_detail"),
    path("library/", views.exercise_list, name="exercise_list"),
]
