# layered 조각

루트 패키지를 layered(MVC·계층) 스타일로 시작하는 결정 문서 틀과, 그 결정을 검사로 옮기는 규칙 틀이다.
하위 패키지의 스타일이나 패키지 사이 관계는 나중에 `kit-architecture`로 더하거나 바꾼다. 설치 절차는
`docs/setup-checks.md`에 있다. 이 README는 설치하지 않는다.

| 파일 | 설치 위치 | 소유 |
|---|---|---|
| `architecture.md` | `.ai/project/architecture.md` | 프로젝트 |
| `python/importlinter.ini` | `.ai/checks/importlinter.ini` | 프로젝트 |
| `adr/README.md` | `docs/adr/README.md` | 프로젝트 |

`architecture.md` 틀은 언어와 상관없다. 다른 언어를 더할 때는 그 언어의 규칙 틀만 `<언어>/` 아래에 둔다.

## architecture.md

결정만 적는다. 키트는 결정을 지어내지 않는다. 기존 프로젝트면 에이전트가 기존 문서(팀 `AGENTS.md`의
계층 규칙 같은 것)와 코드의 계층 사이 import를 대조해 초안을 쓰고, 사용자는 확인만 한다.

- `## 패키지`: `패키지 | 스타일 | 이유`. 설치하면 루트 한 줄(layered)이 들어간다.
- `## 패키지 사이`: 경계를 나누기 전에는 비워 둔다.
- `## 규칙`: `- **<id>** <규칙> — 어기면: <문제> — [검사: <단계>/<id 또는 코드>]` 또는 `[리뷰]`. 줄은
  `.agents/skills/kit-architecture/styles/layered.md`의 것을 루트 이름으로 채운 것이다.
- `## 예외 / 옮기는 순서`: `대상 | 이유 | 기한`.

계약 id는 `<패키지 짧은 이름>-<규칙>`이다(루트 `app`이면 `app-layers`). doctor는 패키지 표의 패키지마다 그 이름으로
시작하는 계약이 있는지, 모든 `layers` 계약이 `exhaustive = True`인지도 본다.

`[검사: architecture/<id>]`의 id는 `importlinter.ini`의 계약 id와 같아야 한다. `check doctor`가 둘을 맞춰 보고,
다르면 2(미완료)를 낸다.

## 기본 규칙과 검사

| 규칙 | 검사 | 메모 |
|---|---|---|
| `<루트>-layers` | import-linter `layers` 계약, `exhaustive = True` | 목록에 없는 하위 패키지도 위반이다. 쓰지 않을 층만 `(이름)`으로 둔다. 기준 브랜치에 아직 없는 모듈은 그대로 적는다(키트가 트리마다 그 트리에 없는 모듈을 계약에서 빼고 돌린다) |
| `<루트>-framework-at-edge` | import-linter `forbidden` 계약(fastapi, starlette) | `source_modules`에는 실제로 있는 층만 둔다. 아무도 import하지 않는 이름이면 조용히 통과하니 철자를 확인한다 |
| `<루트>-clients-only` | Ruff TID251(`ruff-rules.json`의 `banned_api`) | 아래 절 |
| `<루트>-thin-api` | 리뷰 | 라우터가 services 함수 하나만 부르는지는 기계로 못 잡는다 |

계약마다 `name`과 `broken_contract_guidance`(고치는 방법, 한국어)를 둔다. lint-imports는 계약이 깨지면
그 계약 아래에 guidance를 그대로 찍는다. `name`은 출력과 위반 코드에 그대로 쓰이니 ASCII로 짧게 쓴다.
한글 이름은 시험해 보지 않았다.

프로젝트에 맞게 계약을 더할 수 있다. 예를 들어 순수 계산 계층이 다른 계층을 import하지 않게 하려면
`forbidden` 계약을 더하고, architecture.md에 같은 id의 규칙을 적는다. `ignore_imports`로 import 하나를 예외로
두는 계약에는 `unmatched_ignore_imports_alerting = error`를 두어, 예외가 가리키는 import가 없어지면 알게 한다.
아직 없을 수 있는 모듈을 가리키는 예외(events-only의 `events` 모듈 같은 것)는
`unmatched_ignore_imports_alerting = none`으로 둔다.

## 외부 호출은 clients에서만

기본 검사는 import-linter가 아니라 Ruff TID251이다.

- import-linter `protected` 계약은 아무도 import하지 않는 패키지를 두면 "not present in the graph"로 실패한다.
  표준 라이브러리는 최상위 이름(`urllib`)만 다룰 수 있어 `urllib.request`만 막을 수도 없다(2026-10-19 확인).
  그래서 이 검사는 import-linter 계약으로 두지 않는다.
- TID251은 `urllib.request`, `http.client`처럼 정확한 모듈을 막고, 메시지에 고치는 방법을 적을 수 있다.

설치할 때 `ruff-rules.json`을 이렇게 채운다. 막을 모듈(`urllib.request`, `http.client`, `requests`,
모델 SDK 등)마다 같은 메시지로 한 줄씩 더하고, clients 폴더의 경로는 프로젝트에 맞춘다.

```json
"banned_api": {
  "httpx": "외부 호출은 app/clients 안에서만 한다. services가 clients의 클라이언트를 받아 호출한다. (architecture.md#clients-only)"
},
"per_file_ignores": {
  "**/tests/**": ["S101", "S105", "S106", "ARG001", "INP001", "TID251", "PLR2004"],
  "**/app/clients/**": ["TID251"]
}
```

한계: 줄 끝의 무시 주석 하나로 TID251을 넘길 수 있다. 약화 감시(`check all`의 weakening 단계)가 새 무시 주석을 잡는다.
