# GLOSSARY.md 형식

## 구조

```md
# {컨텍스트 이름}

{이 컨텍스트가 무엇이고 왜 있는지 한두 문장으로 설명한다.}

## Language

**Order**:
{용어에 대한 한두 문장 설명}
_Avoid_: Purchase, transaction

**Invoice**:
배송 후 고객에게 보내는 결제 요청.
_Avoid_: Bill, payment request

**Customer**:
주문을 하는 사람 또는 조직.
_Avoid_: Client, buyer, account
```

## 규칙

- **입장을 분명히 한다.** 같은 개념에 단어가 여럿이면 가장 좋은 하나를 고르고, 나머지는 `_Avoid_` 아래에 적는다.
- **정의를 짧게 쓴다.** 최대 한두 문장이다. 그것이 무엇을 하는지가 아니라 무엇*인지*를 정의한다.
- **이 프로젝트의 컨텍스트에 특화된 용어만 넣는다.** 일반적인 프로그래밍 개념(타임아웃, 오류 유형, 유틸리티 패턴)은 프로젝트가 아무리 많이 쓰더라도 넣지 않는다. 용어를 추가하기 전에 묻는다. 이 컨텍스트에만 있는 개념인가, 일반적인 프로그래밍 개념인가? 앞의 경우만 넣는다.
- **자연스러운 묶음이 생기면 용어를 소제목 아래로 묶는다.** 모든 용어가 하나의 응집된 영역에 속하면 평평한 목록으로 충분하다.

## 단일 컨텍스트 저장소와 다중 컨텍스트 저장소

**단일 컨텍스트(대부분의 저장소):** 저장소 루트에 `GLOSSARY.md` 하나를 둔다.

**다중 컨텍스트:** 저장소 루트의 `GLOSSARY-MAP.md`가 컨텍스트 목록과 각 위치, 컨텍스트 사이의 관계를 나열한다:

```md
# Glossary Map

## Contexts

- [Ordering](./src/ordering/GLOSSARY.md): 고객 주문을 받고 추적한다
- [Billing](./src/billing/GLOSSARY.md): 청구서를 생성하고 결제를 처리한다
- [Fulfillment](./src/fulfillment/GLOSSARY.md): 창고 피킹과 배송을 관리한다

## Relationships

- **Ordering → Fulfillment**: Ordering이 `OrderPlaced` 이벤트를 발행하고, Fulfillment가 이를 소비해 피킹을 시작한다
- **Fulfillment → Billing**: Fulfillment가 `ShipmentDispatched` 이벤트를 발행하고, Billing이 이를 소비해 청구서를 생성한다
- **Ordering ↔ Billing**: `CustomerId`와 `Money` 타입을 공유한다
```

이 스킬은 어느 구조인지 추론한다:

- `GLOSSARY-MAP.md`가 있으면 그것을 읽어 컨텍스트를 찾는다
- 루트의 `GLOSSARY.md`만 있으면 단일 컨텍스트다
- 둘 다 없으면 첫 용어가 정리될 때 루트 `GLOSSARY.md`를 만든다(lazily)

컨텍스트가 여러 개 있으면 현재 주제가 어느 컨텍스트와 관련되는지 추론한다. 불분명하면 묻는다.
