from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import OneOffChoreForm
from .household import get_user_household, household_required
from .models import ChoreInstance, WeekPlan, current_week_start


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
