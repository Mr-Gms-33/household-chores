from datetime import timedelta

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Assignee,
    ChoreInstance,
    ChoreTemplate,
    Household,
    WeekPlan,
    Weekday,
    current_week_start,
)


class ProjectSmokeTest(TestCase):
    def test_chores_app_is_installed(self):
        self.assertTrue(apps.is_installed("chores"))


class HouseholdFixturesMixin:
    def setUp(self):
        super().setUp()
        self.user_a = User.objects.create_user(
            username="alice",
            password="password123",
        )
        self.user_b = User.objects.create_user(
            username="bob",
            password="password123",
        )
        self.outsider = User.objects.create_user(
            username="charlie",
            password="password123",
        )
        self.household = Household.objects.create(name="Maple Street")
        self.household.members.add(self.user_a, self.user_b)
        self.week_start = current_week_start()


class GenerateWeekTests(HouseholdFixturesMixin, TestCase):
    def test_generate_creates_instances_from_templates(self):
        ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
            default_assignee=Assignee.PARTNER_A,
        )
        ChoreTemplate.objects.create(
            household=self.household,
            name="Trash",
            weekday=Weekday.SUNDAY,
            default_assignee="",
        )
        self.client.login(username="alice", password="password123")

        response = self.client.post(reverse("generate_week"))

        self.assertRedirects(response, reverse("home"))
        instances = ChoreInstance.objects.filter(week_plan__household=self.household)
        self.assertEqual(instances.count(), 2)

        vacuum = instances.get(title="Vacuum")
        self.assertEqual(vacuum.date, self.week_start)
        self.assertEqual(vacuum.assignee, Assignee.PARTNER_A)
        self.assertFalse(vacuum.complete)
        self.assertEqual(vacuum.template.name, "Vacuum")

        trash = instances.get(title="Trash")
        self.assertEqual(trash.date, self.week_start + timedelta(days=6))
        self.assertEqual(trash.assignee, Assignee.EITHER)
        self.assertFalse(trash.complete)

    def test_generate_is_idempotent(self):
        ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
            default_assignee=Assignee.PARTNER_A,
        )
        self.client.login(username="alice", password="password123")

        self.client.post(reverse("generate_week"))
        self.client.post(reverse("generate_week"))

        self.assertEqual(WeekPlan.objects.filter(household=self.household).count(), 1)
        self.assertEqual(
            ChoreInstance.objects.filter(week_plan__household=self.household).count(),
            1,
        )

    def test_generate_ignores_other_household_templates(self):
        other = Household.objects.create(name="Oak Avenue")
        other.members.add(self.outsider)
        ChoreTemplate.objects.create(
            household=other,
            name="Other chore",
            weekday=Weekday.MONDAY,
        )
        ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
            default_assignee=Assignee.PARTNER_A,
        )
        self.client.login(username="alice", password="password123")

        self.client.post(reverse("generate_week"))

        titles = list(
            ChoreInstance.objects.filter(
                week_plan__household=self.household
            ).values_list("title", flat=True)
        )
        self.assertEqual(titles, ["Vacuum"])
        self.assertFalse(
            ChoreInstance.objects.filter(week_plan__household=other).exists()
        )


class AddOneOffChoreTests(HouseholdFixturesMixin, TestCase):
    def test_member_can_add_one_off_chore(self):
        self.client.login(username="alice", password="password123")
        chore_date = timezone.localdate()

        response = self.client.post(
            reverse("add_chore"),
            {
                "title": "Buy milk",
                "date": chore_date.isoformat(),
                "assignee": Assignee.PARTNER_B,
            },
        )

        self.assertRedirects(response, reverse("home"))
        instance = ChoreInstance.objects.get(title="Buy milk")
        self.assertIsNone(instance.template)
        self.assertEqual(instance.date, chore_date)
        self.assertEqual(instance.assignee, Assignee.PARTNER_B)
        self.assertFalse(instance.complete)
        self.assertEqual(instance.week_plan.household, self.household)
        self.assertEqual(instance.week_plan.week_start, self.week_start)

    def test_one_off_date_must_be_in_current_week(self):
        self.client.login(username="alice", password="password123")
        outside = self.week_start - timedelta(days=1)

        response = self.client.post(
            reverse("add_chore"),
            {
                "title": "Too early",
                "date": outside.isoformat(),
                "assignee": Assignee.EITHER,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ChoreInstance.objects.exists())


class NonMemberAccessTests(HouseholdFixturesMixin, TestCase):
    def test_user_without_household_cannot_generate(self):
        self.client.login(username="charlie", password="password123")

        response = self.client.post(reverse("generate_week"))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(WeekPlan.objects.exists())

    def test_user_without_household_cannot_add_chore(self):
        self.client.login(username="charlie", password="password123")

        response = self.client.post(
            reverse("add_chore"),
            {
                "title": "Sneaky chore",
                "date": timezone.localdate().isoformat(),
                "assignee": Assignee.EITHER,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ChoreInstance.objects.exists())

    def test_other_household_member_cannot_create_chores_here(self):
        other = Household.objects.create(name="Oak Avenue")
        other.members.add(self.outsider)
        ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
            default_assignee=Assignee.PARTNER_A,
        )
        self.client.login(username="charlie", password="password123")

        self.client.post(reverse("generate_week"))
        self.client.post(
            reverse("add_chore"),
            {
                "title": "Not yours",
                "date": timezone.localdate().isoformat(),
                "assignee": Assignee.EITHER,
            },
        )

        self.assertFalse(
            ChoreInstance.objects.filter(week_plan__household=self.household).exists()
        )
        self.assertTrue(
            ChoreInstance.objects.filter(week_plan__household=other).exists()
        )
