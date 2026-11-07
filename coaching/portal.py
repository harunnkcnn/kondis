"""Client portal: no account, no app. Access is a private, rotatable link."""

from functools import wraps

from django.db import transaction
from django.db.models import Max
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from billing.middleware import portal_paused_response
from billing.models import has_access as trainer_has_access

from . import services
from .forms import FinishWorkoutForm, SetEntryForm
from .models import Client, Exercise, ProgramDay, SetEntry, Workout


def portal_view(view):
    """Resolve the token to an active client and keep the page out of search engines and third-party referrers."""

    @wraps(view)
    def wrapper(request: HttpRequest, token: str, *args, **kwargs) -> HttpResponse:
        client = get_object_or_404(Client.objects.select_related("trainer"), access_token=token, is_active=True)
        if not trainer_has_access(client.trainer):
            response = portal_paused_response(request, client)
        else:
            response = view(request, client, *args, **kwargs)
        response["X-Robots-Tag"] = "noindex, nofollow"
        response["Referrer-Policy"] = "same-origin"
        response["Cache-Control"] = "private, no-store"
        return response

    return wrapper


def _workout(client: Client, pk: int) -> Workout:
    return get_object_or_404(Workout.objects.select_related("day"), pk=pk, client=client)


@portal_view
def home(request: HttpRequest, client: Client) -> HttpResponse:
    program = client.active_program
    open_workout = client.workouts.filter(finished_at__isnull=True, performed_on=timezone.localdate()).first()
    return render(
        request,
        "coaching/portal/home.html",
        {
            "client": client,
            "program": program,
            "days": program.days.prefetch_related("items__exercise") if program else [],
            "suggested": program.suggested_day() if program else None,
            "open_workout": open_workout,
            "membership": client.current_membership,
            "recent": client.workouts.select_related("day")[:5],
        },
    )


@portal_view
@require_POST
def start(request: HttpRequest, client: Client, day_id: int) -> HttpResponse:
    program = client.active_program
    if program is None:
        raise Http404
    day = get_object_or_404(ProgramDay, pk=day_id, program=program)
    workout = Workout.objects.create(client=client, day=day, performed_on=timezone.localdate())
    return redirect("portal:workout", token=client.access_token, pk=workout.pk)


@portal_view
def workout(request: HttpRequest, client: Client, pk: int) -> HttpResponse:
    session = _workout(client, pk)
    logged = list(session.sets.select_related("exercise"))
    blocks = []
    items = session.day.items.select_related("exercise") if session.day else []
    for item in items:
        blocks.append(
            {
                "item": item,
                "exercise": item.exercise,
                "sets": [s for s in logged if s.exercise_id == item.exercise_id],
                "previous": services.previous_sets(client, item.exercise, before=session),
            }
        )
    return render(
        request,
        "coaching/portal/workout.html",
        {"client": client, "workout": session, "blocks": blocks, "finish_form": FinishWorkoutForm(instance=session)},
    )


@portal_view
@require_POST
def add_set(request: HttpRequest, client: Client, pk: int) -> HttpResponse:
    session = _workout(client, pk)
    if session.is_finished:
        return HttpResponse(status=409)
    form = SetEntryForm(request.POST)
    if not form.is_valid():
        return HttpResponse(status=422)
    allowed = Exercise.available_to(client.trainer)
    exercise = get_object_or_404(allowed, pk=form.cleaned_data["exercise"])
    item = None
    if session.day and form.cleaned_data.get("item"):
        item = session.day.items.filter(pk=form.cleaned_data["item"]).first()
    with transaction.atomic():
        last = session.sets.filter(exercise=exercise).aggregate(n=Max("set_number"))["n"] or 0
        entry = SetEntry.objects.create(
            workout=session,
            exercise=exercise,
            item=item,
            set_number=last + 1,
            weight=form.cleaned_data.get("weight") or 0,
            reps=form.cleaned_data["reps"],
        )
    return render(request, "coaching/portal/set_row.html", {"s": entry, "client": client, "workout": session})


@portal_view
@require_POST
def delete_set(request: HttpRequest, client: Client, pk: int, set_id: int) -> HttpResponse:
    session = _workout(client, pk)
    if not session.is_finished:
        session.sets.filter(pk=set_id).delete()
    return HttpResponse("")


@portal_view
@require_POST
def finish(request: HttpRequest, client: Client, pk: int) -> HttpResponse:
    session = _workout(client, pk)
    form = FinishWorkoutForm(request.POST, instance=session)
    if form.is_valid():
        done = form.save(commit=False)
        done.finished_at = timezone.now()
        done.save()
    return redirect("portal:summary", token=client.access_token, pk=session.pk)


@portal_view
def summary(request: HttpRequest, client: Client, pk: int) -> HttpResponse:
    session = _workout(client, pk)
    records = {r.exercise.pk: r for r in services.personal_records(client)}
    new_records = [
        r for r in records.values() if r.performed_on == session.performed_on and session.sets.filter(exercise=r.exercise).exists()
    ]
    return render(
        request,
        "coaching/portal/summary.html",
        {"client": client, "workout": session, "set_count": session.sets.count(), "new_records": new_records},
    )


@portal_view
def progress(request: HttpRequest, client: Client) -> HttpResponse:
    return render(
        request,
        "coaching/portal/progress.html",
        {"client": client, "records": services.personal_records(client), "history": client.workouts.select_related("day")[:30]},
    )
