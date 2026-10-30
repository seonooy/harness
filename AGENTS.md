# AGENTS.md

## 목적

이 저장소는 **에이전트 하네스 셋업 키트**다. 다른 프로젝트의 에이전트가 이 저장소를 읽고, 그
프로젝트에 맞는 하네스를 설치하는 데 쓴다.

이 폴더를 대상 프로젝트로 보지 않는다. 대상 프로젝트는 사용자가 에이전트를 부른 현재 작업 폴더다.
사용자가 다른 경로를 주면 그 경로가 대상이다.

## 설치 절차

사용자가 이런 식으로 말하면:

```text
~/h 보고 이 프로젝트에 셋업해줘
```

다음을 한다.

1. 이 파일과 `README.md`를 읽는다.
2. 대상 프로젝트를 조사한다:
   - `pwd`
   - git 저장소면 `git status --short --branch`
   - `README.md`, `AGENTS.md` 같은 루트 문서
   - `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `Makefile`, `docker-compose.yml` 같은
     패키지·빌드·테스트 파일
3. 하네스 모드 하나를 고르거나 확인한다:
   - **GitHub Issue mode**: 공유 저장소 워크플로. GitHub Issues와 PR이 기준 출처다.
   - **Local AI Issue mode**: 개인·로컬 워크플로. `.ai/tasks.md`와 `.ai/issues/`가 기준 출처이고
     git에서 제외한다.
   - **Hybrid mode**: 공개·공유 작업은 GitHub Issues를 쓰고, 개인 에이전트 계획과 실험은 로컬
     `.ai/issues/`를 쓴다.
4. `docs/`에서 모드에 맞는 셋업 안내를 읽는다.
5. 고른 모드에 필요한 파일만 `templates/`에서 복사한다.
6. 대상 프로젝트의 `AGENTS.md`를 그 프로젝트에 맞는 완성된 파일로 쓴다. 자리표시자 토큰을 남기지
   않는다. 구체적인 명령과 경로는 대상 저장소에서 알아내고, 선택이 위험하거나 알 수 없을 때만 묻는다.
8. 바뀐 파일을 정확히 보고하고, 다음에 하네스를 어떻게 쓰는지 알려 준다.

## 모드 선택 기본값

- 프로젝트가 이미 GitHub Issues/PR 자동화를 쓰고 에이전트 작업을 협업자와 공유해야 하면
  **GitHub Issue mode**를 쓴다.
- 팀 저장소지만 사용자가 커밋하지 않을 개인용 에이전트 하네스를 원하면 **Local AI Issue mode**를 쓴다.
- 공유 PR 워크플로와 개인 계획이 모두 필요하면 **Hybrid mode**를 쓴다.

## 안전 규칙

- 사용자가 명시적으로 요청하지 않으면 push, fetch, pull을 하거나 remote를 바꾸지 않는다.
- 기존 `AGENTS.md`, `.ai/`, `.github/`는 먼저 읽고 프로젝트에 쓸모 있는 내용을 보존한 채로만
  고친다. 읽지 않고 덮어쓰지 않는다.
- Local AI Issue mode에서는 `.git/info/exclude`를 고친다. `.gitignore`만 믿지 않는다.
- 선택한 모드가 일부러 추적하는 경우가 아니면 로컬 전용 하네스 파일을 커밋하지 않는다.
- 생성하는 대상 문서는 이후 에이전트가 실제로 읽을 만큼 짧게 둔다.

## 템플릿 지도

- `templates/common/`: 모든 모드가 함께 쓰는 파일.
- `templates/github/`: GitHub Issue·PR 템플릿.
- `templates/local-ai/`: 로컬 issue 탭, issue 파일 템플릿, exclude 스니펫.
- `docs/setup-github-issue-mode.md`: 공유 GitHub 워크플로 셋업.
- `docs/setup-local-ai-mode.md`: 비공개 로컬 `.ai` 워크플로 셋업.
- `docs/setup-hybrid-mode.md`: 둘을 합친 워크플로 셋업.
- `docs/target-project-checklist.md`: 셋업 에이전트용 조사 체크리스트.
