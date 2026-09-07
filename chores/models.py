from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import m2m_changed
from django.utils import timezone

MAX_HOUSEHOLD_MEMBERS = 2


def validate_household_member_pks(household, member_pks, *, replace=False):
    """Reject more than two members, or a user who already belongs elsewhere."""
    incoming = {int(pk) for pk in member_pks}
    if household.pk and not replace:
        current = set(household.members.values_list("pk", flat=True))
        resulting = current | incoming
    else:
        resulting = incoming
    if len(resulting) > MAX_HOUSEHOLD_MEMBERS:
        raise ValidationError("A household can have at most two members.")
    if not incoming:
        return
    already_elsewhere = Household.objects.filter(members__in=incoming)
    if household.pk:
        already_elsewhere = already_elsewhere.exclude(pk=household.pk)
    if already_elsewhere.exists():
        raise ValidationError("A user cannot be a member of two households at once.")


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

    def clean(self):
        super().clean()
        if not self.pk:
            return
        member_pks = list(self.members.values_list("pk", flat=True))
        validate_household_member_pks(self, member_pks, replace=True)


def _household_members_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in ("pre_add", "pre_set"):
        return
    pks = pk_set or set()
    if reverse:
        user = instance
        existing = Household.objects.filter(members=user)
        if action == "pre_add":
            if existing.exists() or len(pks) > 1:
                raise ValidationError(
                    "A user cannot be a member of two households at once."
                )
            for household_id in pks:
                household = Household.objects.get(pk=household_id)
                if household.members.count() >= MAX_HOUSEHOLD_MEMBERS:
                    raise ValidationError(
                        "A household can have at most two members."
                    )
        elif action == "pre_set":
            if len(pks) > 1:
                raise ValidationError(
                    "A user cannot be a member of two households at once."
                )
            for household_id in pks:
                household = Household.objects.get(pk=household_id)
                already_here = household.members.filter(pk=user.pk).exists()
                if not already_here and household.members.count() >= MAX_HOUSEHOLD_MEMBERS:
                    raise ValidationError(
                        "A household can have at most two members."
                    )
        return

    replace = action == "pre_set"
    validate_household_member_pks(instance, pks, replace=replace)


m2m_changed.connect(
    _household_members_changed,
    sender=Household.members.through,
)


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
