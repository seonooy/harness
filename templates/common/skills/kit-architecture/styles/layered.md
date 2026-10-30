# layered (MVC·계층)

## 언제

- 요청을 받아 저장하고 돌려주는 일이 대부분이고, 지킬 업무 규칙이 적을 때(관리 화면, 단순 CRUD).
- hexagonal의 포트·어댑터 층이 비어 있거나 한 겹 감싸기만 할 때.

## 모양

위 층이 아래 층만 import한다.

| 층 | 하는 일 |
|---|---|
| `api` | 컨트롤러. 요청을 검증하고 services 함수 하나를 부른 뒤 응답으로 바꾼다. 웹 프레임워크는 여기서만 쓴다 |
| `services` | 흐름과 업무 규칙, 트랜잭션 |
| `repositories`, `clients` | DB 읽고 쓰기, 외부 호출. 서로 import하지 않는다 |
| `models`, `schemas` | 데이터 모양(저장 모델, 요청·응답 스키마). 서로 import해도 되지만 위 층은 모른다 |
| `core` | 설정, 공용 도구. 아무 층도 import하지 않는다 |

쓰지 않는 층은 계약에서 `(이름)`으로 두거나 지운다.

## 계약 조각

```ini
[importlinter:contract:{short}-layers]
name = {short} layers
type = layers
containers =
    {pkg}
layers =
    api
    services
    (repositories) | (clients)
    models : (schemas)
    (core)
exhaustive = True
broken_contract_guidance =
    위 층은 아래 층만 import한다(api -> services -> repositories|clients -> models·schemas -> core).
    아래 층이 위 층을 부르면 함수 인자로 넘겨받거나, 같이 쓰는 코드를 아래 층으로 내린다.
    새 모듈은 이 목록의 층 하나에 넣는다.

[importlinter:contract:{short}-framework-at-edge]
name = {short} framework only in api
type = forbidden
source_modules =
    {pkg}.services
    {pkg}.models
forbidden_modules =
    fastapi
    starlette
broken_contract_guidance =
    웹 프레임워크는 api 층에서만 쓴다. services는 도메인 예외를 던지고 api가 HTTP 응답으로 바꾼다.
```

`source_modules`에는 그 패키지에 실제로 있는 층만 둔다. 다른 웹 프레임워크를 쓰면 `forbidden_modules`를 바꾼다.

## architecture.md에 넣을 규칙 줄

- **{short}-layers** {pkg}는 api → services → repositories·clients → models·schemas → core 방향으로만 import한다 — 어기면: 순환 import가 생기고 아래 층을 따로 테스트하거나 바꿀 수 없다 — [검사: architecture/{short}-layers]
- **{short}-framework-at-edge** 웹 프레임워크는 {pkg}.api에서만 쓴다 — 어기면: 서비스가 HTTP에 묶여 CLI·워커·테스트에서 다시 쓸 수 없다 — [검사: architecture/{short}-framework-at-edge]
- **{short}-clients-only** 외부 호출(HTTP, 모델 SDK)은 {pkg}.clients에서만 한다 — 어기면: 교체·모의·재시도를 한곳에서 다룰 수 없다 — [검사: lint/TID251]
- **{short}-thin-api** 컨트롤러는 services 함수 하나를 부르고 결과를 바꾸기만 한다 — 어기면: 업무 규칙이 HTTP 층에 숨는다 — [리뷰]

금지 API는 `ruff-rules.json`의 `banned_api`에 넣고, `per_file_ignores`에서 `{pkg}.clients` 폴더만 `TID251`을 허용한다.

## 리뷰 체크리스트

- 컨트롤러가 services 함수 하나만 부르나? 조건문·계산이 컨트롤러에 있지 않나?
- services가 웹 프레임워크 타입(Request, Response)을 받거나 돌려주지 않나?
- 같은 일을 하는 services 함수가 둘 생기지 않았나?

## 다른 스타일에서 옮겨 올 때

hexagonal에서 옮겨 오면: 진입(http)은 `api`, application은 `services`, adapters는 `repositories`·`clients`, domain은
`models`가 된다. 포트(Protocol)는 하나뿐인 구현이면 지우고 services가 구현을 바로 부른다. 옮기는 동안의 위반은 기준선이
빼므로, 새로 쓰는 코드부터 새 층을 따른다.
