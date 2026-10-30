# 검증 지도

변경 종류마다 최소로 돌릴 검증이다. `kit-verify`가 이 표에서 고른다.
기본은 작업 중 `python3 .ai/checks/check.py fast`, 완료를 말하기 전 `python3 .ai/checks/check.py all`이다.

| 변경 | 최소 검증 |
|---|---|
| <<FILL: 변경 종류. 예: 순수 로직·계약>> | <<FILL: 예: check fast, 바뀐 계약의 회귀 사례>> |
| <<FILL: 예: 저장·API·워커>> | <<FILL: 예: check all, 전용 테스트 DB에서 DB 테스트>> |
| 문서·지침만 | `check doctor`와 경로·참조 확인. 제품 테스트는 돌리지 않는다 |

## 테스트 위치

`kit-verify`의 design이 계약 테스트를 둘 곳과 하나만 돌리는 명령이다.

- 단위·계약 테스트: <<FILL: 폴더. 예: tests/contract/>>
- 통합 테스트(DB·API): <<FILL: 폴더와 필요한 환경. 예: tests/api/, 전용 테스트 DB>>
- 테스트 하나만 돌리기: <<FILL: 명령. 예: .venv/bin/python -m pytest tests/contract/test_notes.py::test_version -q>>

## 주의사항

- <<FILL: 서비스가 필요한 검증(DB·큐·E2E)을 돌리는 조건과 준비 방법. 개발 DB·Redis를 가리키지 않게 하는 법>>
- skip이나 mock으로만 지나간 검증은 미검증으로 보고한다.
- 관련 검증이 통과한 뒤 이유 없이 전체 검증을 반복하지 않는다.
