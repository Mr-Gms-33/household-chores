from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("week/generate/", views.generate_week, name="generate_week"),
    path("week/add-chore/", views.add_chore, name="add_chore"),
]
