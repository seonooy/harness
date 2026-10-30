# Git Convention

## Branches

- `main`: stable/release branch.
- The target project's base branch is defined in its `AGENTS.md`.
- Never push directly to protected branches.
- Branch from the target project's base branch for new work.

## Task Records

- Prefer creating or selecting a task record before work starts.
- A task record can be a GitHub Issue or local `.ai/issues/<id>.md` file.
- One task should map to one focused PR when practical.
- In GitHub Issue mode, link PRs with `Closes #<number>` when the PR completes the issue.
- In Local AI Issue mode, update the local issue progress log and `.ai/tasks.md`
  status instead of pretending there is a GitHub Issue.

## Branch Names

Use short lowercase names:

```text
feat/task-name
fix/task-name
docs/task-name
refactor/task-name
chore/task-name
```

## Commits

Prefer conventional commits:

```text
feat:
fix:
docs:
refactor:
chore:
test:
```

## Pull Requests

- Target the base branch named in the target project's `AGENTS.md`.
- Use `.github/pull_request_template.md`.
- Include verification commands and results.
- Keep Agent Notes short or `None`.
- Wait for CI and automated reviews when configured.
- Human reviewer/maintainer decides merge.
