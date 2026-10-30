# Codex Harness

Codex로 일할 때 쓰는 스킬과 프로젝트 셋업 키트다. 애플리케이션 코드는 없다.

## 설치

작업 저장소의 터미널에서 Codex를 켜기 전에 실행한다.

```bash
git clone https://github.com/seonooy/harness ~/h
mkdir -p ~/.agents/skills && cp -R ~/h/skills/* ~/.agents/skills/
codex
```

Codex에 이렇게 말한다.

```text
~/h 보고 이 프로젝트에 셋업해 줘
```

## handoff

`$handoff`로 상태를 작업 폴더의 `.handoff/`에 저장하고, `/new` 뒤 `$handoff 이어`로 이어 한다.
컨텍스트 알림을 쓰려면 `~/.codex/hooks.json`의 UserPromptSubmit에 `python3 ~/.agents/skills/handoff/nudge.py`를 등록한다.

## 출처

`skills/`의 각 폴더에 `LICENSE`와 `SOURCE.md`가 있으면 그 출처와 라이선스를 따른다. 나머지는 이 저장소의 MIT 라이선스를 따른다.

---

# Agent Harness Template

Agent-readable setup kit for adding a project-specific development harness to a
repository. This is not a script and not a placeholder-only template. It is a
set of guides and source files that Codex can read, adapt, and install
inside another project.

## How To Use From A Target Project

Open Codex in the target project, then say one of:

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

The agent should inspect the target project, choose or confirm a mode, copy the
right files, and write a finished `AGENTS.md` for that project. It should not
leave placeholder text behind.

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

## Modes

### GitHub Issue Mode

Use when tasks should be shared through GitHub Issues and landed through PRs.

Installs:
- common `.ai/agents/` and `.ai/rules/`
- `.github/ISSUE_TEMPLATE/agent_task.md`
- `.github/pull_request_template.md`
- project-specific `AGENTS.md`

Source of truth: GitHub Issue + PR.

### Local AI Issue Mode

Use when the harness is personal/local and should not be committed to the team
repo.

Installs:
- common `.ai/agents/` and `.ai/rules/`
- `.ai/tasks.md`
- `.ai/issues/0000-issue-template.md`
- project-specific `AGENTS.md`
- `.git/info/exclude` entries for local-only files

Source of truth: `.ai/tasks.md` + `.ai/issues/*.md`.

### Hybrid Mode

Use when shared work needs GitHub Issues/PRs but personal agent planning should
stay local.

Installs both GitHub and local `.ai` issue pieces, then writes explicit
precedence rules in `AGENTS.md`.

Source of truth:
- GitHub Issues for shared implementation and PR tracking.
- Local `.ai/issues/` for private planning, spikes, personal queues, and
  unshared agent coordination.

## Directory Map

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

## Setup Agent Contract

The setup agent must:
- inspect the target repo before writing;
- preserve existing project instructions;
- write concrete commands and paths into the target `AGENTS.md`;
- choose only one task source by default, unless Hybrid mode is requested;
- update `.git/info/exclude` for local-only mode;
- report changed files and next prompt examples.

## After Setup

In the target project, start future sessions with:

```text
AGENTS.md 따라 시작해줘.
```

For Local AI Issue mode:

```text
AGENTS.md 따라 .ai/tasks.md 읽고 다음 작업 후보 보여줘.
```

For a specific local issue:

```text
AGENTS.md 따라 .ai/issues/0001-example.md 진행해줘.
```

For GitHub Issue mode:

```text
AGENTS.md 따라 GitHub Issue #123 진행해줘.
```
