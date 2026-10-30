# 아키텍처

<<FILL: 이 문서가 다루는 범위 한 줄. 예: src/app 패키지 전체>>

이 프로젝트의 아키텍처 결정이다. 패키지마다 스타일(layered 또는 hexagonal)을 고르고, 경계를 나눈 패키지 사이의 관계를
적는다. 스타일과 관계의 뜻, 계약 조각, 리뷰 체크리스트는 `.agents/skills/kit-architecture/`의 문서가 정본이고, 정하거나
바꿀 때는 `kit-architecture` 스킬을 따른다. 되돌리기 어려운 구조 결정의 이유는 `docs/adr/`에 둔다. 용어는 루트의 `GLOSSARY.md`에 둔다.

검사 설정은 이 결정에서만 나온다. 구조를 바꾸려면 먼저 이 문서를 고치고, 그다음 검사 설정
(`.ai/checks/importlinter.ini`, `.ai/checks/ruff-rules.json`)을 맞춘다. 검사 설정은 보호 파일이라 에이전트는
`.ai/proposals/`에 제안을 두고, 사용자가 `harness.py proposal apply`로 적용한다.

규칙 끝의 표시
- `[검사: architecture/<id>]`: `.ai/checks/importlinter.ini`의 계약 id. `check doctor`가 둘이 같은지 본다.
- `[검사: lint/<코드>]`: Ruff 규칙이 잡는다.
- `[리뷰]`: 기계로 잡지 못한다. 리뷰에서 본다.

## 패키지

| 패키지 | 스타일 | 이유 |
|---|---|---|
| <<FILL: 최상위 패키지. 예: app>> | hexagonal | <<FILL: 고른 이유 한 줄. 예: 업무 규칙이 많아 웹·DB 없이 시험하려고>> |

## 패키지 사이

경계를 나누기 전에는 비워 둔다. 나누면 `kit-architecture`의 관계 문서(independent, events-only, separate-service)를 따른다.

| 관계 | 대상 | 규칙 |
|---|---|---|

## 패턴

패키지 안 모듈 하나에 패턴을 쓰면 적는다. 쓰기 전에는 비워 둔다. 패턴 문서(pipeline, plugin, task-queue)는
`kit-architecture`에 있다.

| 자리 | 패턴 | 이유 |
|---|---|---|

## 규칙

- **<<FILL: 최상위 패키지. 예: app>>-layers** <<FILL: 최상위 패키지. 예: app>>는 bootstrap → 진입·adapters → application → domain 방향으로만 import한다 — 어기면: 안쪽이 서버·파일·외부 도구에 묶여 따로 테스트하거나 바꿀 수 없다 — [검사: architecture/<<FILL: 최상위 패키지. 예: app>>-layers]
- **<<FILL: 최상위 패키지. 예: app>>-domain-pure** <<FILL: 최상위 패키지. 예: app>>의 domain과 application은 프레임워크·외부 도구를 import하지 않는다 — 어기면: 규칙 하나를 시험하는 데 서버·JVM·파일이 필요해진다 — [검사: architecture/<<FILL: 최상위 패키지. 예: app>>-domain-pure]
- **<<FILL: 최상위 패키지. 예: app>>-ports-in-application** 어댑터가 구현할 포트는 application에 두고 이름은 `GLOSSARY.md`의 용어로 짓는다 — 어기면: 유스케이스가 구현에 묶인다 — [리뷰]
- **<<FILL: 최상위 패키지. 예: app>>-invariants-in-domain** 항상 참이어야 하는 규칙은 domain 모델이 지킨다 — 어기면: 같은 검사가 바깥에 흩어진다 — [리뷰]

## 예외 / 옮기는 순서

| 대상 | 이유 | 기한 |
|---|---|---|
| <<FILL: 예외가 없으면 이 줄을 지운다. 예: app.legacy의 직접 파일 읽기>> | <<FILL: 예: 어댑터로 옮기기 전까지>> | <<FILL: 예: 2026-12>> |
