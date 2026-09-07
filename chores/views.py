from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ChoreTemplateForm, OneOffChoreForm
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
