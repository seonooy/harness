# Setup: Hybrid Mode

Use this mode when the project needs both shared GitHub Issue workflow and a
private local `.ai` issue tracker.

## Intended Split

- GitHub Issues: shared implementation work, PR tracking, collaborator-visible
  bugs/features.
- Local `.ai/issues/`: private planning, spikes, agent coordination, personal
  queues, and unshared experiment notes.

## Install Steps

1. Read `docs/target-project-checklist.md`.
2. Follow `docs/setup-github-issue-mode.md` for common files and `.github/`.
3. Follow `docs/setup-local-ai-mode.md` for `.ai/tasks.md`, `.ai/issues/`, and
   `.git/info/exclude`.
4. Write explicit precedence rules in target `AGENTS.md`.
5. If a local issue becomes shared implementation work, create or link a GitHub
   Issue and record that link in the local issue file.

## Target AGENTS.md Task Source Section

Use language like this, adjusted to the project:

```md
## Task Source

This project uses Hybrid mode.

Shared source of truth:
- GitHub Issues and PRs are authoritative for work that will be shared with
  collaborators or merged through remote PRs.

Local source of truth:
- `.ai/tasks.md` and `.ai/issues/*.md` are private planning and agent workflow
  records. They are excluded through `.git/info/exclude`.

Precedence:
- If a GitHub Issue and local `.ai` issue conflict, ask before implementing.
- If the work will affect shared code, prefer or create a GitHub Issue before
  opening a PR.
- Local `.ai` issues may track spikes, decomposition, or private next actions
  that are not ready for GitHub.
```

## Future Prompt Examples

```text
AGENTS.md 따라 hybrid mode로 시작해줘. GitHub 이슈랑 .ai/tasks 둘 다 보고 충돌 있으면 알려줘.
```

```text
.ai/issues/0002 내용을 GitHub Issue로 승격할지 판단해줘.
```

## Verification

After setup, run:

```bash
find .ai .github -maxdepth 3 -type f | sort
git status --short -- AGENTS.md .ai .github
```

Expected:
- GitHub templates exist;
- local `.ai/tasks.md` and `.ai/issues/` exist;
- a manual scan of generated files finds no leftover setup placeholders;
- local-only files are excluded if that is the selected policy.
