# AGENTS.md

## Project

This repository uses an agent harness. Before assuming current behavior, inspect
the relevant source, task record, and `.ai/` guidance.

When installing this file into a real project, make this section concrete:
- project name and purpose;
- project type, language, runtime, and package manager;
- public API/schema/data boundaries;
- areas that need explicit approval before change.

## Task Source

Set this section during setup.

Supported policies:
- GitHub Issue mode: GitHub Issues are the source of truth.
- Local AI Issue mode: `.ai/tasks.md` and `.ai/issues/*.md` are the source of truth.
- Hybrid mode: GitHub Issues are shared truth; local `.ai/issues/` is private
  planning and agent coordination.

Do not begin implementation until the selected task source is read and the work
has clear ownership, acceptance criteria, and a verification plan.

## Agent Workflow

At session start:

- Read `AGENTS.md`.
- Read the selected task source.
- Run `pwd`, `git branch --show-current`, and `git status --short --branch`.
- Confirm branch, ownership, and verification plan.
- For worktree workflow, read `.ai/agents/README.md`.

When work finishes or a decision changes, update the selected task source:
- GitHub Issue mode: update the GitHub Issue or PR.
- Local AI Issue mode: update the matching `.ai/issues/<id>.md`; update
  `.ai/tasks.md` only if status, priority, or issue list changes.
- Hybrid mode: update whichever source owns the work; ask if sources conflict.

## Worktrees

Use a task branch or task worktree before implementation. Keep one reference
worktree on the base branch when doing review or comparison.

Default pattern:

- main repo: integration checkout.
- reference worktree: latest base branch, review only, no implementation edits.
- task worktree: one unit of work, branch from base, edit only owned paths.

Replace this section during setup with concrete local worktree names if the
target project uses stable worktrees.

## Local Commands

Fill this section during setup by inspecting the target project.

Verification examples to replace with concrete commands:

```bash
pytest
npm test
cargo test
go test ./...
```

Runtime examples to replace with concrete commands:

```bash
npm run dev
uv run python -m package
docker compose up
```

## Rules

- Follow existing code patterns before introducing new structure.
- Keep work inside task ownership; stop and ask before editing outside scope.
- Ask before migrations, dependency changes, vendored code changes, or build
  system changes.
- Do not commit `.env`, secrets, generated uploads, local artifacts, or
  environment-specific paths.
- Preserve public API, schema, database, and serialized data contracts unless
  the task explicitly owns the change.
- Run relevant verification before claiming done; document commands and results
  in the task record or PR.
- Do not push directly to protected branches; use PRs when remote collaboration
  is part of the selected mode.

## Git

- Branch from the target project's base branch for new work.
- Use small changes tied to one task record.
- Prefer conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`,
  `test:`.
- Write task and PR bodies in the team's default language.
- PRs should include Summary, Why, Changes, Verification, Risk, Review Focus,
  Linked Issue when applicable, and Agent Notes.

## Review Guidelines

- Focus on real bugs, behavioral regressions, missing tests, security issues,
  API/schema contract breaks, and scope creep.
- Check ownership boundaries and runtime assumptions.
- Ignore style-only comments unless they hide a correctness or maintainability
  issue.

## Reference Docs

- `.ai/agents/` - agent workflow, roles, prompts, checklists.
- `.ai/rules/` - detailed local project rules.
- `.github/` - GitHub Issue and PR templates when GitHub Issue mode is used.
