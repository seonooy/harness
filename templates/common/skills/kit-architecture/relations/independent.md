# independent (경계 나누기, Strategic DDD)

## 언제

- 두 업무 영역의 용어와 규칙이 다르고, 한쪽을 바꿀 때 다른 쪽을 몰라도 되어야 할 때(bounded context).
- 같은 말이 두 영역에서 다른 뜻으로 쓰이기 시작할 때.

## 모양

경계(context)끼리는 서로 import하지 않는다. 상대가 공개한 application 함수나 이벤트로만 주고받는다. 둘이 같이 쓰는 값은
`shared`에 둔다.

경계를 나누면 루트는 context 목록이 된다. 루트의 `layers` 계약은 모든 패키지를 등록만 하고(context는 한 줄에 `:`로 잇는다),
금지는 이 관계 계약이 맡는다.

```text
[importlinter:contract:app-layers]
type = layers
containers =
    app
layers =
    (bootstrap)
    notes : billing
    (shared)
exhaustive = True
```

`architecture.md`의 `## 패키지` 표에서는 루트 줄의 스타일을 `layered`로 바꾸고, 이유에 경계를 나눈 ADR을 적는다. 위 등록
계약이 루트의 스타일 계약이 된다. 루트에 있던 다른 스타일 계약(예: `app-domain-pure`)은 그 모듈이 옮겨 간 context의 계약으로
바꾼다. context마다 표에 한 줄을 더해 스타일을 적고, 그 스타일 문서의 계약 조각을 context 이름으로 채운다
(`app.notes` → `notes-layers`).

context마다 `GLOSSARY.md`를 두거나, 루트에 `GLOSSARY-MAP.md`를 두어 경계 사이에 오가는 말을 적는다.

## 계약 조각

```ini
[importlinter:contract:independent-{name}]
name = {name} are independent
type = independence
modules =
    {a}
    {b}
broken_contract_guidance =
    경계끼리는 서로 import하지 않는다. 상대가 공개한 application 함수나 이벤트로만 주고받는다.
    같이 쓰는 값은 shared로 내린다.
```

## architecture.md에 넣을 규칙 줄

- **independent-{name}** {a}와 {b}는 서로 import하지 않는다 — 어기면: 한 경계를 바꿀 때 다른 경계가 깨지고, 같은 말이 두 뜻으로 섞인다 — [검사: architecture/independent-{name}]
- **{name}-language** 경계마다 용어집이 있고, 경계를 넘는 말은 그 경계의 용어로 바꿔 넘긴다 — 어기면: 한쪽 모델이 다른 쪽에 새어 들어간다 — [리뷰]

## 리뷰 체크리스트

- 경계를 넘는 호출이 상대의 공개 application 함수나 이벤트인가? 상대의 domain 모델을 그대로 쓰지 않나?
- shared에 한 경계만 쓰는 코드가 들어가지 않았나?
