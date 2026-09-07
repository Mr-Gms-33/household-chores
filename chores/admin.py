from django.contrib import admin

from .models import ChoreInstance, ChoreTemplate, Household, WeekPlan


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ("name",)
    filter_horizontal = ("members",)


@admin.register(ChoreTemplate)
class ChoreTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "household", "weekday", "default_assignee")
    list_filter = ("household", "weekday")


class ChoreInstanceInline(admin.TabularInline):
    model = ChoreInstance
    extra = 0


@admin.register(WeekPlan)
class WeekPlanAdmin(admin.ModelAdmin):
    list_display = ("household", "week_start")
    list_filter = ("household",)
    inlines = [ChoreInstanceInline]


@admin.register(ChoreInstance)
class ChoreInstanceAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "assignee", "complete", "week_plan")
    list_filter = ("complete", "assignee", "week_plan")
