# events-only (경계 사이는 이벤트로만)

## 언제

- 한 경계가 다른 경계를 동기로 불러서, 한쪽이 느리거나 깨지면 다른 쪽도 같이 깨질 때.
- 한 일이 끝난 뒤 다른 경계가 반응만 하면 될 때(예: 필기 버전이 생기면 검색 색인을 고친다).

## 모양

independent와 같고, 상대 경계의 `events` 모듈(공개 이벤트 타입)만 import해도 된다.

- 이벤트 타입은 보내는 경계의 `events` 모듈에 둔다. 이름은 과거형이고, 바꾸지 않으며, 버전을 가진다.
- 보내기는 그 경계의 adapters(발행기)가, 받기는 받는 경계의 진입(worker·consumer)이 한다.
- 같은 저장소 안이면 메모리 버스로 시작해도 된다. 큐(Kafka, RabbitMQ, Redis)는 adapters 안에만 둔다.

## 계약 조각

```ini
[importlinter:contract:events-only-{name}]
name = {name} talk through events
type = independence
modules =
    {a}
    {b}
ignore_imports =
    {a}.** -> {b}.events
    {b}.** -> {a}.events
unmatched_ignore_imports_alerting = none
broken_contract_guidance =
    경계 사이에는 상대의 events 모듈만 import한다. 상대에게 일을 시키려면 이벤트를 보내고, 상대는 그 이벤트를 받아 처리한다.
```

## architecture.md에 넣을 규칙 줄

- **events-only-{name}** {a}와 {b}는 서로의 `events` 모듈만 import한다 — 어기면: 한 경계가 깨질 때 다른 경계가 같이 깨진다 — [검사: architecture/events-only-{name}]
- **{name}-events-past-tense** 이벤트 이름은 과거형이고, 보낸 뒤 모양을 바꾸지 않는다(바꾸면 새 버전) — 어기면: 받는 쪽이 조용히 깨진다 — [리뷰]

## 리뷰 체크리스트

- 이벤트에 받는 쪽이 다시 물어보지 않아도 될 만큼의 값이 들어 있나? 보내는 쪽의 내부 모델을 그대로 싣지 않나?
- 같은 이벤트를 두 번 받아도 결과가 같나(멱등)?
- 큐 라이브러리가 adapters 밖에서 import되지 않나?
