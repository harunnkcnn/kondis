from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from coaching.views import KondisLoginView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", KondisLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("c/", include("coaching.portal_urls")),
    path("", include("coaching.urls")),
]
