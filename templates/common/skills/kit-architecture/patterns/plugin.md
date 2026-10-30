# plugin (전략·플러그인)

## 언제

- 같은 일을 하는 구현이 둘 이상이고 설정·데이터로 하나를 고를 때(스텁과 실물, 공급자 둘, 문서 종류마다 다른 팩).
- 구현을 가르는 if문이 여러 곳에 생기거나, 구현마다 부르는 모양이 달라 쓰는 쪽이 구현을 알아야 할 때.

## 모양

패턴은 패키지 스타일의 한 층 안에 있는 모듈 하나(`{pkg}`)에 쓴다.

| 자리 | 하는 일 |
|---|---|
| `{pkg}.registry` | 이름 → 구현 등록표와 고르는 함수 하나(`get(name)`). 구현을 고르는 곳은 여기뿐이다 |
| `{pkg}.plugins.<구현>` | 구현 하나. base의 모양을 따른다 |
| `{pkg}.base` | 모든 구현이 따르는 모양(Protocol)과 주고받는 데이터, 구현이 같이 쓰는 도우미 |

쓰는 쪽은 registry와 base만 안다. 새 구현은 plugins에 모듈 하나를 더하고 등록표에 한 줄을 넣는다.

## 계약 조각

```ini
[importlinter:contract:{short}-shape]
name = {short} registry above plugins above base
type = layers
containers =
    {pkg}
layers =
    registry
    plugins
    base
exhaustive = True
broken_contract_guidance =
    {pkg} 안은 registry -> plugins -> base 방향으로만 import한다.
    구현이 같이 쓰는 코드는 base에 둔다.

[importlinter:contract:{short}-plugins-independent]
name = {short} plugins do not import each other
type = independence
modules =
    {pkg}.plugins.*
broken_contract_guidance =
    구현이 같이 쓰는 코드는 base로 옮긴다.

[importlinter:contract:{short}-pick-in-registry]
name = {short} plugins are picked only in the registry
type = protected
protected_modules =
    {pkg}.plugins
allowed_importers =
    {pkg}.registry
broken_contract_guidance =
    구현은 registry의 get(name)으로 고르고, 쓰는 쪽은 base의 모양으로 부른다.
```

## architecture.md에 넣을 규칙 줄

- **{short}-shape** {pkg}는 registry → plugins → base 방향으로만 import한다 — 어기면: 구현이 등록표나 서로를 알아 하나를 빼거나 바꿀 수 없다 — [검사: architecture/{short}-shape]
- **{short}-plugins-independent** {pkg}.plugins의 구현은 서로 import하지 않고 같이 쓰는 코드는 base에 둔다 — 어기면: 한 구현을 고치면 다른 구현이 깨진다 — [검사: architecture/{short}-plugins-independent]
- **{short}-pick-in-registry** 구현은 {pkg}.registry에서만 고르고, 쓰는 쪽은 base의 모양으로 부른다 — 어기면: 구현을 가르는 if문이 쓰는 쪽에 흩어진다 — [검사: architecture/{short}-pick-in-registry]
- **{short}-one-shape** 모든 구현은 base의 같은 모양을 따른다. 한 구현만 다른 인자나 단계를 요구하면 base의 모양을 고친다 — 어기면: 쓰는 쪽이 구현마다 다르게 불러야 해서 등록표가 쓸모없다 — [리뷰]

## 리뷰 체크리스트

- 쓰는 쪽이 `registry.get` 한 번으로 구현을 얻나? 구현 이름으로 가르는 if문이 남아 있으면 등록표로 옮긴다.
- 모든 구현이 base의 같은 모양을 따르나?
- 구현이 둘 이상인가? 하나뿐이면 패턴 없이 바로 부른다.
- 테스트가 등록표로 가짜 구현을 끼울 수 있나?

## 이미 있는 코드에 들일 때

구현을 가르는 if문을 찾아 각 갈래를 plugins의 모듈 하나로 옮기고, if문 자리에 `registry.get`을 둔다. 갈래마다 부르는
모양이 다르면 먼저 base의 모양 하나로 맞추는 래퍼를 만든다. 순수한 계산(엔진)을 감싼 래퍼가 모델 호출 같은 I/O를 하면,
그 래퍼와 패턴 모듈은 I/O가 허락된 층(layered면 services)에 둔다.
