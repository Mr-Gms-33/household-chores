from django.apps import apps
from django.test import TestCase


class ProjectSmokeTest(TestCase):
    def test_chores_app_is_installed(self):
        self.assertTrue(apps.is_installed("chores"))
