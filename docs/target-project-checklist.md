# Target Project Checklist

하네스를 대상 저장소에 설치하기 전에 쓴다.

## 대상 확인

- `pwd`로 본 현재 폴더
- `git status --short --branch`로 본 git 저장소 상태
- `git branch --show-current`와 기존 브랜치 정책으로 정한 기준 브랜치
- 대상이 하네스 파일을 git으로 추적해야 하는지

## 기존 지침 읽기

- `AGENTS.md`
- `README.md`
- `.github/` 템플릿
- 에이전트 워크플로를 다룬 기존 `.ai/`나 문서

프로젝트에 쓸모 있는 규칙은 보존한다. 고른 워크플로와 충돌하지 않으면 일반 하네스 규칙으로
바꾸지 않는다.

## 프로젝트 사실 알아내기

찾아볼 것:

- 언어와 프레임워크
- 패키지 매니저
- 테스트 명령
- 린트·타입 검사 명령
- 런타임·개발 서버 명령
- 생성물 출력 폴더
- 시크릿·환경 변수 규칙
- 공개 API나 스키마 파일
- 마이그레이션·의존성 경계
- 프론트엔드/백엔드 분리
- 기존 CI 명령

## 하네스 모드 고르기

- GitHub Issue mode: 공유 issue/PR 워크플로.
- Local AI Issue mode: git에서 제외하는 개인 로컬 하네스.
- Hybrid mode: 둘 다 쓰되 우선순위를 명시한다.

불분명하면 짧게 한 번만 묻는다:

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

## 설치 확인

- `AGENTS.md`에 구체적인 프로젝트 명령과 경로가 있다.
- 고른 작업 출처가 있다:
  - GitHub: `.github/ISSUE_TEMPLATE/agent_task.md`
  - Local: `.ai/tasks.md`와 `.ai/issues/`
- Local mode는 `.git/info/exclude`를 고쳤다.
- 자리표시자 토큰이 남아 있지 않다.
- 최종 보고에 이후 프롬프트 예시가 들어 있다.
