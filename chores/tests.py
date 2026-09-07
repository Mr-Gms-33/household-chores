from datetime import timedelta

from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .household import get_user_household

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


class AuthAndHomeTests(HouseholdFixturesMixin, TestCase):
    def test_home_requires_login(self):
        response = self.client.get("/")
        self.assertRedirects(response, "/accounts/login/?next=/")

    def test_login_page_shows_fields_and_button(self):
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
        self.assertContains(response, "Log in")

    def test_successful_login(self):
        response = self.client.post(
            "/accounts/login/",
            {"username": "alice", "password": "password123"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.wsgi_request.path, "/")
        self.assertContains(response, "Maple Street")

    def test_failed_login(self):
        response = self.client.post(
            "/accounts/login/",
            {"username": "alice", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.wsgi_request.path, "/accounts/login/")
        self.assertTrue(response.context["form"].errors)
        home = self.client.get("/")
        self.assertRedirects(home, "/accounts/login/?next=/")

    def test_logout(self):
        self.client.login(username="alice", password="password123")
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, "/accounts/login/")
        home = self.client.get("/")
        self.assertRedirects(home, "/accounts/login/?next=/")

    def test_non_member_home_shows_message(self):
        self.client.login(username="charlie", password="password123")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not a member of a household")
        self.assertNotContains(response, "Maple Street")

    def test_both_members_see_household_name(self):
        for username in ("alice", "bob"):
            self.client.login(username=username, password="password123")
            response = self.client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Maple Street")
            self.client.logout()

    def test_unauthenticated_week_views_redirect_to_login(self):
        generate = reverse("generate_week")
        add_chore = reverse("add_chore")
        self.assertRedirects(
            self.client.get(generate),
            f"/accounts/login/?next={generate}",
        )
        self.assertRedirects(
            self.client.get(add_chore),
            f"/accounts/login/?next={add_chore}",
        )


class HouseholdMembershipTests(HouseholdFixturesMixin, TransactionTestCase):
    def test_two_members_allowed(self):
        self.assertEqual(self.household.members.count(), 2)
        self.assertEqual(get_user_household(self.user_a), self.household)
        self.assertEqual(get_user_household(self.user_b), self.household)

    def test_third_member_rejected(self):
        third = User.objects.create_user(username="dana", password="password123")
        with self.assertRaises(ValidationError):
            self.household.members.add(third)
        self.household.refresh_from_db()
        self.assertEqual(self.household.members.count(), 2)
        self.assertFalse(self.household.members.filter(pk=third.pk).exists())

    def test_second_household_membership_rejected(self):
        other = Household.objects.create(name="Oak Avenue")
        with self.assertRaises(ValidationError):
            other.members.add(self.user_a)
        self.assertFalse(other.members.filter(pk=self.user_a.pk).exists())
        self.assertEqual(get_user_household(self.user_a), self.household)
        self.assertEqual(self.user_a.households.count(), 1)

    def test_non_member_forbidden_on_household_required_view(self):
        self.client.login(username="charlie", password="password123")
        response = self.client.post(reverse("generate_week"))
        self.assertEqual(response.status_code, 403)


class HouseholdAdminTests(HouseholdFixturesMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.login(username="admin", password="password123")

    def test_admin_can_create_household_with_two_members(self):
        user_c = User.objects.create_user(username="cara", password="password123")
        user_d = User.objects.create_user(username="drew", password="password123")
        response = self.client.post(
            "/admin/chores/household/add/",
            {
                "name": "Pine Road",
                "members": [user_c.pk, user_d.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        household = Household.objects.get(name="Pine Road")
        self.assertEqual(set(household.members.all()), {user_c, user_d})

    def test_admin_rejects_third_member(self):
        third = User.objects.create_user(username="dana", password="password123")
        response = self.client.post(
            f"/admin/chores/household/{self.household.pk}/change/",
            {
                "name": self.household.name,
                "members": [self.user_a.pk, self.user_b.pk, third.pk],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "at most two members")
        self.assertEqual(self.household.members.count(), 2)
        self.assertFalse(self.household.members.filter(pk=third.pk).exists())

    def test_admin_rejects_member_already_in_another_household(self):
        response = self.client.post(
            "/admin/chores/household/add/",
            {
                "name": "Oak Avenue",
                "members": [self.user_a.pk],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "two households")
        self.assertFalse(Household.objects.filter(name="Oak Avenue").exists())
        self.assertEqual(get_user_household(self.user_a), self.household)
