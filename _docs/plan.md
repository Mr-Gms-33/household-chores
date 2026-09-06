# Household Chores — Project Plan

## Problem

Couples need a simple way to **plan household chores across the week** so nothing falls through the cracks.

## Users

- Two partners in one household
- Both plan and execute chores together

## Core workflow

1. **Define templates** — recurring chores (e.g. vacuum every Tuesday, trash every Sunday)
2. **Plan the week together** — drag/drop or pick tasks for each day; adjust templates as needed
3. **Assign tasks** — mix of:
   - assigned to one partner for the week
   - open / shared (“whoever gets to it”)
4. **Track during the week** — mark chores done, see progress

## Scope decisions

| Topic | Decision |
|-------|----------|
| Primary goal | Weekly planning |
| Schedule building | Collaborative planning (not auto-rotation) |
| Chore types | Recurring templates + weekly tweaks |
| During the week | Full completion tracking with progress |
| Assignment | Mixed: some assigned, some flexible |

## Out of scope (for now)

- Kids / parental assignment flows
- Roommate-specific features
- Fixed auto-rotation without manual planning
- Plan-only mode without check-offs

## Open questions

- [ ] Show workload balance while planning? (counts, fairness view, or none)
- [ ] Platform: web app, mobile, or both?
- [ ] Notifications / reminders?
- [ ] History and stats beyond the current week?

## MVP feature list (draft)

- Household with two users
- Chore templates (name, recurrence, default assignee optional)
- Weekly board or calendar view for planning
- Per-chore assignment: partner A, partner B, or either
- Mark complete / incomplete
- Weekly progress summary

## Next steps

1. Finalize open questions above
2. Sketch UI (weekly planner + task list)
3. Choose stack and data model
4. Build MVP
