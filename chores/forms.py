from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import Assignee, ChoreInstance, ChoreTemplate, Weekday


class OneOffChoreForm(forms.ModelForm):
    class Meta:
        model = ChoreInstance
        fields = ("title", "date", "assignee")

    def __init__(self, *args, week_start=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.week_start = week_start
        week_end = week_start + timedelta(days=6) if week_start else None
        self.fields["date"].widget = forms.DateInput(
            attrs={
                "type": "date",
                **(
                    {
                        "min": week_start.isoformat(),
                        "max": week_end.isoformat(),
                    }
                    if week_start and week_end
                    else {}
                ),
            }
        )
        self.fields["date"].initial = timezone.localdate()
        self.fields["assignee"].initial = Assignee.EITHER

    def clean_date(self):
        chore_date = self.cleaned_data["date"]
        if self.week_start is None:
            return chore_date
        week_end = self.week_start + timedelta(days=6)
        if chore_date < self.week_start or chore_date > week_end:
            raise forms.ValidationError("Date must be within the current week.")
        return chore_date


class ChoreTemplateForm(forms.ModelForm):
    class Meta:
        model = ChoreTemplate
        fields = ("name", "weekday", "default_assignee")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        self.fields["weekday"].choices = list(Weekday.choices)
        self.fields["default_assignee"].required = False
        self.fields["default_assignee"].choices = [
            ("", "Unset"),
            (Assignee.PARTNER_A, Assignee.PARTNER_A.label),
            (Assignee.PARTNER_B, Assignee.PARTNER_B.label),
        ]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("This field is required.")
        return name
