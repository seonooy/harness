# Git 규칙

## 브랜치

- `main`: 안정/릴리스 브랜치.
- 대상 프로젝트의 기준 브랜치는 그 프로젝트의 `AGENTS.md`에 정의한다.
- 보호된 브랜치에 직접 push하지 않는다.
- 새 작업은 대상 프로젝트의 기준 브랜치에서 분기한다.

## 작업 기록

- 작업을 시작하기 전에 작업 기록을 만들거나 고르는 것을 우선한다.
- 작업 기록은 GitHub Issue나 로컬 `.ai/issues/<id>.md` 파일일 수 있다.
- 가능하면 작업 하나를 집중된 PR 하나에 대응시킨다.
- GitHub Issue mode에서는 PR이 issue를 완료하면 `Closes #<number>`로 연결한다.
- Local AI Issue mode에서는 GitHub Issue가 있는 척하지 말고, 로컬 issue의 Progress Log와
  `.ai/tasks.md`의 상태를 갱신한다.

## 브랜치 이름

짧은 소문자 이름을 쓴다:

```text
feat/task-name
fix/task-name
docs/task-name
refactor/task-name
chore/task-name
```

## 커밋

conventional commit을 우선한다:

```text
feat:
fix:
docs:
refactor:
chore:
test:
```

## Pull Request

- 대상 프로젝트의 `AGENTS.md`에 적힌 기준 브랜치를 대상으로 한다.
- `.github/pull_request_template.md`를 쓴다.
- 검증 명령과 결과를 넣는다.
- Agent Notes는 짧게 두거나 `None`으로 둔다.
- 설정돼 있으면 CI와 자동 리뷰를 기다린다.
- 병합은 사람 reviewer/maintainer가 결정한다.
