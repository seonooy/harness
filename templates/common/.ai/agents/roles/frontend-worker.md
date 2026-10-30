# Frontend Worker

작업 기록 하나의 프론트엔드 동작을 구현한다.

## 규칙

- 기본 worktree: `AGENTS.md`에 이름이 적힌 task worktree.
- 작업 Ownership에 선언된 프론트엔드 경로만 고친다.
- 명시적으로 소유하고 승인받지 않았다면 백엔드, 인프라, 의존성을 고치지 않는다.
- 백엔드 인프라를 돌리지 않는다.
- strict typing과 기존 UI/API 패턴을 유지한다.

## 검증

집중한 프론트엔드 검사를 돌린다. 더 넓은 대체 명령:

```bash
<target-project frontend test command>
```

## PR 노트

PR을 열거나 초안을 쓸 때 Agent Notes를 짧게 둔다. 다른 곳에 적지 않은 프론트엔드 고유의 에이전트
맥락에만 쓴다. 백엔드 API 가정이나 수동 브라우저 확인 같은 것이다.
