# task-queue (작업 큐·컨슈머)

## 언제

- 요청 안에서 끝나지 않는 무거운 일(파싱, 모델 호출, 받아쓰기)을 뒤로 보낼 때.
- API와 처리 프로세스를 따로 띄우고, 처리만 늘리거나 다시 돌려야 할 때.

## 모양

`{pkg}`는 큐를 듣는 쪽(컨슈머, 보통 `worker`)이다. 큐에 넣는 쪽(프로듀서)은 api·services다.

| 자리 | 하는 일 |
|---|---|
| 프로듀서(api·services) | 작업 이름과 id 하나를 큐 포트에 넣는다. 컨슈머 코드는 작업 이름으로만 안다 |
| 큐 포트(보통 `core.queue`) | 넣는 모양(Protocol)과 구현, 작업 이름 → 태스크 경로 표, 재시도·제한 시간 |
| `{pkg}.main` | 큐를 듣는 진입점 |
| `{pkg}.tasks.<작업>` | id를 받아 유스케이스 함수 하나를 부르는 한 줄 |

큐에는 id만 넣고, 태스크는 내용을 DB·저장소에서 다시 읽는다. 상태의 정본은 DB라서 큐가 비워져도 결과는 남고, 같은 id를
다시 넣으면 다시 돈다.

## 계약 조각

```ini
[importlinter:contract:{short}-unknown-to-producers]
name = {short} is not imported by the code that enqueues
type = protected
protected_modules =
    {pkg}
allowed_importers =
broken_contract_guidance =
    큐에 넣는 쪽은 작업 이름(문자열)과 id로 큐 포트에 넣는다.
    {pkg}를 띄우는 진입점이 따로 있으면 allowed_importers에 적는다.

[importlinter:contract:{short}-thin-tasks]
name = {short} tasks call only the use cases
type = forbidden
source_modules =
    {pkg}.tasks
forbidden_modules =
    {lower}
allow_indirect_imports = True
broken_contract_guidance =
    태스크는 유스케이스 함수 하나를 부른다. 저장·외부 호출·계산은 유스케이스 아래에서 한다.
```

`{lower}`에는 태스크가 바로 닿지 않을 아래 층을 줄마다 하나씩 적는다(layered면 repositories·clients·models).
유스케이스를 거쳐 닿는 길은 정상이라 `allow_indirect_imports`로 바로 import만 막는다.

## architecture.md에 넣을 규칙 줄

- **{short}-unknown-to-producers** 큐에 넣는 쪽은 {pkg}를 import하지 않고 작업 이름과 id로 큐 포트에 넣는다 — 어기면: API가 처리 코드와 그 무거운 의존성을 함께 띄운다 — [검사: architecture/{short}-unknown-to-producers]
- **{short}-thin-tasks** {pkg}.tasks는 유스케이스 함수 하나를 부르고 아래 층에 바로 닿지 않는다 — 어기면: 같은 일을 API와 워커가 따로 구현한다 — [검사: architecture/{short}-thin-tasks]
- **{short}-ids-only** 큐에는 id만 넣고 태스크는 입력을 DB·저장소에서 다시 읽으며, 같은 id로 두 번 돌아도 결과가 같다 — 어기면: 재시도가 낡은 값을 쓰거나 결과를 겹친다 — [리뷰]

## 리뷰 체크리스트

- 큐 메시지에 id만 실리나? 본문·파일이 실려 있으면 DB·저장소에 두고 id를 넣는다.
- 진행 상태를 DB에 적나? 큐가 비워져도 같은 id를 다시 넣어 이어 갈 수 있나?
- 실패가 DB에 남고, 재시도 횟수·간격이 큐 포트 한 곳에 있나?
- 큐에 넣는 일이 트랜잭션 커밋 뒤에 일어나나? 커밋 전에 넣으면 컨슈머가 아직 없는 행을 읽는다.

## 이미 있는 코드에 들일 때

API에서 오래 걸리는 처리를 찾아 유스케이스 함수로 빼고, API는 행을 만들어 커밋한 뒤 id를 큐에 넣는다. 워커에는 그 함수를
부르는 태스크 한 줄을 둔다. 결과를 기다리는 화면은 DB 상태를 폴링한다.
