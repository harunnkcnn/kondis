from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "gym_name", "phone", "status", "paid_until", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "user__email", "gym_name", "phone")
    actions = ["add_month", "add_year", "cancel"]

    @admin.action(description=_("Payment received: add 1 month"))
    def add_month(self, request, queryset):
        for sub in queryset:
            sub.extend(30)
        messages.success(request, _("Extended by 30 days."))

    @admin.action(description=_("Payment received: add 1 year"))
    def add_year(self, request, queryset):
        for sub in queryset:
            sub.extend(365)
        messages.success(request, _("Extended by 365 days."))

    @admin.action(description=_("Cancel access"))
    def cancel(self, request, queryset):
        queryset.update(status=Subscription.Status.CANCELED)
