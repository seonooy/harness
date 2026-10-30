# Setup: GitHub Issue Mode

Use this mode when the target project should share agent tasks through GitHub
Issues and land work through pull requests.

## Install Steps

1. Read `docs/target-project-checklist.md`.
2. Copy `templates/common/.ai/` to the target repo.
3. Copy `templates/github/.github/` to the target repo.
5. Create or update target `AGENTS.md` using `templates/common/AGENTS.md` as the
   shape, then make it concrete for the target project.
6. In target `AGENTS.md`, set task source to GitHub Issues only.
7. In target `AGENTS.md`, include:
   - base branch
   - branch naming convention
   - verification commands
   - runtime/dev server commands
   - ownership boundaries
   - dependency/migration/secret rules
   - review guidelines
8. Keep `.github/ISSUE_TEMPLATE/agent_task.md` and
   `.github/pull_request_template.md` tracked in git.
9. Do not add `.ai/` to `.git/info/exclude` unless the user wants the agent
   harness itself to stay private.

## Target AGENTS.md Task Source Section

Use language like this, adjusted to the project:

```md
## Task Source

This project uses GitHub Issues as the source of truth for agent-sized tasks.

Before implementation:
- read the linked GitHub Issue;
- confirm Problem, Goal, Scope, Non-goals, Ownership, Acceptance Criteria,
  Test Plan, and Review Focus;
- create a task branch from the base branch;
- keep edits inside issue ownership.

When work finishes:
- complete `.ai/agents/checklists/pr-ready.md`;
- open a PR with `.github/pull_request_template.md`;
- link the issue with `Closes #<number>` when the PR completes it.
```

## Future Prompt Examples

```text
AGENTS.md 따라 GitHub Issue #123 진행해줘.
```

```text
AGENTS.md 따라 PR 리뷰해줘.
```

## Verification

After setup, run:

```bash
find .ai .github -maxdepth 3 -type f | sort
```

Expected:
- files exist under `.ai/` and `.github/`;
- a manual scan of generated files finds no leftover setup placeholders.
