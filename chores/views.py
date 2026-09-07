from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ChoreAssigneeForm, ChoreMoveForm, ChoreTemplateForm, OneOffChoreForm
from .household import get_user_household, household_required
from .models import ChoreInstance, ChoreTemplate, WeekPlan, current_week_start


@login_required
def home(request):
    household = get_user_household(request.user)
    return render(request, "chores/home.html", {"household": household})


@household_required
def generate_week(request):
    if request.method == "POST":
        WeekPlan.generate_current_week(request.household)
        messages.success(request, "This week's chores have been generated.")
    return redirect("home")


@household_required
def add_chore(request):
    week_start = current_week_start()
    if request.method == "POST":
        form = OneOffChoreForm(request.POST, week_start=week_start)
        if form.is_valid():
            week_plan, _ = WeekPlan.objects.get_or_create(
                household=request.household,
                week_start=week_start,
            )
            ChoreInstance.objects.get_or_create(
                week_plan=week_plan,
                template=None,
                title=form.cleaned_data["title"],
                date=form.cleaned_data["date"],
                defaults={"assignee": form.cleaned_data["assignee"]},
            )
            messages.success(request, "Chore added.")
            return redirect("home")
    else:
        form = OneOffChoreForm(week_start=week_start)
    return render(
        request,
        "chores/add_chore.html",
        {"form": form, "household": request.household},
    )


def _board_context(household):
    """Build the current week's board data: 7 days, each with its chores.

    Looks up (does not create) the WeekPlan for the current week; if none
    exists yet, every day renders empty rather than erroring.
    """
    week_start = current_week_start()
    week_plan = WeekPlan.objects.filter(
        household=household, week_start=week_start
    ).first()

    days = []
    for offset in range(7):
        day_date = week_start + timedelta(days=offset)
        if week_plan is not None:
            chores = list(
                week_plan.chores.filter(date=day_date).order_by("title", "pk")
            )
        else:
            chores = []
        days.append(
            {
                "date": day_date,
                "weekday_name": day_date.strftime("%A"),
                "chores": [
                    {
                        "instance": chore,
                        "assignee_form": ChoreAssigneeForm(instance=chore),
                        "move_form": ChoreMoveForm(
                            week_start=week_start,
                            initial={"date": chore.date.isoformat()},
                        ),
                    }
                    for chore in chores
                ],
            }
        )
    return {
        "household": household,
        "week_start": week_start,
        "week_plan": week_plan,
        "days": days,
    }


@login_required
def board(request):
    household = get_user_household(request.user)
    if household is None:
        return render(request, "chores/board.html", {"household": None})
    return render(request, "chores/board.html", _board_context(household))


def _get_current_week_chore(request, pk):
    """Fetch a ChoreInstance for this household's *current* WeekPlan only.

    Returns 404 if the id belongs to another household, or to a WeekPlan
    that is not the current week's plan for this household.
    """
    week_start = current_week_start()
    return get_object_or_404(
        ChoreInstance,
        pk=pk,
        week_plan__household=request.household,
        week_plan__week_start=week_start,
    )


@household_required
def board_chore_assignee(request, pk):
    if request.method != "POST":
        return redirect("board")
    chore = _get_current_week_chore(request, pk)
    form = ChoreAssigneeForm(request.POST, instance=chore)
    if form.is_valid():
        form.save()
        messages.success(request, "Assignee updated.")
        return redirect("board")
    messages.error(request, "Could not update assignee.")
    return render(
        request,
        "chores/board.html",
        _board_context(request.household),
        status=400,
    )


@household_required
def board_chore_move(request, pk):
    if request.method != "POST":
        return redirect("board")
    chore = _get_current_week_chore(request, pk)
    form = ChoreMoveForm(request.POST, week_start=current_week_start())
    if form.is_valid():
        chore.date = form.cleaned_data["date"]
        chore.save(update_fields=["date"])
        messages.success(request, "Chore moved.")
        return redirect("board")
    messages.error(request, "Could not move chore.")
    return render(
        request,
        "chores/board.html",
        _board_context(request.household),
        status=400,
    )


@household_required
def template_list(request):
    templates = request.household.templates.order_by("weekday", "name", "pk")
    return render(
        request,
        "chores/template_list.html",
        {"household": request.household, "templates": templates},
    )


@household_required
def template_create(request):
    if request.method == "POST":
        form = ChoreTemplateForm(request.POST)
        if form.is_valid():
            template = form.save(commit=False)
            template.household = request.household
            template.save()
            messages.success(request, "Template created.")
            return redirect("template_list")
    else:
        form = ChoreTemplateForm()
    return render(
        request,
        "chores/template_form.html",
        {
            "form": form,
            "household": request.household,
            "heading": "New chore template",
        },
    )


@household_required
def template_edit(request, pk):
    template = get_object_or_404(
        ChoreTemplate, pk=pk, household=request.household
    )
    if request.method == "POST":
        form = ChoreTemplateForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, "Template updated.")
            return redirect("template_list")
    else:
        form = ChoreTemplateForm(instance=template)
    return render(
        request,
        "chores/template_form.html",
        {
            "form": form,
            "household": request.household,
            "heading": "Edit chore template",
            "template": template,
        },
    )


@household_required
def template_delete(request, pk):
    template = get_object_or_404(
        ChoreTemplate, pk=pk, household=request.household
    )
    if request.method == "POST":
        template.delete()
        messages.success(request, "Template deleted.")
        return redirect("template_list")
    return render(
        request,
        "chores/template_confirm_delete.html",
        {"household": request.household, "template": template},
    )
