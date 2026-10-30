# Setup: Local AI Issue Mode

사용자가 대상 저장소에 커밋하지 않을 개인·로컬 에이전트 하네스를 원할 때 이 모드를 쓴다.

## 설치 절차

1. `docs/target-project-checklist.md`를 읽는다.
2. `templates/common/.ai/`를 대상 저장소에 복사한다.
3. `templates/local-ai/.ai/tasks.md`를 대상 `.ai/tasks.md`로 복사한다.
4. `templates/local-ai/.ai/issues/0000-issue-template.md`를 대상
   `.ai/issues/0000-issue-template.md`로 복사한다.
6. 대상 `AGENTS.md`를 만들거나 고친다. `templates/common/AGENTS.md`를 틀로 삼아 대상 프로젝트에
   맞게 구체화한다.
7. 대상 `AGENTS.md`에서 작업 출처를 로컬 `.ai` issue로만 정한다.
8. `templates/local-ai/snippets/git-info-exclude.txt`의 스니펫을 대상 `.git/info/exclude`에
   더한다.
9. 저장소에 이미 git이 추적하는 `.github/` 템플릿이 있으면, 사용자가 GitHub 워크플로를 바꾸라고
   하지 않는 한 건드리지 않는다.

## 대상 AGENTS.md의 작업 출처 절

프로젝트에 맞게 고쳐서 이런 식으로 쓴다:

```md
## 작업 출처

이 프로젝트는 에이전트 크기의 작업에 GitHub Issues 대신 로컬 개인 issue 트래커를 쓴다.

기준 출처:
- `.ai/tasks.md`: 짧은 issue 탭이자 진행 중 백로그 색인.
- `.ai/issues/*.md`: 파일 하나에 issue 하나. Problem, Goal, Scope, Non-goals, Ownership,
  Acceptance Criteria, Test Plan, Review Focus, Progress Log를 담는다.

구현 전:
- `.ai/tasks.md`를 읽는다.
- 고른 `.ai/issues/<id>.md`를 읽는다.
- 브랜치, 소유 범위, 검증 계획을 확인한다.
- 수정은 issue의 Ownership 안에서만 한다.

작업을 마치거나 결정이 바뀌면:
- 해당하는 `.ai/issues/<id>.md`를 고친다.
- 상태, 우선순위, issue 목록이 바뀔 때만 `.ai/tasks.md`를 고친다.

로컬 하네스 파일은 `.git/info/exclude`로 git에서 제외하며, 사용자가 이 정책을 명시적으로 바꾸지
않는 한 push하지 않는다.
```

## 이후 프롬프트 예시

```text
AGENTS.md 따라 .ai/tasks.md 읽고 다음 작업 후보 보여줘.
```

```text
AGENTS.md 따라 .ai/issues/0001-example.md 진행해줘.
```

## 검증

셋업이 끝나면 실행한다:

```bash
find .ai -maxdepth 3 -type f | sort
git status --short -- AGENTS.md .ai .github
```

기대 결과:
- `.ai/tasks.md`와 `.ai/issues/0000-issue-template.md`가 있다.
- 생성한 파일을 직접 훑어봐도 남은 셋업 자리표시자가 없다.
- `.git/info/exclude`를 고친 뒤에는 로컬 전용 파일이 `git status`에 나오지 않는다.
