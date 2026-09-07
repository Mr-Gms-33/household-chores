from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def current_week_start(today=None):
    """Return the Monday of the week containing `today` (local date by default)."""
    today = today or timezone.localdate()
    return today - timedelta(days=today.weekday())


class Household(models.Model):
    name = models.CharField(max_length=100)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="households",
        blank=True,
    )

    def __str__(self):
        return self.name


class Assignee(models.TextChoices):
    PARTNER_A = "partner_a", "Partner A"
    PARTNER_B = "partner_b", "Partner B"
    EITHER = "either", "Either"


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class ChoreTemplate(models.Model):
    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="templates",
    )
    name = models.CharField(max_length=200)
    weekday = models.IntegerField(choices=Weekday.choices)
    default_assignee = models.CharField(
        max_length=16,
        choices=[
            (Assignee.PARTNER_A, Assignee.PARTNER_A.label),
            (Assignee.PARTNER_B, Assignee.PARTNER_B.label),
        ],
        blank=True,
        default="",
    )

    def __str__(self):
        return self.name


class WeekPlan(models.Model):
    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="week_plans",
    )
    week_start = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["household", "week_start"],
                name="chores_unique_week_plan_per_household",
            ),
        ]

    def __str__(self):
        return f"{self.household} — week of {self.week_start}"

    @classmethod
    def generate_current_week(cls, household):
        """Create this week's plan and one instance per matching template.

        Existing instances for the same plan + template are left unchanged.
        """
        week_start = current_week_start()
        week_plan, _ = cls.objects.get_or_create(
            household=household,
            week_start=week_start,
        )
        templates = household.templates.filter(
            weekday__gte=Weekday.MONDAY,
            weekday__lte=Weekday.SUNDAY,
        )
        for template in templates:
            assignee = template.default_assignee or Assignee.EITHER
            ChoreInstance.objects.get_or_create(
                week_plan=week_plan,
                template=template,
                defaults={
                    "title": template.name,
                    "date": week_start + timedelta(days=template.weekday),
                    "assignee": assignee,
                },
            )
        return week_plan


class ChoreInstance(models.Model):
    week_plan = models.ForeignKey(
        WeekPlan,
        on_delete=models.CASCADE,
        related_name="chores",
    )
    template = models.ForeignKey(
        ChoreTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instances",
    )
    title = models.CharField(max_length=200)
    date = models.DateField()
    assignee = models.CharField(max_length=16, choices=Assignee.choices)
    complete = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["week_plan", "template"],
                condition=models.Q(template__isnull=False),
                name="chores_unique_template_instance_per_week",
            ),
            models.UniqueConstraint(
                fields=["week_plan", "title", "date"],
                condition=models.Q(template__isnull=True),
                name="chores_unique_one_off_instance_per_week",
            ),
        ]

    def __str__(self):
        return self.title
