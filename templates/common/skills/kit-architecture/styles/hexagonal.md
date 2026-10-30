# hexagonal (헥사고날, 그 안의 Tactical DDD)

## 언제

- 지킬 업무 규칙(불변식)이 많고, 그 규칙을 웹·DB·외부 도구 없이 시험하고 싶을 때.
- 프레임워크나 저장소 코드가 업무 규칙과 섞여서, 한쪽을 바꾸면 다른 쪽이 깨질 때.

## 모양

바깥이 안쪽에 기댄다. 안쪽(application, domain)은 바깥을 모른다.

| 층 | 하는 일 |
|---|---|
| `bootstrap` | 설정을 읽고 어댑터를 만들어 application에 넣는다 |
| `http`, `worker` | 진입. 요청·작업을 받아 유스케이스 하나를 부른다. 서로 import하지 않는다 |
| `adapters` | application의 포트를 구현한다. DB, 파일, 외부 API, JVM |
| `application` | 유스케이스의 흐름과 포트(어댑터가 구현할 Protocol) |
| `domain`, `events` | 모델, 불변식, 순수 계산. 다른 경계에 공개하는 이벤트 타입은 `events`에 둔다 |

쓰지 않는 층은 계약에서 `(이름)`으로 둔다.

## 계약 조각

```ini
[importlinter:contract:{short}-layers]
name = {short} hexagon
type = layers
containers =
    {pkg}
layers =
    (bootstrap)
    (http) | (worker) | adapters
    application
    domain : (events)
exhaustive = True
broken_contract_guidance =
    바깥에서 안쪽으로만 import한다: bootstrap -> http|worker|adapters -> application -> domain.
    application이 어댑터를 직접 부르면 application에 포트(Protocol)를 두고 adapters가 구현하게 한 뒤 bootstrap에서 넣는다.
    http, worker, adapters는 서로 import하지 않는다.

[importlinter:contract:{short}-domain-pure]
name = {short} inside uses no infrastructure
type = forbidden
source_modules =
    {pkg}.application
    {pkg}.domain
forbidden_modules =
    fastapi
    starlette
broken_contract_guidance =
    domain과 application은 웹 프레임워크, 외부 변환기, JVM 연결, 저장소 라이브러리를 쓰지 않는다.
    필요한 기능은 application에 포트로 정의하고 adapters에서 구현한다.
```

`forbidden_modules`에 이 패키지가 쓰는 외부 도구(DB 드라이버, PDF 엔진, JVM 연결 등)를 더한다.

## architecture.md에 넣을 규칙 줄

- **{short}-layers** {pkg}는 bootstrap → 진입·adapters → application → domain 방향으로만 import한다 — 어기면: 안쪽이 서버·파일·외부 도구에 묶여 따로 테스트하거나 바꿀 수 없다 — [검사: architecture/{short}-layers]
- **{short}-domain-pure** {pkg}의 domain과 application은 프레임워크·외부 도구를 import하지 않는다 — 어기면: 규칙 하나를 시험하는 데 서버·JVM·파일이 필요해진다 — [검사: architecture/{short}-domain-pure]
- **{short}-ports-in-application** 어댑터가 구현할 포트는 application에 두고 이름은 `GLOSSARY.md`의 용어로 짓는다 — 어기면: 유스케이스가 구현에 묶인다 — [리뷰]
- **{short}-invariants-in-domain** 항상 참이어야 하는 규칙은 domain 모델이 지킨다 — 어기면: 같은 검사가 바깥에 흩어진다 — [리뷰]

## 리뷰 체크리스트

Tactical DDD(도메인 안을 짜는 법):

- Aggregate: 한 번의 변경은 Aggregate 하나만 바꾼다. 다른 Aggregate는 ID로만 가리킨다.
- Entity: 식별자로 같은지 판단한다. 식별자는 만들 때 정하고 바꾸지 않는다.
- Value Object: 값으로 같은지 판단하고 바꾸지 않는다(frozen dataclass, pydantic frozen).
- 불변식은 Aggregate의 메서드가 지킨다. 바깥에서 필드를 직접 고치지 않는다.
- 저장소 포트는 Aggregate마다 하나를 application에 둔다.
- 도메인 이벤트 이름은 일어난 일을 과거형으로 쓴다(예: NoteVersionCreated).

구조:

- 새 이름이 `GLOSSARY.md`의 용어인가? 아니면 용어집에 먼저 넣었나?
- 유스케이스가 어댑터 구현을 직접 만들지 않고 포트로 받나? 조립은 bootstrap에서만 하나?

## 다른 스타일에서 옮겨 올 때

layered에서 옮겨 오면: `models`의 규칙을 `domain`으로, `services`의 흐름을 `application`으로, `repositories`·`clients`를
`adapters`로, `api`를 `http`로 옮긴다. services가 repositories를 바로 부르던 곳마다 application에 포트를 둔다. 한 번에
옮기지 않는다. 기준선이 기존 위반을 빼므로, 이번에 고치는 유스케이스부터 옮기고 순서는 ADR에 적는다.
