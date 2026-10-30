# Setup: Hybrid Mode

프로젝트에 공유 GitHub Issue 워크플로와 비공개 로컬 `.ai` issue 트래커가 모두 필요할 때 이 모드를
쓴다.

## 역할 나눔

- GitHub Issues: 공유하는 구현 작업, PR 추적, 협업자에게 보이는 버그·기능.
- 로컬 `.ai/issues/`: 비공개 계획, spike, 에이전트 조율, 개인 작업 대기열, 공유하지 않는 실험 노트.

## 설치 절차

1. `docs/target-project-checklist.md`를 읽는다.
2. 공통 파일과 `.github/`는 `docs/setup-github-issue-mode.md`를 따른다.
3. `.ai/tasks.md`, `.ai/issues/`, `.git/info/exclude`는 `docs/setup-local-ai-mode.md`를 따른다.
4. 대상 `AGENTS.md`에 우선순위 규칙을 명시해서 쓴다.
5. 로컬 issue가 공유할 구현 작업이 되면 GitHub Issue를 만들거나 연결하고, 그 링크를 로컬 issue
   파일에 기록한다.

## 대상 AGENTS.md의 작업 출처 절

프로젝트에 맞게 고쳐서 이런 식으로 쓴다:

```md
## 작업 출처

이 프로젝트는 Hybrid mode를 쓴다.

공유 기준 출처:
- 협업자와 공유하거나 원격 PR로 병합할 작업은 GitHub Issues와 PR이 기준이다.

로컬 기준 출처:
- `.ai/tasks.md`와 `.ai/issues/*.md`는 비공개 계획과 에이전트 워크플로 기록이다.
  `.git/info/exclude`로 git에서 제외한다.

우선순위:
- GitHub Issue와 로컬 `.ai` issue가 충돌하면 구현하기 전에 묻는다.
- 작업이 공유 코드에 영향을 주면 PR을 열기 전에 GitHub Issue를 우선하거나 만든다.
- 로컬 `.ai` issue는 spike, 작업 쪼개기, 아직 GitHub에 올릴 단계가 아닌 개인 다음 행동을 추적할 수
  있다.
```

## 이후 프롬프트 예시

```text
AGENTS.md 따라 hybrid mode로 시작해줘. GitHub 이슈랑 .ai/tasks 둘 다 보고 충돌 있으면 알려줘.
```

```text
.ai/issues/0002 내용을 GitHub Issue로 승격할지 판단해줘.
```

## 검증

셋업이 끝나면 실행한다:

```bash
find .ai .github -maxdepth 3 -type f | sort
git status --short -- AGENTS.md .ai .github
```

기대 결과:
- GitHub 템플릿이 있다.
- 로컬 `.ai/tasks.md`와 `.ai/issues/`가 있다.
- 생성한 파일을 직접 훑어봐도 남은 셋업 자리표시자가 없다.
- 로컬 전용 파일은, 그 정책을 골랐다면 제외돼 있다.
