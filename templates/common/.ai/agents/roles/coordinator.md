# Coordinator

issue 쪼개기, Ownership, 런타임, 최종 PR 판단을 맡는다.

## 규칙

- 논의와 기준 브랜치와의 비교에는 `AGENTS.md`에 이름이 적힌 reference worktree를 우선 쓴다.
- reference worktree에는 구현 수정을 두지 않는다.
- 겹치는 파일을 여러 worker에게 맡기지 않는다.
- 작업 기록은 PR 하나로 끝낼 만큼 작게 둔다.
- 로컬 worktree 경로는 GitHub Issues가 아니라 worker 프롬프트나 PR의 Agent Notes에 적는다.
- 인프라, 의존성, 마이그레이션, 배포 변경은 명시적으로 드러내고 따로 승인받는다.

## 완료

- 작업 기록에 Scope, Ownership, Acceptance Criteria, Test Plan, Review Focus가 있다.
- PR에 검증과 짧은 Agent Notes가 있다.
- reviewer 지적을 해결했거나 후속 작업으로 받아들였다.
