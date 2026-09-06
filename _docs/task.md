# Household Chores — Tasks

Django web app for two partners to plan and track weekly household chores.

Each task is one session. Each description is enough to start without reading the others.

**MVP scope:** household + login, recurring templates, generate and adjust a weekly plan, assign chores, mark done, simple progress count. Not in MVP: notifications, history beyond the current week, workload/fairness views, drag-and-drop, invite links, or mobile.

---

## 1. Auth and household
Goal: Two partners can log in and share one household; everyone else is kept out.
Description: Add a `Household` model and link Django users to it (max two members per household for now). Wire login, logout, and a simple home page that requires authentication. Scope all future data to the signed-in user’s household. Tests should cover creating a household with two members, logging in, and confirming a third user is not treated as a member.

---

## 2. Chore templates
Goal: Partners can manage recurring chores for their household.
Description: Add a `ChoreTemplate` model (name, weekday, optional default assignee: partner A, partner B, or unset) tied to a household. Build list, create, edit, and delete pages scoped to the logged-in household; register models in admin for debugging. Tests should cover creating a template, editing it, deleting it, and blocking access to another household’s templates.

---

## 3. Generate a weekly plan
Goal: One action creates this week’s planned chores from templates, with room for one-off tasks.
Description: Add `WeekPlan` (household + week start date) and `ChoreInstance` (title, date, assignee, complete flag, optional link to template). Provide a “generate this week” action that creates instances from templates on the matching weekday without duplicating if run twice. Add a form to insert a one-off chore on a chosen day. Tests should cover generation from templates, idempotent re-generation, and adding an extra chore.

---

## 4. Weekly board and planning
Goal: Partners see the week and adjust who does what and when.
Description: Render the current week as seven day columns (or a list grouped by day) showing each `ChoreInstance`. From the board, let members change assignee (partner A, partner B, or either) and move a chore to another day in the same week—simple forms are fine; drag-and-drop is not required. Only household members may view or change the plan. Tests should cover viewing chores on the correct day, updating assignee, and moving a chore.

---

## 5. Track completion and progress
Goal: During the week, partners check chores off and see how much is left.
Description: Add a complete/incomplete toggle on each chore on the weekly board. Show a summary for the week: done count vs total (e.g. “4 / 12”). Persist changes immediately. Tests should cover marking complete, undoing it, summary counts updating, and blocking a non-member from toggling chores.
