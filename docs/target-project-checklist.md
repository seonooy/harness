# Target Project Checklist

Use this before installing the harness into a target repository.

## Identify Target

- Current directory from `pwd`
- Git repo state from `git status --short --branch`
- Base branch from `git branch --show-current` and existing branch policy
- Whether the target should track harness files in git

## Read Existing Instructions

- `AGENTS.md`
- `README.md`
- `.github/` templates
- existing `.ai/` or docs for agent workflow

Preserve useful project-specific rules. Do not replace them with generic harness
rules unless they conflict with the selected workflow.

## Infer Project Facts

Look for:

- language and framework
- package manager
- test commands
- lint/typecheck commands
- runtime/dev server commands
- generated output directories
- secret/env conventions
- public API or schema files
- migrations/dependency boundaries
- frontend/backend split
- existing CI commands

## Choose Harness Mode

- GitHub Issue mode: shared issue/PR workflow.
- Local AI Issue mode: personal local harness excluded from git.
- Hybrid mode: both, with explicit precedence.

If unclear, ask one concise question:

```text
이 하네스는 GitHub Issue 공유용, 로컬 개인 .ai 이슈용, 아니면 둘 다 쓰는 hybrid 중 뭐로 둘까?
```

## 검사 칸 조사

검사 키트(`docs/setup-checks.md`)를 들일 때 먼저 본다. 확인한 것은 설치 보고에 적는다.

- **언어·프레임워크:** 조각이 있는지 본다(1차는 python + layered). 패키지 루트(`pyproject.toml`이 있는 폴더)와
  최상위 패키지 이름.
- **기존 검사 설정:** Ruff·mypy·pytest·import-linter 설정과 버전, `Makefile`, pre-commit, CI 워크플로.
  이미 있는 도구는 그 프로젝트가 고정한 버전을 venv에서 바로 실행한다(`.venv/bin/python -m ...`). `uv run`은
  단계 명령에 쓰지 않는다. `--locked`면 낡은 venv를 맞추며 설치하고, `--no-sync`여도 없는 venv를 만든다.
  venv의 Python이 프로젝트가 정한 버전(`.python-version`, `requires-python`)과 같은지 본다.
- **없는 도구:** mypy·import-linter가 팀 의존성에 없으면 개인 도구 환경을 만들어야 한다. 네트워크를 한 번 쓴다.
- **테스트:** 서비스 없이 도는 빠른 테스트 경로, DB·Redis·E2E가 필요한 테스트와 그 환경 변수. 테스트가 개발
  DB를 가리키지 않게 막을 변수를 적어 둔다.
- **지침 파일:** 팀 `AGENTS.md`가 있는지, 개인 하네스 파일(`AGENTS.override.md`,
  `.agents/skills`, `.codex/`)이 있는지, 각각 git이 추적하는지(`git ls-files`).
  개인 배치는 추적되는 경로에 설치하지 않는다.
- **exclude:** `.git/info/exclude`의 지금 내용.
- **기준 브랜치:** 팀의 기준 브랜치(예: `origin/main`)와, 지금 브랜치와의 merge-base가 있는지.
- **워크트리:** `git worktree list`. 다른 세션이 쓰는 워크트리를 확인한다.
- **계층:** 문서에 적힌 계층 규칙과 실제 계층 사이 import. `architecture.md` 초안의 근거가 된다.
- **배치:** 개인(팀 저장소, 모두 exclude) 또는 공유(혼자 하는 새 프로젝트, 모두 커밋). 모호하면 한 번만 묻는다.
  새 저장소라도 팀·회사 저장소에 올릴 수 있으면(회사 일, 원격 미정) 모호한 경우다. 공유로 깔면 팀원도 키트의
  hook과 지침을 받는다는 점을 같이 말한다.

## Verify Install

- `AGENTS.md` has concrete project commands and paths.
- selected task source exists:
  - GitHub: `.github/ISSUE_TEMPLATE/agent_task.md`
  - Local: `.ai/tasks.md` and `.ai/issues/`
- Local mode updates `.git/info/exclude`.
- No placeholder tokens remain.
- Future prompt examples are included in the final report.
