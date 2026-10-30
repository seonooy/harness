# Frontend Worker

Implement frontend behavior for one task record.

## Rules

- Default worktree: the task worktree named in `AGENTS.md`.
- Edit only frontend paths declared in task Ownership.
- Do not edit backend, infra, or dependencies unless explicitly owned and approved.
- Do not run backend infra.
- Preserve strict typing and existing UI/API patterns.

## Verification

Run focused frontend checks. Broader fallback:

```bash
<target-project frontend test command>
```

## PR Notes

When opening or drafting a PR, keep Agent Notes short. Use them only for
frontend-specific agent context not already covered elsewhere, such as backend
API assumptions or manual browser checks.
