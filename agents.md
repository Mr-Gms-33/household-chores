# Agents

## Commands

- `python -m venv .venv` — create a virtual environment (once)
- `.\.venv\Scripts\Activate.ps1` — activate the venv (PowerShell)
- `pip install -r requirements.txt` — install dependencies
- `python manage.py migrate` — apply database migrations
- `python manage.py test` — run the whole test suite
- `python manage.py test chores` — run tests for the chores app
- `python manage.py test chores.tests.ProjectSmokeTest` — run one test class
- `python manage.py runserver` — start the dev server

## Rules

- Dependencies are added in `requirements.txt`. Do not add one without asking.
