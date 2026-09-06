# Household Chores

A shared tool for couples to plan weekly household chores together, track completion, and stay organized.

## Status

Early planning — see [`_docs/plan.md`](_docs/plan.md) for scope and feature decisions.

## Goals

- Plan chores together for the week (drag/drop or pick tasks per day)
- Use recurring templates with weekly adjustments
- Track completion and see progress during the week
- Support mixed assignment (some tasks assigned, some open to either partner)

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/
