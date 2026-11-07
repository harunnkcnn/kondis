"""Trainer-facing views. Every query is scoped to request.user."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import services
from .forms import ClientForm, ExerciseForm, MembershipForm, ProgramDayForm, ProgramForm, ProgramItemForm
from .models import Client, Exercise, Membership, Program, ProgramDay, ProgramItem, Workout


def _client(request: HttpRequest, pk: int) -> Client:
    return get_object_or_404(Client, pk=pk, trainer=request.user)


def _program(request: HttpRequest, pk: int) -> Program:
    return get_object_or_404(Program.objects.select_related("client"), pk=pk, client__trainer=request.user)


def portal_url(request: HttpRequest, client: Client) -> str:
    path = client.portal_path()
    return f"{settings.KONDIS_BASE_URL}{path}" if settings.KONDIS_BASE_URL else request.build_absolute_uri(path)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "coaching/dashboard.html", {"board": services.build_dashboard(request.user), "nav": "today"})


@login_required
def client_list(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    clients = (
        Client.objects.filter(trainer=request.user)
        .annotate(last_seen=Max("workouts__performed_on"), workout_count=Count("workouts"))
        .prefetch_related("memberships")
    )
    if query:
        clients = clients.filter(Q(full_name__icontains=query) | Q(phone__icontains=query))
    show = request.GET.get("show", "active")
    if show == "active":
        clients = clients.filter(is_active=True)
    template = "coaching/partials/client_rows.html" if request.headers.get("HX-Request") else "coaching/client_list.html"
    return render(request, template, {"clients": clients, "q": query, "show": show, "nav": "clients"})


@login_required
def client_create(request: HttpRequest) -> HttpResponse:
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save(commit=False)
        client.trainer = request.user
        client.save()
        messages.success(request, _("%(name)s added. Share their link so they can log workouts.") % {"name": client})
        return redirect(client)
    return render(request, "coaching/form.html", {"form": form, "title": _("New client"), "nav": "clients"})


@login_required
def client_edit(request: HttpRequest, pk: int) -> HttpResponse:
    client = _client(request, pk)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Changes saved."))
        return redirect(client)
    return render(
        request, "coaching/form.html", {"form": form, "title": client.full_name, "back": client.get_absolute_url(), "nav": "clients"}
    )


@login_required
def client_detail(request: HttpRequest, pk: int) -> HttpResponse:
    client = _client(request, pk)
    workouts = client.workouts.select_related("day").prefetch_related("sets")[:10]
    weights = list(client.workouts.exclude(body_weight__isnull=True).order_by("performed_on").values_list("performed_on", "body_weight"))[
        -20:
    ]
    return render(
        request,
        "coaching/client_detail.html",
        {
            "client": client,
            "memberships": client.memberships.all()[:5],
            "program": client.active_program,
            "workouts": workouts,
            "records": services.personal_records(client, limit=8),
            "weights": weights,
            "portal_url": portal_url(request, client),
            "nav": "clients",
        },
    )


@login_required
@require_POST
def client_rotate_link(request: HttpRequest, pk: int) -> HttpResponse:
    client = _client(request, pk)
    client.rotate_token()
    messages.success(request, _("New link created. The old one no longer works."))
    return redirect(client)


@login_required
def membership_create(request: HttpRequest, pk: int) -> HttpResponse:
    client = _client(request, pk)
    form = MembershipForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        membership = form.save(commit=False)
        membership.client = client
        membership.save()
        messages.success(request, _("Package added."))
        return redirect(client)
    return render(
        request,
        "coaching/form.html",
        {"form": form, "title": _("New package for %(name)s") % {"name": client}, "back": client.get_absolute_url(), "nav": "clients"},
    )


@login_required
@require_POST
def membership_use_session(request: HttpRequest, pk: int) -> HttpResponse:
    membership = get_object_or_404(Membership, pk=pk, client__trainer=request.user)
    if not membership.use_session():
        messages.error(request, _("No sessions left on this package."))
    if request.headers.get("HX-Request"):
        return render(request, "coaching/partials/membership_card.html", {"m": membership})
    return redirect(membership.client)


@login_required
def program_create(request: HttpRequest, pk: int) -> HttpResponse:
    client = _client(request, pk)
    form = ProgramForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        template = form.cleaned_data.get("template")
        if template:
            program = services.create_program_from_template(client, template)
            if form.cleaned_data.get("title"):
                program.title = form.cleaned_data["title"]
            program.notes = form.cleaned_data.get("notes", "")
            program.save()
        else:
            program = form.save(commit=False)
            program.client = client
            program.save()
        return redirect(program)
    return render(
        request,
        "coaching/form.html",
        {"form": form, "title": _("New program for %(name)s") % {"name": client}, "back": client.get_absolute_url(), "nav": "clients"},
    )


@login_required
def program_builder(request: HttpRequest, pk: int) -> HttpResponse:
    program = _program(request, pk)
    days = program.days.prefetch_related("items__exercise")
    return render(
        request,
        "coaching/program_builder.html",
        {
            "program": program,
            "days": days,
            "day_form": ProgramDayForm(),
            "item_form": ProgramItemForm(trainer=request.user),
            "nav": "clients",
        },
    )


@login_required
@require_POST
def program_day_add(request: HttpRequest, pk: int) -> HttpResponse:
    program = _program(request, pk)
    form = ProgramDayForm(request.POST)
    if form.is_valid():
        day = form.save(commit=False)
        day.program = program
        day.order = program.days.count()
        day.save()
    else:
        messages.error(request, _("Give the day a title."))
    return redirect(program)


@login_required
@require_POST
def program_day_delete(request: HttpRequest, pk: int) -> HttpResponse:
    day = get_object_or_404(ProgramDay, pk=pk, program__client__trainer=request.user)
    program = day.program
    day.delete()
    return redirect(program)


@login_required
@require_POST
def program_item_add(request: HttpRequest, pk: int) -> HttpResponse:
    day = get_object_or_404(ProgramDay.objects.select_related("program"), pk=pk, program__client__trainer=request.user)
    form = ProgramItemForm(request.POST, trainer=request.user)
    if form.is_valid():
        item = form.save(commit=False)
        item.day = day
        item.order = day.items.count()
        item.save()
        if request.headers.get("HX-Request"):
            return render(request, "coaching/partials/program_item.html", {"item": item})
        return redirect(day.program)
    if request.headers.get("HX-Request"):
        return HttpResponse(status=422)
    messages.error(request, _("Check the exercise fields."))
    return redirect(day.program)


@login_required
@require_POST
def program_item_delete(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(ProgramItem, pk=pk, day__program__client__trainer=request.user)
    program = item.day.program
    item.delete()
    if request.headers.get("HX-Request"):
        return HttpResponse("")
    return redirect(program)


@login_required
def workout_detail(request: HttpRequest, pk: int) -> HttpResponse:
    workout = get_object_or_404(Workout.objects.select_related("client", "day"), pk=pk, client__trainer=request.user)
    sets = workout.sets.select_related("exercise")
    grouped: dict[Exercise, list] = {}
    for entry in sets:
        grouped.setdefault(entry.exercise, []).append(entry)
    return render(request, "coaching/workout_detail.html", {"workout": workout, "grouped": grouped, "nav": "clients"})


@login_required
def exercise_list(request: HttpRequest) -> HttpResponse:
    form = ExerciseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        exercise = form.save(commit=False)
        exercise.trainer = request.user
        exercise.slug = f"custom-{Exercise.objects.filter(trainer=request.user).count() + 1}"
        exercise.save()
        messages.success(request, _("Exercise added to your library."))
        return redirect("coaching:exercise_list")
    exercises = Exercise.available_to(request.user)
    muscle = request.GET.get("muscle", "")
    if muscle:
        exercises = exercises.filter(muscle=muscle)
    return render(
        request,
        "coaching/exercise_list.html",
        {"exercises": exercises, "form": form, "muscles": Exercise.Muscle.choices, "muscle": muscle, "nav": "library"},
    )
