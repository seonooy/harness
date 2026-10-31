# Codex Harness

Codex로 일할 때 쓰는 스킬과 프로젝트 셋업 키트다. 애플리케이션 코드는 없다.

## 설치

작업 폴더의 터미널에서 실행한다. 모델을 부르지 않고, 있는 파일은 덮어쓰지 않는다.

```bash
git clone https://github.com/seonooy/harness && bash harness/install.sh && rm -rf harness && codex
```

스킬은 `.agents/skills/`에, 작업 지침은 `AGENTS.md`에, 문서 틀은 `notes/`와 `DECISIONS.md`에 들어간다. 기본은 핵심 스킬 19개다. 전체가 필요하면 `bash harness/install.sh --all`로 설치한다.

## 흐름

1. `intake`: 환경 확인, 과제·데이터 재기, 담당자 질문
2. 담당자 답을 규칙으로 옮기고 `grilling`으로 빈 곳 찾기
3. `measure`: 평가 기준과 기준선
4. `$to-spec`, `brief`: 구조를 맞추고 사용자가 승인
5. `$to-tickets`, `dispatch`: 티켓별 구현, 재측정, 구조 지도 갱신, 커밋
6. 제출 전: `code-review`, 정리, 정적 검사, `recap`

## handoff

`$handoff`로 상태를 작업 폴더의 `.handoff/`에 저장하고, `/new` 뒤 `$handoff 이어`로 이어 한다.
컨텍스트 알림을 쓰려면 `~/.codex/hooks.json`의 UserPromptSubmit에 작업 폴더의 `.agents/skills/handoff/nudge.py`를 `python3`로 부르게 등록한다.

## 출처

`skills/`의 각 폴더에 `LICENSE`와 `SOURCE.md`가 있으면 그 출처와 라이선스를 따른다. 나머지는 이 저장소의 MIT 라이선스를 따른다.

---

# Agent Harness Template

저장소에 프로젝트에 맞는 개발 하네스를 더하는, 에이전트가 읽는 셋업 키트다. 스크립트도 아니고
자리표시자만 있는 템플릿도 아니다. Codex가 다른 프로젝트 안에서 읽고, 고치고, 설치할 수 있는
안내와 원본 파일 묶음이다.

## 대상 프로젝트에서 쓰는 법

대상 프로젝트에서 Codex를 열고 다음 중 하나를 말한다:

```text
~/h 보고 이 프로젝트에 agent harness 셋업해줘.
```

```text
~/h 보고 local-ai mode로 셋업해줘.
```

```text
~/h 보고 GitHub Issue mode로 셋업해줘.
```

```text
~/h 보고 python·layered, 개인 배치로 셋업해줘.
```

```text
~/h 보고 python·ddd, 개인 배치로 셋업하고 켜줘.
```

에이전트는 대상 프로젝트를 조사하고, 모드를 고르거나 확인하고, 알맞은 파일을 복사하고, 그
프로젝트에 맞는 완성된 `AGENTS.md`를 써야 한다. 자리표시자 텍스트를 남기면 안 된다.

## 검사 키트

모드와 따로 고르는 조각이다. `check` 명령 하나가 포맷·린트·아키텍처·타입·빠른 테스트와 약화 감시를 돌리고,
0(통과)·1(실패)·2(미완료)로 끝난다.

- 조각: `templates/common`(실행기·절차) + 언어 조각(`templates/stacks/python`) + 아키텍처 조각
  (`templates/arch/layered` 또는 `templates/arch/ddd`) + `templates/project`
- 배치: 개인(모두 `.git/info/exclude`) 또는 공유(모두 커밋). 작업 출처 모드와 따로 고른다.
- 설치 절차: `docs/setup-checks.md`. 대상 조사 항목: `docs/target-project-checklist.md`의 "검사 칸 조사".
- 늘 들어가는 스킬: 절차 `kit-change`·`kit-verify`·`kit-architecture`와 코드 품질 `kit-deslop`·`kit-no-comments`·`kit-quality-review`.
  코드 품질 스킬과 kit-change의 구현 원칙·설계 경고 목록은 pstack·cursor-team-kit(MIT)을 응용했다.
  kit-change가 구현 → 정리 → 검증 → 리뷰 순서로 부른다.
- 아키텍처: 패키지마다 스타일(layered·hexagonal)을 고르고, 경계를 나누면 관계(independent·events-only·
  separate-service)를 정한다. 패키지 안 모듈 하나에는 패턴(pipeline·plugin·task-queue)을 쓸 수 있다.
  `--arch`는 루트 패키지의 첫 스타일이고, 그 뒤로는 `kit-architecture`로 더하거나 바꾼다.
  보호 파일 변경은 에이전트가 `.ai/proposals/`에 제안을 두고 사용자가 `harness.py proposal apply <이름>`으로 적용한다.
- 그 밖의 스킬: 미리 정하지 않고 셋업할 때 프로젝트에 맞게 고른다. 기준과 후보는 `docs/skill-guide.md`,
  넣고 빼기는 `harness.py skills add|remove|list`.

셋업한 뒤에는 이렇게 쓴다.

```text
kit-change로 <작업> 해줘.
```

```text
kit-verify로 지금 diff 검증해줘.
```

## 모드

### GitHub Issue Mode

작업을 GitHub Issues로 공유하고 PR로 반영해야 할 때 쓴다.

설치되는 것:
- 공통 `.ai/agents/`와 `.ai/rules/`
- `.github/ISSUE_TEMPLATE/agent_task.md`
- `.github/pull_request_template.md`
- 프로젝트별 `AGENTS.md`

기준 출처: GitHub Issue + PR.

### Local AI Issue Mode

하네스가 개인·로컬용이라 팀 저장소에 커밋하지 않을 때 쓴다.

설치되는 것:
- 공통 `.ai/agents/`와 `.ai/rules/`
- `.ai/tasks.md`
- `.ai/issues/0000-issue-template.md`
- 프로젝트별 `AGENTS.md`
- 로컬 전용 파일을 위한 `.git/info/exclude` 항목

기준 출처: `.ai/tasks.md` + `.ai/issues/*.md`.

### Hybrid Mode

공유 작업에는 GitHub Issues/PR이 필요하지만 개인 에이전트 계획은 로컬에 두어야 할 때 쓴다.

GitHub와 로컬 `.ai` issue 조각을 모두 설치한 뒤, `AGENTS.md`에 우선순위 규칙을 명시해서 쓴다.

기준 출처:
- 공유하는 구현과 PR 추적은 GitHub Issues.
- 비공개 계획, spike, 개인 대기열, 공유하지 않는 에이전트 조율은 로컬 `.ai/issues/`.

## 디렉터리 지도

```text
agent-harness-template/
├── AGENTS.md
├── README.md
├── docs/
│   ├── setup-github-issue-mode.md
│   ├── setup-local-ai-mode.md
│   ├── setup-hybrid-mode.md
│   ├── setup-checks.md          검사 키트 설치 절차
│   └── target-project-checklist.md
└── templates/
    ├── common/
    │   ├── AGENTS.md
    │       │   ├── .ai/
    │   ├── manifest.json        검사 키트 common 조각의 설치 목록
    │   ├── checks/              check.py, harness.py, kit/
    │   ├── skills/              kit-change, kit-verify, kit-architecture, kit-deslop, kit-no-comments, kit-quality-review
    │   └── snippets/            지침 파일의 "Checks" 절
    ├── github/
    │   └── .github/
    ├── local-ai/
    │   ├── .ai/
    │   └── snippets/            exclude 목록, AGENTS.override.md 틀
    ├── stacks/
    │   └── python/              단계 목록, Ruff·mypy 설정, 개인 도구 잠금 파일
    ├── arch/
    │   └── layered/             architecture.md 틀, import-linter 계약 틀
    └── project/                 intent.md, 검증 지도, 변경 규칙
```

## 셋업 에이전트 규약

셋업 에이전트는 다음을 해야 한다:
- 쓰기 전에 대상 저장소를 조사한다.
- 기존 프로젝트 지침을 보존한다.
- 대상 `AGENTS.md`에 구체적인 명령과 경로를 쓴다.
- Hybrid mode를 요청받지 않았다면 기본으로 작업 출처 하나만 고른다.
- 로컬 전용 모드면 `.git/info/exclude`를 고친다.
- 바뀐 파일과 다음 프롬프트 예시를 보고한다.

## 셋업 뒤

대상 프로젝트에서 이후 세션은 이렇게 시작한다:

```text
AGENTS.md 따라 시작해줘.
```

Local AI Issue mode면:

```text
AGENTS.md 따라 .ai/tasks.md 읽고 다음 작업 후보 보여줘.
```

특정 로컬 issue를 진행하려면:

```text
AGENTS.md 따라 .ai/issues/0001-example.md 진행해줘.
```

GitHub Issue mode면:

```text
AGENTS.md 따라 GitHub Issue #123 진행해줘.
```
