from django.contrib import admin

from .models import Client, Exercise, Membership, Program, ProgramDay, ProgramItem, SetEntry, Workout


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "trainer", "goal", "is_active", "created_at")
    list_filter = ("is_active", "goal", "trainer")
    search_fields = ("full_name", "phone", "email")
    inlines = [MembershipInline]


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ("name_tr", "name_en", "muscle", "equipment", "trainer")
    list_filter = ("muscle", "equipment")
    search_fields = ("name_tr", "name_en")


class ProgramItemInline(admin.TabularInline):
    model = ProgramItem
    extra = 0


@admin.register(ProgramDay)
class ProgramDayAdmin(admin.ModelAdmin):
    list_display = ("title", "program", "weekday")
    inlines = [ProgramItemInline]


class SetEntryInline(admin.TabularInline):
    model = SetEntry
    extra = 0


@admin.register(Workout)
class WorkoutAdmin(admin.ModelAdmin):
    list_display = ("client", "performed_on", "day", "finished_at")
    inlines = [SetEntryInline]


admin.site.register(Program)
admin.site.register(Membership)
