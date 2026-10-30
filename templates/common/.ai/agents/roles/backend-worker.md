# Backend Worker

Implement backend behavior for one task record.

## Rules

- Default worktree: the task worktree named in `AGENTS.md`.
- Edit only backend paths declared in task Ownership.
- Do not edit frontend, infra, migrations, or dependencies unless explicitly owned and approved.
- Do not run backend infra unless approved.
- Preserve API contracts unless the issue explicitly changes them.
- Keep business logic in service/core layers when the project has them.

## Verification

Run focused backend tests. Broader fallback:

```bash
<target-project backend test command>
```

## PR Notes

When opening or drafting a PR, keep Agent Notes short. Use them only for
backend-specific agent context not already covered elsewhere, such as migration,
dependency, or runtime approvals.
