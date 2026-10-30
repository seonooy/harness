# 전체 점검용 하위 에이전트 지시서

레포 전체를 점검할 때, 프로덕션 책임(기능) 하나당 하위 에이전트 하나에게 보내는 프롬프트 양식이다.
`<…>` 칸을 채워 보낸다. 조정하는 에이전트가 기준선과 인벤토리를 미리 돌려 두고, 에이전트마다 일회용 서비스
(DB 포트 등)를 따로 정해 준다.

---

너는 테스트 스위트의 한 부분(기능 하나)을 맡아 tidy-tests의 1단계를 읽기 전용으로 수행한다. 직접 하고,
하위 에이전트는 만들지 않는다. 먼저 `<skill dir>/SKILL.md`(1단계와 처리 규칙), `<skill dir>/references/patterns.md`,
`<skill dir>/references/contract-tests.md`, `<skill dir>/references/test-criteria.md`를 읽는다.

**목표:** 테스트 기준 점검 표, 이 기능이 약속하는 계약 목록, 계약마다 현재 보호 상태(변이로 측정), 기존 테스트마다 처리
(유지·흡수·삭제·수정·미결)와 근거, 그리고 계약 테스트로 바꾸는 계획. 테스트 수를 줄이는 게 목표가 아니다.

**범위:** `<scope>` — `<scratch>/inv/<scope>.jsonl`의 모든 id(<N>개). 레포 `<repo>` (`<branch> @ <HEAD>`),
프로덕션 코드 `<prod dirs>`, 의도는 `<docs·ADR·README>`. 기준선 결과: `<results files>` (<요약>).
인벤토리 필드: `asserts`/`strong`/`weak`/`mock_asserts`, `mocks`, `flags`, `status`, `duration_ms`.
`<scratch>/inv.files.json`에는 imports, `module_mocks`, `unused_imports`, `test_only_symbols`가 있다.

**안전 (철칙):**
1. `<repo>`는 읽기 전용이다. 수정 금지, `git stash/checkout/reset/commit` 금지. 주인의 커밋 안 된 작업이 있을 수 있다.
2. 테스트는 이 환경으로만 돌린다: `<env + command>`. 주인의 개발 DB·브로커·저장소로는 절대 돌리지 않는다.
3. 변이는 `<skill dir>/scripts/falsify.py --repo <repo> --scratch <scratch>/copies/<scope> …`로만 돌린다(자기 사본만,
   다른 에이전트의 사본은 건드리지 않는다).
4. 쓰는 곳은 아래 출력 파일들과 자기 사본뿐이다.

**방법:**
1. 기능의 진입점 코드(분기·가드·부작용·오류 경로), 문서, 기존 테스트 이름에서 계약을 뽑는다. 계약마다 사본의
   일회용 테스트로 현재 동작을 관찰한다. 의도와 달라 보이는 동작은 미결 질문으로 둔다. 그다음 SKILL.md 1단계의
   기준 점검을 한다. 기준상 있어야 하는데 없는 테스트는 빈틈 계약으로 더한다.
2. 계약마다 변이 1~3개를 `<scratch>/reports/<scope>.mutants.jsonl`에 쓰고, 그 기능의 테스트 명령으로
   `falsify.py --mutants … --out <scratch>/reports/<scope>.kills-before.json`을 돌려 계약별 보호 표를 만든다.
3. 테스트마다 어느 계약에 속하는지와 처리를 근거와 함께 기록한다. 테스트가 import하는 것의 프로덕션 호출처를
   grep한다. 다른 범위의 인벤토리(`<scratch>/inv/`)도 grep해서 층·파일 사이의 반복 증명을 찾는다.
4. 계약 테스트 설계안(진입점, 표의 행, 단언)을 만든다. 가능하면 사본에 설계안 테스트를 써 보고 변이를 다 잡는지 확인한다.

**출력 1 — `<scratch>/reports/<scope>.md` (<사용자 언어>). 조금씩 쓴다:** 뼈대를 먼저 만들고, 끝낸 부분부터
붙여 쓴다. 중간에 끊겨도 끝낸 부분은 남아 있어야 한다.

```
# <scope> 계약 정리 계획
## 0. 요약 — 테스트 수·LOC·기준선 / 처리 분포 / 가장 심각한 문제 3개 (file:line)
## 1. 계약과 현재 보호 — | 계약(사용자 말로) | 지금 지키는 테스트 | 변이 잡힘(k/n) | 비고 |
## 1b. 기준 점검 — | 코드 단위 | 종류 | 기준상 테스트 | 지금 있는 테스트 | 판정 |
## 2. 기존 테스트 처리 — 파일별로 한 줄씩: `test` — 처리 — 실제로 잡는 실패 — 근거(file:line) — 조치
## 3. 발견한 패턴 (patterns.md의 이름으로, 예시 file:line)
## 4. 층·범위 사이의 반복 증명 (ids)
## 5. 빈틈 — | 계약/진입점 | 관찰된 현재 동작 | 추천 계약 테스트 |
## 6. 계약 테스트 계획 — 계약별 테스트 설계, 흡수·삭제할 테스트, 예상 전후(테스트 수, 잡히는 변이)
## 7. 방법론 메모 — 모호했던 기준, 오탐·누락된 플래그, 시간이 많이 든 단계
```

**출력 2 — `<scratch>/reports/<scope>.verdicts.jsonl`.** 한 줄에 객체 하나, 하면서 붙여 쓴다:
`{"ids": [...], "verdict": "keep|repair|combine|remove|open", "contract": "...", "detects": "...", "evidence": "file:line ...", "action": "... (combine/remove는 생존 테스트 id)", "falsified": true|false, "batch": "<묶음 이름>"}`
인벤토리의 모든 id가 정확히 한 번씩 들어가야 한다. `<skill dir>/scripts/verdicts.py <scratch>/inv/<scope>.jsonl <이 파일>`이
exit 0인지 확인한다.

**출력 3 — `<scope>.mutants.jsonl`, `<scope>.kills-before.json`** (방법 2에서 만든 것).

**마지막 메시지:** 12줄 이하 — 보고서 경로, 처리 분포, 계약별 보호 요약(잡힘/전체), 가장 심각한 문제 3개, 돌리지 못한 것.
