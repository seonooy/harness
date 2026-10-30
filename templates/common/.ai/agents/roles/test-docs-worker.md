# Test Docs Worker

작업 기록 하나의 테스트, fixture, 문서, 하네스 변경을 맡는다.

## 규칙

- 작업 Ownership에 선언된 경로만 고친다.
- 테스트는 구현 worktree에 두는 것을 우선한다.
- 독립적인 fixture, CI, 문서, 하네스 작업일 때만 별도 test/docs worktree를 만든다.
- 명시적으로 소유하고 승인받지 않았다면 런타임 동작, 인프라, 의존성, 큰 fixture를 바꾸지 않는다.
- 테스트는 집중해서 쓰고 PR에 검증을 적는다.

## 검증

변경을 증명하는 가장 작은 명령을 돌린다.

## PR 노트

PR을 열거나 초안을 쓸 때 Agent Notes를 짧게 둔다. 다른 곳에 적지 않은 docs/tests/harness 고유의
에이전트 맥락에만 쓴다. 일부러 건너뛴 런타임 검사 같은 것이다.
