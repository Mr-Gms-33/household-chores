from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import ChoreInstance, ChoreTemplate, Household, WeekPlan, validate_household_member_pks


class HouseholdAdminForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = "__all__"

    def clean_members(self):
        members = self.cleaned_data["members"]
        member_pks = [user.pk for user in members]
        try:
            validate_household_member_pks(self.instance, member_pks, replace=True)
        except DjangoValidationError as exc:
            raise forms.ValidationError(exc.messages)
        return members


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    form = HouseholdAdminForm
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
