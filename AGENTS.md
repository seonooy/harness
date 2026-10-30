# AGENTS.md

## Purpose

This repository is an **agent harness setup kit**. It is meant to be read by an
agent from another project and used to install a project-specific harness there.

Do not treat this directory as the target project. The target project is the
current working directory where the user invoked the agent, unless the user gives
a different path.

## Install Workflow

When a user says something like:

```text
~/h 보고 이 프로젝트에 셋업해줘
```

do this:

1. Read this file and `README.md`.
2. Inspect the target project:
   - `pwd`
   - `git status --short --branch` if it is a git repo
   - root docs such as `README.md`, `AGENTS.md`
   - package/build/test files such as `pyproject.toml`, `package.json`,
     `Cargo.toml`, `go.mod`, `Makefile`, `docker-compose.yml`
3. Pick or confirm one harness mode:
   - **GitHub Issue mode**: shared repo workflow, GitHub Issues and PRs are the
     source of truth.
   - **Local AI Issue mode**: personal/local workflow, `.ai/tasks.md` and
     `.ai/issues/` are the source of truth and are excluded from git.
   - **Hybrid mode**: public/shared work uses GitHub Issues, personal agent
     planning and experiments use local `.ai/issues/`.
4. Read the matching setup guide in `docs/`.
5. Copy only the files needed for the selected mode from `templates/`.
6. Write the target project's `AGENTS.md` as a finished project-specific file.
   Do not leave placeholder tokens. Infer concrete commands and paths from the
   target repo, and ask only when the choice is risky or unknowable.
8. Report exactly what files changed and how to use the harness next.

## Mode Selection Defaults

- If the project already uses GitHub Issues/PR automation and should share agent
  tasks with collaborators, use **GitHub Issue mode**.
- If the project is a team repo but the user wants a private personal agent
  harness that should not be committed, use **Local AI Issue mode**.
- If both shared PR workflow and private planning are useful, use **Hybrid mode**.

## Safety Rules

- Do not push, fetch, pull, or change remotes unless the user explicitly asks.
- Do not overwrite an existing `AGENTS.md`, `.ai/`, or `.github/`
  without reading it first and preserving useful project-specific content.
- In Local AI Issue mode, update `.git/info/exclude`; do not rely only on
  `.gitignore`.
- Do not commit local-only harness files unless the selected mode intentionally
  tracks them.
- Keep generated target docs short enough for future agents to actually read.

## Template Map

- `templates/common/`: files shared by all modes.
- `templates/github/`: GitHub Issue and PR templates.
- `templates/local-ai/`: local issue tab, issue file template, and exclude snippet.
- `docs/setup-github-issue-mode.md`: shared GitHub workflow setup.
- `docs/setup-local-ai-mode.md`: private local `.ai` workflow setup.
- `docs/setup-hybrid-mode.md`: combined workflow setup.
- `docs/target-project-checklist.md`: inspection checklist for setup agents.
