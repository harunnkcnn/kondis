from django.urls import path

from . import portal

app_name = "portal"

urlpatterns = [
    path("<str:token>/", portal.home, name="home"),
    path("<str:token>/progress/", portal.progress, name="progress"),
    path("<str:token>/start/<int:day_id>/", portal.start, name="start"),
    path("<str:token>/w/<int:pk>/", portal.workout, name="workout"),
    path("<str:token>/w/<int:pk>/sets/", portal.add_set, name="add_set"),
    path("<str:token>/w/<int:pk>/sets/<int:set_id>/delete/", portal.delete_set, name="delete_set"),
    path("<str:token>/w/<int:pk>/finish/", portal.finish, name="finish"),
    path("<str:token>/w/<int:pk>/done/", portal.summary, name="summary"),
]
