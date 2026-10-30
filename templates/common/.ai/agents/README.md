# AGENTS/v0

작업 출처를 기반으로 하는 에이전트 작업용 가벼운 하네스다. 작업 출처는 GitHub Issue, 로컬
`.ai/issues/<id>.md` 파일, 또는 Hybrid mode에서 둘 다일 수 있다.

## 흐름

- 작업 기록 -> 브랜치/worktree -> 역할 프롬프트 -> 범위를 지킨 작업 -> 검증
  -> 커밋 -> 해당하면 PR -> reviewer.
- 작업 기록은 Problem, Goal, Scope, Non-goals, Ownership, Acceptance Criteria, Test Plan,
  Review Focus를 정해야 한다.
- worker는 소유한 경로만 고친다. 범위가 바뀌면 멈추고 coordinator에게 묻는다.
- 작업 기록과 PR 본문은 팀의 기본 언어로 쓴다.
- GitHub 워크플로를 켰으면 PR은 `.github/pull_request_template.md`를 쓰고, 짧은 Agent Notes를
  넣는다.

## 표준 Worktree

셋업할 때 대상 프로젝트의 `AGENTS.md`에 구체적인 worktree 이름을 쓴다.
기본 형태는 이렇다:

| Worktree | 역할 | 브랜치 형식 | 수정 가능 | 실행 가능 |
| --- | --- | --- | --- | --- |
| main repo | 통합 체크아웃 | 현재 브랜치 | 보호된 브랜치에서 직접 구현하지 않는다 | 프로젝트 조사와 git status |
| reference worktree | 기준 확인 + reviewer + coordinator 논의 | 기준 브랜치 | 구현 수정 없음 | diff와 리뷰 명령 |
| task worktree | 작업 하나를 맡은 worker | 작업 브랜치 | 작업 Ownership이 선언한 경로만 | 소유 영역의 집중 검증 |

기본으로 테스트 전용 worktree를 상시 만들지 않는다. 백엔드 테스트는 백엔드 PR에, 프론트엔드
테스트는 프론트엔드 PR에 넣는다. 임시 test/docs worktree는 독립적인 fixture, CI, 문서, 하네스
작업에만 쓴다.

## Worktree 명령

임시 worker:

```bash
git worktree add ../worker-123 -b agent/123-task-name <base-branch>
cd ../worker-123
codex
```

기존 reference worktree 갱신:

```bash
git -C ../reference-worktree pull --ff-only
```

브랜치가 이미 있으면:

```bash
git worktree add ../worker-123 agent/123-task-name
```

## 역할 선택

- Coordinator: issue 쪼개기, Ownership, 런타임, 최종 PR 판단.
- Backend Worker: 백엔드 구현.
- Frontend Worker: 프론트엔드 구현.
- Test Docs Worker: 테스트·문서·하네스 작업. 가능하면 구현 worktree에서 한다.
- Reviewer: diff 리뷰만. 가능하면 reference worktree에서 한다.

## 런타임 소유

대상 프로젝트의 `AGENTS.md`에 이름이 적힌 worktree만 백엔드 인프라/런타임을 소유한다.

백엔드 런타임 명령:

```bash
<target-project backend runtime command>
```

프론트엔드 worker는 문서화된 백엔드 API 엔드포인트를 쓴다. 프론트엔드 런타임 명령은 돌려도 되지만,
명시적으로 승인받지 않으면 백엔드 인프라를 돌리지 않는다.

## PR 흐름

1. `.ai/agents/checklists/pr-ready.md`를 채운다.
2. conventional commit 메시지로 커밋한다.
3. 고른 모드가 원격 PR 워크플로를 포함하면 브랜치를 push하고 기준 브랜치로 PR을 연다.
4. PR이 의도한 base/head로 열렸는지, 해당하면 소유 작업 기록을 연결했는지 확인한다.
5. 게시하기 전에 작업/PR 본문의 순서를 확인한다. 번호를 매겼다면 단계, issue 링크, 리뷰 노트가
   오름차순이어야 한다.
6. 켜져 있으면 CI, CodeRabbit, Codex 리뷰 신호를 기다린다.
7. 자동 리뷰 코멘트를 살펴본다.
8. 타당한 지적은 고치고, 조치하지 않은 것은 Agent Notes에 적는다.
9. 고친 뒤 검증을 다시 돌린다.
10. `mergeStateStatus`, `reviewDecision`, 필수 status check를 확인한다.
11. 병합은 사람 reviewer/maintainer가 결정한다.

유용한 PR 상태 명령:

```bash
gh pr view <number> --json state,isDraft,baseRefName,headRefName,mergeStateStatus,reviewDecision,statusCheckRollup
gh pr checks <number>
gh pr view <number> --comments
```

Codex 자동 리뷰가 돌지 않으면 PR 코멘트로 요청한다:

```md
@codex review
```

PR은 작업 하나, 브랜치 하나, 집중된 변경, 문서화한 검증으로 유지한다.
에이전트가 만든 작업은 squash merge를 쓴다.

## Agent Notes

Agent Notes는 Summary, Changes, Verification, Risk, Review Focus에 맞지 않는 에이전트 고유의
맥락을 적는 곳이다. 짧게 둔다. 한 줄이면 충분하다.

Agent Notes는 다음에만 쓴다:

- 에이전트 조율을 이해하는 데 필요한 worktree나 프롬프트 맥락.
- 리뷰에서 수상해 보일 수 있는 의도된 무변경.
- 일부러 미뤘거나 조치할 필요가 없다고 판단한 자동 리뷰 지적.
- 다른 곳에 아직 적지 않은 후속 작업 후보.

에이전트 고유의 맥락이 없으면 `None`이라고 쓴다.
