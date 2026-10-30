# AGENTS/v0

Lightweight harness for task-source-based agent work. A task source can be a
GitHub Issue, a local `.ai/issues/<id>.md` file, or both in Hybrid mode.

## Flow

- Task record -> branch/worktree -> role prompt -> scoped work -> verification
  -> commit -> PR when applicable -> reviewer.
- Task records must define Problem, Goal, Scope, Non-goals, Ownership,
  Acceptance Criteria, Test Plan, and Review Focus.
- Workers edit only owned paths. If scope changes, stop and ask the coordinator.
- Task records and PR bodies use the team's default language.
- PRs use `.github/pull_request_template.md` when GitHub workflow is enabled and
  include short Agent Notes.

## Standard Worktrees

Write concrete worktree names in the target project's `AGENTS.md` during setup.
Use this default shape:

| Worktree | Role | Branch style | May edit | May run |
| --- | --- | --- | --- | --- |
| main repo | integration checkout | current branch | no direct implementation on protected branches | project inspection and git status |
| reference worktree | reference + reviewer + coordinator discussion | base branch | no implementation edits | diff and review commands |
| task worktree | worker for one task | task branch | only paths declared by task ownership | focused verification for owned area |

Do not create a permanent test-only worktree by default. Put backend tests in
backend PRs and frontend tests in frontend PRs. Use temporary test/docs
worktrees only for independent fixture, CI, docs, or harness work.

## Worktree Commands

Temporary worker:

```bash
git worktree add ../worker-123 -b agent/123-task-name <base-branch>
cd ../worker-123
codex
```

Refresh the existing reference worktree:

```bash
git -C ../reference-worktree pull --ff-only
```

If an existing branch already exists:

```bash
git worktree add ../worker-123 agent/123-task-name
```

## Role Selection

- Coordinator: issue slicing, ownership, runtime, final PR judgment.
- Backend Worker: backend implementation.
- Frontend Worker: frontend implementation.
- Test Docs Worker: tests/docs/harness work, preferably in the implementation worktree.
- Reviewer: diff review only, preferably in the reference worktree.

## Runtime Ownership

Only the worktree named in the target project's `AGENTS.md` owns backend
infra/runtime.

Backend runtime commands:

```bash
<target-project backend runtime command>
```

Frontend workers use the documented backend API endpoint. They may run frontend
runtime commands, but must not run backend infra unless explicitly approved.

## PR Flow

1. Complete `.ai/agents/checklists/pr-ready.md`.
2. Commit with a conventional commit message.
3. Push the branch and open a PR to the base branch when remote PR workflow is
   part of the selected mode.
4. Confirm the PR opened against the intended base/head and links the owning
   task record when applicable.
5. Check task/PR body ordering before publishing: steps, issue links, and review
   notes should be in ascending order when numbered.
6. Wait for CI, CodeRabbit, and Codex review signals when enabled.
7. Inspect automated review comments.
8. Fix valid findings, or document non-actions in Agent Notes.
9. Re-run verification after fixes.
10. Confirm `mergeStateStatus`, `reviewDecision`, and required status checks.
11. Human reviewer/maintainer decides merge.

Useful PR status commands:

```bash
gh pr view <number> --json state,isDraft,baseRefName,headRefName,mergeStateStatus,reviewDecision,statusCheckRollup
gh pr checks <number>
gh pr view <number> --comments
```

If Codex automatic review does not run, request it from a PR comment:

```md
@codex review
```

Keep PRs to one task, one branch, focused changes, and documented verification.
Use squash merge for agent-generated work.

## Agent Notes

Agent Notes are for agent-specific context that does not belong in Summary,
Changes, Verification, Risk, or Review Focus. Keep them short. One line is fine.

Use Agent Notes only for:

- Worktree or prompt context needed to understand agent coordination.
- Intentional non-changes that may look suspicious in review.
- Automated review findings intentionally deferred or judged non-actionable.
- Follow-up task candidates not already listed elsewhere.

If there is no agent-specific context, write `None`.
