# Setup: Local AI Issue Mode

Use this mode when the user wants a personal/local agent harness that should
not be committed to the target repository.

## Install Steps

1. Read `docs/target-project-checklist.md`.
2. Copy `templates/common/.ai/` to the target repo.
3. Copy `templates/local-ai/.ai/tasks.md` to target `.ai/tasks.md`.
4. Copy `templates/local-ai/.ai/issues/0000-issue-template.md` to target
   `.ai/issues/0000-issue-template.md`.
6. Create or update target `AGENTS.md` using `templates/common/AGENTS.md` as the
   shape, then make it concrete for the target project.
7. In target `AGENTS.md`, set task source to local `.ai` issues only.
8. Add the snippet from `templates/local-ai/snippets/git-info-exclude.txt` to
   target `.git/info/exclude`.
9. If the repo already has tracked `.github/` templates, leave them alone unless
   the user asks to change GitHub workflow.

## Target AGENTS.md Task Source Section

Use language like this, adjusted to the project:

```md
## Task Source

This project uses a local personal issue tracker instead of GitHub Issues for
agent-sized work.

Source of truth:
- `.ai/tasks.md`: short issue tab / active backlog index.
- `.ai/issues/*.md`: one issue per file with Problem, Goal, Scope, Non-goals,
  Ownership, Acceptance Criteria, Test Plan, Review Focus, and Progress Log.

Before implementation:
- read `.ai/tasks.md`;
- read the selected `.ai/issues/<id>.md`;
- confirm branch, ownership, and verification plan;
- keep edits inside issue ownership.

When work finishes or a decision changes:
- update the matching `.ai/issues/<id>.md`;
- update `.ai/tasks.md` only if status, priority, or issue list changes.

The local harness files are excluded through `.git/info/exclude` and should not
be pushed unless the user explicitly changes that policy.
```

## Future Prompt Examples

```text
AGENTS.md 따라 .ai/tasks.md 읽고 다음 작업 후보 보여줘.
```

```text
AGENTS.md 따라 .ai/issues/0001-example.md 진행해줘.
```

## Verification

After setup, run:

```bash
find .ai -maxdepth 3 -type f | sort
git status --short -- AGENTS.md .ai .github
```

Expected:
- `.ai/tasks.md` and `.ai/issues/0000-issue-template.md` exist;
- a manual scan of generated files finds no leftover setup placeholders;
- local-only files do not appear in `git status` after `.git/info/exclude` is
  updated.
