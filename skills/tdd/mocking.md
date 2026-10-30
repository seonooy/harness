# 언제 목(mock)을 쓰나

**시스템 경계**에서만 목을 쓴다.

- 외부 API(결제, 이메일 등)
- 데이터베이스(경우에 따라. 테스트 DB를 우선한다)
- 시간/무작위성
- 파일 시스템(경우에 따라)

목을 쓰지 않는 것:

- 자기 클래스/모듈
- 내부 협력 객체
- 직접 통제하는 모든 것

## 목으로 대체하기 쉽게 설계하기

시스템 경계에서는 목으로 대체하기 쉬운 인터페이스를 설계한다.

**1. 의존성 주입을 쓴다**

외부 의존성은 안에서 만들지 말고 밖에서 넘겨 준다.

```typescript
// 목으로 대체하기 쉬움
function processPayment(order, paymentClient) {
  return paymentClient.charge(order.total);
}

// 목으로 대체하기 어려움
function processPayment(order) {
  const client = new StripeClient(process.env.STRIPE_KEY);
  return client.charge(order.total);
}
```

**2. 범용 fetcher보다 SDK 스타일 인터페이스를 선호한다**

조건 분기가 든 범용 함수 하나 대신, 외부 연산마다 구체적인 함수를 만든다.

```typescript
// GOOD: 함수마다 따로 목으로 대체할 수 있다
const api = {
  getUser: (id) => fetch(`/users/${id}`),
  getOrders: (userId) => fetch(`/users/${userId}/orders`),
  createOrder: (data) => fetch('/orders', { method: 'POST', body: data }),
};

// BAD: 목으로 대체하려면 목 안에 조건 분기가 필요하다
const api = {
  fetch: (endpoint, options) => fetch(endpoint, options),
};
```

SDK 방식이 뜻하는 것:
- 목마다 구체적인 모양 하나를 돌려준다
- 테스트 준비에 조건 분기가 없다
- 테스트가 어느 엔드포인트를 실행하는지 보기 쉽다
- 엔드포인트마다 타입 안전성이 있다
