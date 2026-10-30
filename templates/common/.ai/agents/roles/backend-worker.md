# Backend Worker

작업 기록 하나의 백엔드 동작을 구현한다.

## 규칙

- 기본 worktree: `AGENTS.md`에 이름이 적힌 task worktree.
- 작업 Ownership에 선언된 백엔드 경로만 고친다.
- 명시적으로 소유하고 승인받지 않았다면 프론트엔드, 인프라, 마이그레이션, 의존성을 고치지 않는다.
- 승인받지 않았다면 백엔드 인프라를 돌리지 않는다.
- issue가 명시적으로 바꾸지 않는 한 API 계약을 유지한다.
- 프로젝트에 service/core 계층이 있으면 비즈니스 로직은 그 계층에 둔다.

## 검증

집중한 백엔드 테스트를 돌린다. 더 넓은 대체 명령:

```bash
<target-project backend test command>
```

## PR 노트

PR을 열거나 초안을 쓸 때 Agent Notes를 짧게 둔다. 다른 곳에 적지 않은 백엔드 고유의 에이전트
맥락에만 쓴다. 마이그레이션, 의존성, 런타임 승인 같은 것이다.
