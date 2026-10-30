# Setup: GitHub Issue Mode

대상 프로젝트가 GitHub Issues로 에이전트 작업을 공유하고 pull request로 작업을 반영해야 할 때 이
모드를 쓴다.

## 설치 절차

1. `docs/target-project-checklist.md`를 읽는다.
2. `templates/common/.ai/`를 대상 저장소에 복사한다.
3. `templates/github/.github/`를 대상 저장소에 복사한다.
5. 대상 `AGENTS.md`를 만들거나 고친다. `templates/common/AGENTS.md`를 틀로 삼아 대상 프로젝트에
   맞게 구체화한다.
6. 대상 `AGENTS.md`에서 작업 출처를 GitHub Issues로만 정한다.
7. 대상 `AGENTS.md`에 다음을 넣는다:
   - 기준 브랜치
   - 브랜치 이름 규칙
   - 검증 명령
   - 런타임/개발 서버 명령
   - 소유 범위
   - 의존성·마이그레이션·시크릿 규칙
   - 리뷰 지침
8. `.github/ISSUE_TEMPLATE/agent_task.md`와 `.github/pull_request_template.md`는 git에서 계속
   추적한다.
9. 사용자가 에이전트 하네스 자체를 비공개로 두길 원하지 않는 한 `.ai/`를 `.git/info/exclude`에
   넣지 않는다.

## 대상 AGENTS.md의 작업 출처 절

프로젝트에 맞게 고쳐서 이런 식으로 쓴다:

```md
## 작업 출처

이 프로젝트는 에이전트 크기의 작업의 기준 출처로 GitHub Issues를 쓴다.

구현 전:
- 연결된 GitHub Issue를 읽는다.
- Problem, Goal, Scope, Non-goals, Ownership, Acceptance Criteria, Test Plan, Review Focus를
  확인한다.
- 기준 브랜치에서 작업 브랜치를 만든다.
- 수정은 issue의 Ownership 안에서만 한다.

작업을 마치면:
- `.ai/agents/checklists/pr-ready.md`를 채운다.
- `.github/pull_request_template.md`로 PR을 연다.
- PR이 issue를 완료하면 `Closes #<number>`로 issue를 연결한다.
```

## 이후 프롬프트 예시

```text
AGENTS.md 따라 GitHub Issue #123 진행해줘.
```

```text
AGENTS.md 따라 PR 리뷰해줘.
```

## 검증

셋업이 끝나면 실행한다:

```bash
find .ai .github -maxdepth 3 -type f | sort
```

기대 결과:
- `.ai/`와 `.github/` 아래에 파일이 있다.
- 생성한 파일을 직접 훑어봐도 남은 셋업 자리표시자가 없다.
