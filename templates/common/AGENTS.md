# AGENTS.md

## 프로젝트

이 저장소는 에이전트 하네스를 쓴다. 현재 동작을 가정하기 전에 관련 소스, 작업 기록, `.ai/` 지침을
확인한다.

이 파일을 실제 프로젝트에 설치할 때는 이 절을 구체적으로 채운다:
- 프로젝트 이름과 목적;
- 프로젝트 종류, 언어, 런타임, 패키지 매니저;
- 공개 API·스키마·데이터 경계;
- 바꾸기 전에 명시적 승인이 필요한 영역.

## 작업 출처

셋업할 때 이 절을 정한다.

지원하는 정책:
- GitHub Issue mode: GitHub Issues가 기준 출처다.
- Local AI Issue mode: `.ai/tasks.md`와 `.ai/issues/*.md`가 기준 출처다.
- Hybrid mode: GitHub Issues는 공유 기준이고, 로컬 `.ai/issues/`는 비공개 계획과 에이전트 조율용이다.

고른 작업 출처를 읽고, 작업의 소유 범위·완료 기준·검증 계획이 분명해지기 전에는 구현을 시작하지
않는다.

## 에이전트 워크플로

세션을 시작할 때:

- `AGENTS.md`를 읽는다.
- 고른 작업 출처를 읽는다.
- `pwd`, `git branch --show-current`, `git status --short --branch`를 실행한다.
- 브랜치, 소유 범위, 검증 계획을 확인한다.
- worktree 워크플로면 `.ai/agents/README.md`를 읽는다.

작업을 마치거나 결정이 바뀌면 고른 작업 출처를 갱신한다:
- GitHub Issue mode: GitHub Issue나 PR을 갱신한다.
- Local AI Issue mode: 해당하는 `.ai/issues/<id>.md`를 갱신한다. 상태, 우선순위, issue 목록이 바뀔
  때만 `.ai/tasks.md`를 갱신한다.
- Hybrid mode: 그 작업을 소유한 출처를 갱신한다. 출처끼리 충돌하면 묻는다.

## Worktree

구현 전에 작업 브랜치나 작업 worktree를 쓴다. 리뷰나 비교를 할 때는 기준 브랜치의 reference
worktree를 하나 둔다.

기본 패턴:

- main repo: 통합 체크아웃.
- reference worktree: 최신 기준 브랜치. 리뷰 전용이고 구현 수정은 하지 않는다.
- task worktree: 작업 단위 하나. 기준 브랜치에서 분기하고, 소유한 경로만 수정한다.

대상 프로젝트가 고정된 worktree를 쓰면, 셋업할 때 이 절을 구체적인 로컬 worktree 이름으로 바꾼다.

## 로컬 명령

셋업할 때 대상 프로젝트를 조사해서 이 절을 채운다.

구체적인 명령으로 바꿀 검증 예시:

```bash
pytest
npm test
cargo test
go test ./...
```

구체적인 명령으로 바꿀 런타임 예시:

```bash
npm run dev
uv run python -m package
docker compose up
```

## 규칙

- 새 구조를 들이기 전에 기존 코드 패턴을 따른다.
- 작업의 소유 범위 안에서만 일한다. 범위 밖을 고쳐야 하면 멈추고 묻는다.
- 마이그레이션, 의존성 변경, vendored 코드 변경, 빌드 시스템 변경은 먼저 묻는다.
- `.env`, 시크릿, 생성된 업로드 파일, 로컬 산출물, 환경에 묶인 경로를 커밋하지 않는다.
- 작업이 그 변경을 명시적으로 맡지 않는 한 공개 API, 스키마, 데이터베이스, 직렬화 데이터 계약을
  유지한다.
- 끝났다고 말하기 전에 관련 검증을 돌린다. 명령과 결과를 작업 기록이나 PR에 적는다.
- 보호된 브랜치에 직접 push하지 않는다. 고른 모드가 원격 협업을 포함하면 PR을 쓴다.

## Git

- 새 작업은 대상 프로젝트의 기준 브랜치에서 분기한다.
- 작업 기록 하나에 묶인 작은 변경으로 나눈다.
- conventional commit을 우선한다: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`,
  `test:`.
- 작업과 PR 본문은 팀의 기본 언어로 쓴다.
- PR에는 Summary, Why, Changes, Verification, Risk, Review Focus, 해당하면 Linked Issue,
  Agent Notes를 넣는다.

## 리뷰 지침

- 실제 버그, 동작 회귀, 빠진 테스트, 보안 문제, API/스키마 계약 파손, 범위 이탈에 집중한다.
- 소유 범위 경계와 런타임 가정을 확인한다.
- 스타일만 다룬 지적은 정확성이나 유지보수성 문제를 가릴 때가 아니면 무시한다.

## 참고 문서

- `.ai/agents/` - 에이전트 워크플로, 역할, 프롬프트, 체크리스트.
- `.ai/rules/` - 상세한 로컬 프로젝트 규칙.
- `.github/` - GitHub Issue mode를 쓸 때의 GitHub Issue·PR 템플릿.
