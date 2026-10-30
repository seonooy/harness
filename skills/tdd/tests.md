# 좋은 테스트와 나쁜 테스트

## 좋은 테스트

**통합 스타일**: 내부 부품을 목으로 대체하지 않고 실제 인터페이스를 통해 테스트한다.

```typescript
// GOOD: 관찰 가능한 동작을 테스트한다
test("user can checkout with valid cart", async () => {
  const cart = createCart();
  cart.add(product);
  const result = await checkout(cart, paymentMethod);
  expect(result.status).toBe("confirmed");
});
```

특징:

- 사용자/호출자가 신경 쓰는 동작을 테스트한다
- 공개 API만 쓴다
- 내부 리팩터링을 견딘다
- HOW가 아니라 WHAT을 서술한다
- 테스트마다 논리적 단언 하나

## 나쁜 테스트

**구현 세부사항 테스트**: 내부 구조에 결합되어 있다.

```typescript
// BAD: 구현 세부사항을 테스트한다
test("checkout calls paymentService.process", async () => {
  const mockPayment = jest.mock(paymentService);
  await checkout(cart, payment);
  expect(mockPayment.process).toHaveBeenCalledWith(cart.total);
});
```

위험 신호:

- 내부 협력 객체를 목으로 대체한다
- private 메서드를 테스트한다
- 호출 횟수/순서를 단언한다
- 동작은 그대로인데 리팩터링하면 테스트가 깨진다
- 테스트 이름이 WHAT이 아니라 HOW를 서술한다
- 인터페이스 대신 외부 수단으로 검증한다

```typescript
// BAD: 인터페이스를 우회해서 검증한다
test("createUser saves to database", async () => {
  await createUser({ name: "Alice" });
  const row = await db.query("SELECT * FROM users WHERE name = ?", ["Alice"]);
  expect(row).toBeDefined();
});

// GOOD: 인터페이스를 통해 검증한다
test("createUser makes user retrievable", async () => {
  const user = await createUser({ name: "Alice" });
  const retrieved = await getUser(user.id);
  expect(retrieved.name).toBe("Alice");
});
```

**동어반복(tautological) 테스트**: 기댓값이 구현을 그대로 되풀이하므로 구조상 항상 통과한다.

```typescript
// BAD: 기댓값을 코드가 계산하는 방식 그대로 다시 계산한다
test("calculateTotal sums line items", () => {
  const items = [{ price: 10 }, { price: 5 }];
  const expected = items.reduce((sum, i) => sum + i.price, 0);
  expect(calculateTotal(items)).toBe(expected);
});

// GOOD: 기댓값이 독립적이고 알려진 리터럴이다
test("calculateTotal sums line items", () => {
  expect(calculateTotal([{ price: 10 }, { price: 5 }])).toBe(15);
});
```
