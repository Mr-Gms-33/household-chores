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


class ChoreTemplateCrudTests(HouseholdFixturesMixin, TestCase):
    def _other_household_template(self):
        other = Household.objects.create(name="Oak Avenue")
        other.members.add(self.outsider)
        return other, ChoreTemplate.objects.create(
            household=other,
            name="Foreign chore",
            weekday=Weekday.TUESDAY,
            default_assignee=Assignee.PARTNER_A,
        )

    def test_anonymous_template_urls_redirect_to_login(self):
        template = ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
        )
        urls = [
            reverse("template_list"),
            reverse("template_create"),
            reverse("template_edit", args=[template.pk]),
            reverse("template_delete", args=[template.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, f"/accounts/login/?next={url}")
                post = self.client.post(url)
                self.assertRedirects(post, f"/accounts/login/?next={url}")

    def test_non_member_gets_403_on_every_template_url(self):
        template = ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
        )
        self.client.login(username="charlie", password="password123")
        urls = [
            reverse("template_list"),
            reverse("template_create"),
            reverse("template_edit", args=[template.pk]),
            reverse("template_delete", args=[template.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(ChoreTemplate.objects.filter(pk=template.pk).exists())

    def test_home_links_to_templates_when_user_has_household(self):
        self.client.login(username="alice", password="password123")
        response = self.client.get(reverse("home"))
        self.assertContains(response, reverse("template_list"))
        self.client.logout()
        self.client.login(username="charlie", password="password123")
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, reverse("template_list"))

    def test_empty_list_renders_without_error(self):
        self.client.login(username="alice", password="password123")
        response = self.client.get(reverse("template_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No chore templates yet")
        self.assertContains(response, reverse("template_create"))

    def test_list_shows_only_own_household_templates(self):
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
        self._other_household_template()
        self.client.login(username="alice", password="password123")

        response = self.client.get(reverse("template_list"))

        self.assertContains(response, "Vacuum")
        self.assertContains(response, "Monday")
        self.assertContains(response, "Partner A")
        self.assertContains(response, "Trash")
        self.assertContains(response, "Sunday")
        self.assertContains(response, "Unset")
        self.assertNotContains(response, "Foreign chore")
        self.assertNotContains(response, "Either")

    def test_both_members_see_same_templates_and_actions(self):
        template = ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.WEDNESDAY,
            default_assignee=Assignee.PARTNER_B,
        )
        for username in ("alice", "bob"):
            self.client.login(username=username, password="password123")
            response = self.client.get(reverse("template_list"))
            self.assertContains(response, "Vacuum")
            self.assertContains(response, reverse("template_create"))
            self.assertContains(response, reverse("template_edit", args=[template.pk]))
            self.assertContains(response, reverse("template_delete", args=[template.pk]))
            self.assertEqual(self.client.get(reverse("template_create")).status_code, 200)
            self.client.logout()

    def test_member_can_create_template(self):
        self.client.login(username="alice", password="password123")
        response = self.client.get(reverse("template_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Monday")
        self.assertContains(response, "Sunday")
        weekday_choices = list(response.context["form"].fields["weekday"].choices)
        self.assertEqual(
            [label for _value, label in weekday_choices],
            [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ],
        )
        assignee_values = [
            value
            for value, _label in response.context["form"].fields["default_assignee"].choices
        ]
        self.assertNotIn(Assignee.EITHER, assignee_values)

        response = self.client.post(
            reverse("template_create"),
            {
                "name": "Dishes",
                "weekday": str(Weekday.FRIDAY),
                "default_assignee": Assignee.PARTNER_B,
            },
        )
        self.assertRedirects(response, reverse("template_list"))
        template = ChoreTemplate.objects.get(name="Dishes")
        self.assertEqual(template.household, self.household)
        self.assertEqual(template.weekday, Weekday.FRIDAY)
        self.assertEqual(template.default_assignee, Assignee.PARTNER_B)

        listing = self.client.get(reverse("template_list"))
        self.assertContains(listing, "Dishes")
        self.assertContains(listing, "Friday")
        self.assertContains(listing, "Partner B")

    def test_create_with_unset_assignee_stores_blank(self):
        self.client.login(username="alice", password="password123")
        self.client.post(
            reverse("template_create"),
            {
                "name": "Windows",
                "weekday": str(Weekday.SATURDAY),
                "default_assignee": "",
            },
        )
        template = ChoreTemplate.objects.get(name="Windows")
        self.assertEqual(template.default_assignee, "")
        listing = self.client.get(reverse("template_list"))
        self.assertContains(listing, "Unset")
        self.assertNotContains(listing, "Either")

    def test_empty_name_rejected_on_create_and_edit(self):
        self.client.login(username="alice", password="password123")
        create = self.client.post(
            reverse("template_create"),
            {"name": "", "weekday": str(Weekday.MONDAY), "default_assignee": ""},
        )
        self.assertEqual(create.status_code, 200)
        self.assertTrue(create.context["form"].errors)
        self.assertFalse(ChoreTemplate.objects.exists())

        template = ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
        )
        edit = self.client.post(
            reverse("template_edit", args=[template.pk]),
            {"name": "   ", "weekday": str(Weekday.TUESDAY), "default_assignee": ""},
        )
        self.assertEqual(edit.status_code, 200)
        self.assertTrue(edit.context["form"].errors)
        template.refresh_from_db()
        self.assertEqual(template.name, "Vacuum")
        self.assertEqual(template.weekday, Weekday.MONDAY)

    def test_member_can_edit_template(self):
        template = ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
            default_assignee=Assignee.PARTNER_A,
        )
        self.client.login(username="bob", password="password123")
        response = self.client.post(
            reverse("template_edit", args=[template.pk]),
            {
                "name": "Deep vacuum",
                "weekday": str(Weekday.THURSDAY),
                "default_assignee": "",
            },
        )
        self.assertRedirects(response, reverse("template_list"))
        template.refresh_from_db()
        self.assertEqual(template.name, "Deep vacuum")
        self.assertEqual(template.weekday, Weekday.THURSDAY)
        self.assertEqual(template.default_assignee, "")
        listing = self.client.get(reverse("template_list"))
        self.assertContains(listing, "Deep vacuum")
        self.assertContains(listing, "Thursday")
        self.assertContains(listing, "Unset")

    def test_edit_does_not_change_existing_instances(self):
        template = ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
            default_assignee=Assignee.PARTNER_A,
        )
        self.client.login(username="alice", password="password123")
        self.client.post(reverse("generate_week"))
        instance = ChoreInstance.objects.get(template=template)
        original_title = instance.title
        original_date = instance.date
        original_assignee = instance.assignee

        self.client.post(
            reverse("template_edit", args=[template.pk]),
            {
                "name": "Mop floors",
                "weekday": str(Weekday.FRIDAY),
                "default_assignee": Assignee.PARTNER_B,
            },
        )

        instance.refresh_from_db()
        self.assertEqual(instance.title, original_title)
        self.assertEqual(instance.date, original_date)
        self.assertEqual(instance.assignee, original_assignee)

        self.client.post(reverse("generate_week"))
        self.assertEqual(
            ChoreInstance.objects.filter(week_plan__household=self.household).count(),
            1,
        )
        instance.refresh_from_db()
        self.assertEqual(instance.title, "Vacuum")

    def test_get_delete_does_not_remove_template(self):
        template = ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
        )
        self.client.login(username="alice", password="password123")
        response = self.client.get(reverse("template_delete", args=[template.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ChoreTemplate.objects.filter(pk=template.pk).exists())

    def test_post_delete_removes_template_but_keeps_instances(self):
        template = ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
            default_assignee=Assignee.PARTNER_A,
        )
        extra = ChoreTemplate.objects.create(
            household=self.household,
            name="Laundry",
            weekday=Weekday.TUESDAY,
            default_assignee=Assignee.PARTNER_B,
        )
        self.client.login(username="alice", password="password123")
        self.client.post(reverse("generate_week"))
        vacuum = ChoreInstance.objects.get(title="Vacuum")

        response = self.client.post(reverse("template_delete", args=[template.pk]))
        self.assertRedirects(response, reverse("template_list"))
        self.assertFalse(ChoreTemplate.objects.filter(pk=template.pk).exists())
        listing = self.client.get(reverse("template_list"))
        self.assertNotContains(listing, "Vacuum")
        self.assertContains(listing, "Laundry")

        vacuum.refresh_from_db()
        self.assertEqual(vacuum.title, "Vacuum")
        self.assertIsNone(vacuum.template)

        self.client.post(reverse("generate_week"))
        self.assertEqual(
            ChoreInstance.objects.filter(week_plan__household=self.household).count(),
            2,
        )
        self.assertTrue(ChoreInstance.objects.filter(template=extra).exists())
        self.assertEqual(
            ChoreInstance.objects.filter(title="Vacuum").count(),
            1,
        )

    def test_duplicate_names_and_weekdays_are_allowed(self):
        self.client.login(username="alice", password="password123")
        payload = {
            "name": "Vacuum",
            "weekday": str(Weekday.MONDAY),
            "default_assignee": "",
        }
        self.client.post(reverse("template_create"), payload)
        self.client.post(reverse("template_create"), payload)
        self.assertEqual(ChoreTemplate.objects.filter(name="Vacuum").count(), 2)
        listing = self.client.get(reverse("template_list"))
        self.assertContains(listing, "Vacuum", count=2)

    def test_cross_household_edit_and_delete_are_blocked(self):
        own = ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
        )
        other, foreign = self._other_household_template()
        self.client.login(username="alice", password="password123")

        edit_url = reverse("template_edit", args=[foreign.pk])
        delete_url = reverse("template_delete", args=[foreign.pk])
        self.assertIn(self.client.get(edit_url).status_code, (403, 404))
        self.assertIn(
            self.client.post(
                edit_url,
                {
                    "name": "Hacked",
                    "weekday": str(Weekday.WEDNESDAY),
                    "default_assignee": "",
                },
            ).status_code,
            (403, 404),
        )
        self.assertIn(self.client.get(delete_url).status_code, (403, 404))
        self.assertIn(self.client.post(delete_url).status_code, (403, 404))

        foreign.refresh_from_db()
        self.assertEqual(foreign.name, "Foreign chore")
        self.assertEqual(foreign.household, other)
        self.assertTrue(ChoreTemplate.objects.filter(pk=own.pk).exists())

        listing = self.client.get(reverse("template_list"))
        self.assertNotContains(listing, "Foreign chore")

        self.client.post(
            reverse("template_create"),
            {
                "name": "Ours",
                "weekday": str(Weekday.MONDAY),
                "default_assignee": "",
            },
        )
        self.assertFalse(
            ChoreTemplate.objects.filter(household=other, name="Ours").exists()
        )

    def test_other_household_member_cannot_manage_this_household_templates(self):
        template = ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
        )
        other, _foreign = self._other_household_template()
        self.client.login(username="charlie", password="password123")

        listing = self.client.get(reverse("template_list"))
        self.assertEqual(listing.status_code, 200)
        self.assertNotContains(listing, "Vacuum")

        self.client.post(
            reverse("template_create"),
            {
                "name": "Sneaky",
                "weekday": str(Weekday.MONDAY),
                "default_assignee": "",
            },
        )
        self.assertFalse(
            ChoreTemplate.objects.filter(household=self.household, name="Sneaky").exists()
        )
        self.assertTrue(
            ChoreTemplate.objects.filter(household=other, name="Sneaky").exists()
        )

        edit = self.client.post(
            reverse("template_edit", args=[template.pk]),
            {
                "name": "Stolen",
                "weekday": str(Weekday.SUNDAY),
                "default_assignee": Assignee.PARTNER_B,
            },
        )
        self.assertIn(edit.status_code, (403, 404))
        delete = self.client.post(reverse("template_delete", args=[template.pk]))
        self.assertIn(delete.status_code, (403, 404))
        template.refresh_from_db()
        self.assertEqual(template.name, "Vacuum")
        self.assertEqual(template.household, self.household)


class WeeklyBoardTests(HouseholdFixturesMixin, TestCase):
    def _make_week_plan(self, household=None):
        household = household or self.household
        return WeekPlan.objects.create(household=household, week_start=self.week_start)

    def _make_instance(self, week_plan=None, template=None, **kwargs):
        week_plan = week_plan or self._make_week_plan()
        defaults = {
            "title": "Vacuum",
            "date": self.week_start,
            "assignee": Assignee.EITHER,
        }
        defaults.update(kwargs)
        return ChoreInstance.objects.create(
            week_plan=week_plan, template=template, **defaults
        )

    def test_home_links_to_board(self):
        self.client.login(username="alice", password="password123")
        response = self.client.get(reverse("home"))
        self.assertContains(response, reverse("board"))

    def test_board_requires_login(self):
        board_url = reverse("board")
        response = self.client.get(board_url)
        self.assertRedirects(response, f"/accounts/login/?next={board_url}")

    def test_action_urls_require_login(self):
        instance = self._make_instance()
        assignee_url = reverse("board_chore_assignee", args=[instance.pk])
        move_url = reverse("board_chore_move", args=[instance.pk])
        for url in (assignee_url, move_url):
            with self.subTest(url=url):
                response = self.client.post(url)
                self.assertRedirects(response, f"/accounts/login/?next={url}")

    def test_non_member_gets_clear_message_not_500(self):
        self.client.login(username="charlie", password="password123")
        response = self.client.get(reverse("board"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not a member of a household")

    def test_non_member_gets_403_on_actions(self):
        instance = self._make_instance()
        self.client.login(username="charlie", password="password123")
        response = self.client.post(
            reverse("board_chore_assignee", args=[instance.pk]),
            {"assignee": Assignee.PARTNER_A},
        )
        self.assertEqual(response.status_code, 403)

    def test_board_renders_seven_days_with_no_week_plan(self):
        self.client.login(username="alice", password="password123")
        response = self.client.get(reverse("board"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(WeekPlan.objects.exists())
        for offset in range(7):
            day = self.week_start + timedelta(days=offset)
            self.assertContains(response, day.strftime("%A"))
        self.assertContains(response, "No chores for this day.", count=7)

    def test_chores_render_under_correct_day_and_empty_days_still_render(self):
        week_plan = self._make_week_plan()
        self._make_instance(
            week_plan=week_plan, title="Vacuum", date=self.week_start
        )
        self._make_instance(
            week_plan=week_plan,
            title="Trash",
            date=self.week_start + timedelta(days=6),
        )
        self.client.login(username="alice", password="password123")

        response = self.client.get(reverse("board"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        monday_pos = content.find(self.week_start.strftime("%A"))
        sunday_pos = content.find(
            (self.week_start + timedelta(days=6)).strftime("%A")
        )
        vacuum_pos = content.find("Vacuum")
        trash_pos = content.find("Trash")
        self.assertTrue(monday_pos < vacuum_pos < sunday_pos)
        self.assertTrue(sunday_pos < trash_pos)
        # Five empty days remain in between.
        self.assertContains(response, "No chores for this day.", count=5)

    def test_chores_within_a_day_are_in_stable_order(self):
        week_plan = self._make_week_plan()
        first = self._make_instance(week_plan=week_plan, title="Bravo")
        second = self._make_instance(week_plan=week_plan, title="Alpha")
        self.client.login(username="alice", password="password123")

        response = self.client.get(reverse("board"))
        content = response.content.decode()
        self.assertTrue(content.find("Alpha") < content.find("Bravo"))
        self.assertEqual(list(response.context["days"][0]["chores"]), [
            {
                "instance": second,
                "assignee_form": response.context["days"][0]["chores"][0][
                    "assignee_form"
                ],
                "move_form": response.context["days"][0]["chores"][0]["move_form"],
            },
            {
                "instance": first,
                "assignee_form": response.context["days"][0]["chores"][1][
                    "assignee_form"
                ],
                "move_form": response.context["days"][0]["chores"][1]["move_form"],
            },
        ])

    def test_board_shows_title_and_assignee(self):
        self._make_instance(title="Vacuum", assignee=Assignee.PARTNER_A)
        self.client.login(username="alice", password="password123")

        response = self.client.get(reverse("board"))

        self.assertContains(response, "Vacuum")
        self.assertContains(response, "Partner A")

    def test_update_assignee_persists_and_reloads_under_same_day(self):
        instance = self._make_instance(assignee=Assignee.EITHER)
        self.client.login(username="alice", password="password123")

        response = self.client.post(
            reverse("board_chore_assignee", args=[instance.pk]),
            {"assignee": Assignee.PARTNER_B},
        )
        self.assertRedirects(response, reverse("board"))
        instance.refresh_from_db()
        self.assertEqual(instance.assignee, Assignee.PARTNER_B)

        board = self.client.get(reverse("board"))
        self.assertContains(board, "Partner B")

    def test_move_within_current_week_persists_and_updates_grouping(self):
        instance = self._make_instance(date=self.week_start)
        new_date = self.week_start + timedelta(days=3)
        self.client.login(username="alice", password="password123")

        response = self.client.post(
            reverse("board_chore_move", args=[instance.pk]),
            {"date": new_date.isoformat()},
        )
        self.assertRedirects(response, reverse("board"))
        instance.refresh_from_db()
        self.assertEqual(instance.date, new_date)

        board = self.client.get(reverse("board"))
        content = board.content.decode()
        old_day_heading = self.week_start.strftime("%A")
        new_day_heading = new_date.strftime("%A")
        # Chore title should now appear after the new day's heading and
        # before the next day's heading (or end of days), not under Monday.
        old_section_end = content.find(
            (self.week_start + timedelta(days=1)).strftime("%A")
        )
        self.assertNotIn(instance.title, content[:old_section_end])
        self.assertGreater(content.find(new_day_heading), -1)

    def test_move_rejects_out_of_week_date(self):
        instance = self._make_instance(date=self.week_start)
        outside = self.week_start - timedelta(days=1)
        self.client.login(username="alice", password="password123")

        response = self.client.post(
            reverse("board_chore_move", args=[instance.pk]),
            {"date": outside.isoformat()},
        )

        self.assertEqual(response.status_code, 400)
        instance.refresh_from_db()
        self.assertEqual(instance.date, self.week_start)

    def test_update_rejects_invalid_assignee(self):
        instance = self._make_instance(assignee=Assignee.EITHER)
        self.client.login(username="alice", password="password123")

        response = self.client.post(
            reverse("board_chore_assignee", args=[instance.pk]),
            {"assignee": "not_a_real_assignee"},
        )

        self.assertEqual(response.status_code, 400)
        instance.refresh_from_db()
        self.assertEqual(instance.assignee, Assignee.EITHER)

    def test_cross_household_chore_returns_404_on_actions(self):
        other = Household.objects.create(name="Oak Avenue")
        other.members.add(self.outsider)
        other_plan = self._make_week_plan(household=other)
        foreign = self._make_instance(week_plan=other_plan, title="Foreign")
        self.client.login(username="alice", password="password123")

        assignee_response = self.client.post(
            reverse("board_chore_assignee", args=[foreign.pk]),
            {"assignee": Assignee.PARTNER_A},
        )
        move_response = self.client.post(
            reverse("board_chore_move", args=[foreign.pk]),
            {"date": self.week_start.isoformat()},
        )

        self.assertEqual(assignee_response.status_code, 404)
        self.assertEqual(move_response.status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.assignee, Assignee.EITHER)

    def test_chore_from_non_current_week_plan_returns_404(self):
        old_week_start = self.week_start - timedelta(days=7)
        old_plan = WeekPlan.objects.create(
            household=self.household, week_start=old_week_start
        )
        old_instance = self._make_instance(
            week_plan=old_plan, title="Old chore", date=old_week_start
        )
        self.client.login(username="alice", password="password123")

        response = self.client.post(
            reverse("board_chore_assignee", args=[old_instance.pk]),
            {"assignee": Assignee.PARTNER_A},
        )

        self.assertEqual(response.status_code, 404)

    def test_move_or_update_never_changes_template(self):
        template = ChoreTemplate.objects.create(
            household=self.household,
            name="Vacuum",
            weekday=Weekday.MONDAY,
            default_assignee=Assignee.PARTNER_A,
        )
        week_plan = self._make_week_plan()
        instance = self._make_instance(
            week_plan=week_plan,
            template=template,
            title="Vacuum",
            date=self.week_start,
            assignee=Assignee.PARTNER_A,
        )
        self.client.login(username="alice", password="password123")

        self.client.post(
            reverse("board_chore_assignee", args=[instance.pk]),
            {"assignee": Assignee.PARTNER_B},
        )
        self.client.post(
            reverse("board_chore_move", args=[instance.pk]),
            {"date": (self.week_start + timedelta(days=2)).isoformat()},
        )

        template.refresh_from_db()
        self.assertEqual(template.weekday, Weekday.MONDAY)
        self.assertEqual(template.default_assignee, Assignee.PARTNER_A)

    def test_get_requests_to_action_urls_do_not_mutate(self):
        instance = self._make_instance(
            assignee=Assignee.EITHER, date=self.week_start
        )
        self.client.login(username="alice", password="password123")

        assignee_response = self.client.get(
            reverse("board_chore_assignee", args=[instance.pk])
        )
        move_response = self.client.get(
            reverse("board_chore_move", args=[instance.pk])
        )

        self.assertIn(assignee_response.status_code, (302, 405))
        self.assertIn(move_response.status_code, (302, 405))
        instance.refresh_from_db()
        self.assertEqual(instance.assignee, Assignee.EITHER)
        self.assertEqual(instance.date, self.week_start)

    def test_move_select_only_offers_current_week_dates(self):
        instance = self._make_instance()
        self.client.login(username="alice", password="password123")

        response = self.client.get(reverse("board"))

        move_form = response.context["days"][0]["chores"][0]["move_form"]
        offered_dates = [value for value, _label in move_form.fields["date"].choices]
        expected_dates = [
            (self.week_start + timedelta(days=i)).isoformat() for i in range(7)
        ]
        self.assertEqual(offered_dates, expected_dates)


class ChoreCompletionTests(HouseholdFixturesMixin, TestCase):
    def _make_week_plan(self, household=None):
        household = household or self.household
        return WeekPlan.objects.create(household=household, week_start=self.week_start)

    def _make_instance(self, week_plan=None, template=None, **kwargs):
        week_plan = week_plan or self._make_week_plan()
        defaults = {
            "title": "Vacuum",
            "date": self.week_start,
            "assignee": Assignee.EITHER,
        }
        defaults.update(kwargs)
        return ChoreInstance.objects.create(
            week_plan=week_plan, template=template, **defaults
        )

    def test_toggle_marks_chore_complete_and_redirects_to_board(self):
        instance = self._make_instance(complete=False)
        self.client.login(username="alice", password="password123")

        response = self.client.post(
            reverse("board_chore_toggle", args=[instance.pk])
        )

        self.assertRedirects(response, reverse("board"))
        instance.refresh_from_db()
        self.assertTrue(instance.complete)

        board = self.client.get(reverse("board"))
        self.assertContains(board, "Completed")

    def test_toggle_marks_complete_chore_back_to_incomplete(self):
        instance = self._make_instance(complete=True)
        self.client.login(username="alice", password="password123")

        response = self.client.post(
            reverse("board_chore_toggle", args=[instance.pk])
        )

        self.assertRedirects(response, reverse("board"))
        instance.refresh_from_db()
        self.assertFalse(instance.complete)

    def test_chore_stays_visible_under_original_day_after_toggle(self):
        instance = self._make_instance(complete=False, date=self.week_start)
        self.client.login(username="alice", password="password123")

        self.client.post(reverse("board_chore_toggle", args=[instance.pk]))
        board = self.client.get(reverse("board"))
        content = board.content.decode()

        monday_pos = content.find(self.week_start.strftime("%A"))
        tuesday_pos = content.find(
            (self.week_start + timedelta(days=1)).strftime("%A")
        )
        vacuum_pos = content.find(instance.title)
        self.assertTrue(monday_pos < vacuum_pos < tuesday_pos)

    def test_summary_reflects_zero_done(self):
        week_plan = self._make_week_plan()
        self._make_instance(week_plan=week_plan, title="A", complete=False)
        self._make_instance(week_plan=week_plan, title="B", complete=False)
        self.client.login(username="alice", password="password123")

        response = self.client.get(reverse("board"))

        self.assertEqual(response.context["done_count"], 0)
        self.assertEqual(response.context["total_count"], 2)
        self.assertContains(response, "0 / 2")

    def test_summary_reflects_some_done(self):
        week_plan = self._make_week_plan()
        self._make_instance(week_plan=week_plan, title="A", complete=True)
        self._make_instance(week_plan=week_plan, title="B", complete=False)
        self.client.login(username="alice", password="password123")

        response = self.client.get(reverse("board"))

        self.assertEqual(response.context["done_count"], 1)
        self.assertEqual(response.context["total_count"], 2)
        self.assertContains(response, "1 / 2")

    def test_summary_reflects_all_done(self):
        week_plan = self._make_week_plan()
        self._make_instance(week_plan=week_plan, title="A", complete=True)
        self._make_instance(week_plan=week_plan, title="B", complete=True)
        self.client.login(username="alice", password="password123")

        response = self.client.get(reverse("board"))

        self.assertEqual(response.context["done_count"], 2)
        self.assertEqual(response.context["total_count"], 2)
        self.assertContains(response, "2 / 2")

    def test_summary_is_zero_zero_with_no_week_plan(self):
        self.client.login(username="alice", password="password123")

        response = self.client.get(reverse("board"))

        self.assertEqual(response.context["done_count"], 0)
        self.assertEqual(response.context["total_count"], 0)
        self.assertContains(response, "0 / 0")

    def test_summary_updates_immediately_after_toggle_redirect(self):
        week_plan = self._make_week_plan()
        instance = self._make_instance(
            week_plan=week_plan, title="A", complete=False
        )
        self._make_instance(week_plan=week_plan, title="B", complete=False)
        self.client.login(username="alice", password="password123")

        response = self.client.post(
            reverse("board_chore_toggle", args=[instance.pk]), follow=True
        )

        self.assertContains(response, "1 / 2")

    def test_any_household_member_can_toggle_any_assignee(self):
        instance = self._make_instance(assignee=Assignee.PARTNER_A, complete=False)
        self.client.login(username="bob", password="password123")

        response = self.client.post(
            reverse("board_chore_toggle", args=[instance.pk])
        )

        self.assertRedirects(response, reverse("board"))
        instance.refresh_from_db()
        self.assertTrue(instance.complete)

    def test_toggle_requires_login(self):
        instance = self._make_instance()
        toggle_url = reverse("board_chore_toggle", args=[instance.pk])

        response = self.client.post(toggle_url)

        self.assertRedirects(response, f"/accounts/login/?next={toggle_url}")

    def test_non_member_gets_403_on_toggle(self):
        instance = self._make_instance()
        self.client.login(username="charlie", password="password123")

        response = self.client.post(
            reverse("board_chore_toggle", args=[instance.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_cross_household_chore_returns_404_on_toggle(self):
        other = Household.objects.create(name="Oak Avenue")
        other.members.add(self.outsider)
        other_plan = self._make_week_plan(household=other)
        foreign = self._make_instance(
            week_plan=other_plan, title="Foreign", complete=False
        )
        self.client.login(username="alice", password="password123")

        response = self.client.post(
            reverse("board_chore_toggle", args=[foreign.pk])
        )

        self.assertEqual(response.status_code, 404)
        foreign.refresh_from_db()
        self.assertFalse(foreign.complete)

    def test_chore_from_non_current_week_plan_returns_404_on_toggle(self):
        old_week_start = self.week_start - timedelta(days=7)
        old_plan = WeekPlan.objects.create(
            household=self.household, week_start=old_week_start
        )
        old_instance = self._make_instance(
            week_plan=old_plan,
            title="Old chore",
            date=old_week_start,
            complete=False,
        )
        self.client.login(username="alice", password="password123")

        response = self.client.post(
            reverse("board_chore_toggle", args=[old_instance.pk])
        )

        self.assertEqual(response.status_code, 404)
        old_instance.refresh_from_db()
        self.assertFalse(old_instance.complete)

    def test_get_request_to_toggle_does_not_mutate_and_redirects(self):
        instance = self._make_instance(complete=False)
        self.client.login(username="alice", password="password123")

        response = self.client.get(
            reverse("board_chore_toggle", args=[instance.pk])
        )

        self.assertRedirects(response, reverse("board"))
        instance.refresh_from_db()
        self.assertFalse(instance.complete)
