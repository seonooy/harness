# pipeline (파이프-필터)

## 언제

- 데이터가 정해진 순서의 단계를 지나며 바뀌고(파싱 → 정렬 → 생성), 단계 하나만 다시 돌리거나 재시도해야 할 때.
- 단계 본문 여럿이 한 파일에 모여 길어지고, 한 단계를 고치려면 다른 단계까지 읽어야 할 때.

## 모양

패턴은 패키지 스타일의 한 층 안에 있는 모듈 하나(`{pkg}`)에 쓴다. layered면 보통 services 층 아래다.

| 자리 | 하는 일 |
|---|---|
| `{pkg}.runner` | 단계 목록과 순서(등록표), 단계 하나의 수명(시작 기록 → 본문 → 결과 기록 → 다음 단계 넘기기), 재시도 |
| `{pkg}.stages.<단계>` | 단계 하나. 입력을 파이프에서 읽고, 일을 하고, 결과를 파이프에 쓴다. 모든 단계가 같은 모양의 진입 함수 하나를 내놓는다 |
| `{pkg}.contracts` | 단계가 주고받는 데이터 모양. 파이프가 DB 행이면 없어도 된다 |

파이프는 단계 사이에 값을 넘기는 곳이다(DB 행, 파일, 큐 메시지). 단계는 파이프만 알고 앞뒤 단계는 runner가 정한다.
그래서 어느 단계든 혼자 다시 돌 수 있다.

## 계약 조각

```ini
[importlinter:contract:{short}-shape]
name = {short} runner above stages
type = layers
containers =
    {pkg}
layers =
    runner
    stages
    (contracts)
exhaustive = True
broken_contract_guidance =
    {pkg} 안은 runner -> stages -> contracts 방향으로만 import한다.
    단계 목록과 순서는 runner에 둔다. 단계는 결과를 파이프에 쓰고, 다음 단계는 runner가 정한다.

[importlinter:contract:{short}-stages-independent]
name = {short} stages do not import each other
type = independence
modules =
    {pkg}.stages.*
broken_contract_guidance =
    앞 단계의 결과는 파이프(DB 행·파일)에서 읽는다.
    두 단계가 같이 쓰는 코드는 contracts나 아래 층으로 내린다.
```

## architecture.md에 넣을 규칙 줄

- **{short}-shape** {pkg}는 runner → stages → contracts 방향으로만 import하고, 단계 목록과 순서는 runner에만 둔다 — 어기면: 단계 순서가 여러 곳에 흩어져 단계를 더하거나 빼기 어렵다 — [검사: architecture/{short}-shape]
- **{short}-stages-independent** {pkg}.stages의 단계는 서로 import하지 않고 앞 단계의 결과를 파이프에서 읽는다 — 어기면: 단계 하나만 다시 돌리거나 따로 시험할 수 없다 — [검사: architecture/{short}-stages-independent]
- **{short}-stage-shape** 모든 단계는 같은 모양의 진입 함수 하나를 내놓고, 입력을 매번 파이프에서 다시 읽고, 같은 입력으로 두 번 돌아도 결과가 같다 — 어기면: 재시도가 결과를 겹쳐 쓰거나 중간 상태에 묶인다 — [리뷰]

## 리뷰 체크리스트

- 다음 단계를 runner가 정하나? 단계가 다음 단계를 부르거나 큐에 넣는 곳이 있으면 runner로 옮긴다.
- 단계 사이의 값은 파이프로만 건너가나? 메모리·전역 변수로 넘기는 값이 있으면 파이프에 쓴다.
- 같은 단계를 두 번 돌리면 결과가 바뀌어 쓰이나(멱등)?
- 실패한 단계 뒤의 단계가 멈추고, 실패가 기록에 남나?

## 이미 있는 코드에 들일 때

단계 본문이 한 파일에 모여 있으면 그 파일의 수명·재시도 코드를 runner로 옮기고, 단계 본문을 하나씩 stages로 옮긴다.
옮길 때마다 테스트를 돌린다. 밖에서 옛 경로를 import하면 옛 모듈에서 새 자리를 다시 내보내는 줄을 잠시 남기고, 옮기는
순서와 함께 ADR에 적는다. 계약은 옮기기 전에 넣어도 된다. 키트가 트리에 아직 없는 모듈을 계약에서 빼고 돌린다.
