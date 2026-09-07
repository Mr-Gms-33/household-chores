from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("week/generate/", views.generate_week, name="generate_week"),
    path("week/add-chore/", views.add_chore, name="add_chore"),
    path("board/", views.board, name="board"),
    path(
        "board/chores/<int:pk>/assignee/",
        views.board_chore_assignee,
        name="board_chore_assignee",
    ),
    path(
        "board/chores/<int:pk>/move/",
        views.board_chore_move,
        name="board_chore_move",
    ),
    path("templates/", views.template_list, name="template_list"),
    path("templates/new/", views.template_create, name="template_create"),
    path("templates/<int:pk>/edit/", views.template_edit, name="template_edit"),
    path("templates/<int:pk>/delete/", views.template_delete, name="template_delete"),
]
