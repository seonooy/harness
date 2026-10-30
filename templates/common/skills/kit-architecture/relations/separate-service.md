# separate-service (별도 서비스, MSA)

## 언제

- 경계마다 따로 배포하거나 따로 늘려야 할 때(부하, 장애 격리, 다른 팀).
- 한 경계의 장애나 배포가 다른 경계를 멈추면 안 될 때.

먼저 independent나 events-only로 충분한지 본다. 서비스로 나누면 배포·관측·데이터 일관성 비용이 생긴다.

## 모양

- **같은 저장소 안의 배포 단위**: 서비스마다 최상위 패키지를 두고(import-linter `root_packages`), 서로 import하지 않는다.
  같이 쓰는 것은 공유 계약 패키지(요청·응답·이벤트 스키마)뿐이다. 그 패키지는 두 서비스 밖에 둔다.
  - `root_packages`에 넣은 최상위 패키지마다 `architecture.md`의 `## 패키지` 표에 한 줄을 두어 스타일을 적고, 그 스타일
    문서의 계약 조각을 그 이름으로 채워 넣는다. doctor는 최상위 패키지마다 `containers`가 그 이름이고
    `exhaustive = True`인 `layers` 계약이 있는지 본다.
- **저장소를 나누면**: 저장소마다 키트를 설치한다. 서비스 사이 규칙은 공유 계약 패키지의 버전으로 지킨다. 이 문서의
  계약 조각은 쓰지 않는다.
- 서비스 사이 동기 호출은 각 서비스의 clients(또는 adapters)에서만 한다. 가능하면 events-only를 따른다.

## 계약 조각

```ini
[importlinter:contract:separate-service-{name}]
name = {name} are separate services
type = independence
modules =
    {a}
    {b}
broken_contract_guidance =
    서비스끼리는 서로 import하지 않는다. 공유 계약 패키지의 스키마로만 주고받는다.
```

## architecture.md에 넣을 규칙 줄

- **separate-service-{name}** {a}와 {b}는 서로 import하지 않고 공유 계약 패키지만 같이 쓴다 — 어기면: 따로 배포할 수 없게 묶인다 — [검사: architecture/separate-service-{name}]
- **{name}-contract-versions** 서비스 사이 스키마는 버전을 올려 바꾸고, 받는 쪽이 옛 버전도 읽는다 — 어기면: 한쪽만 배포했을 때 깨진다 — [리뷰]

## 리뷰 체크리스트

- 서비스가 다른 서비스의 DB를 직접 읽거나 쓰지 않나?
- 동기 호출에 시간 제한과 재시도가 있나? 실패해도 이 서비스가 계속 도나?
- 공유 계약 패키지에 한 서비스만 쓰는 코드가 들어가지 않았나?
