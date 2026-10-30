# python 조각

Python 프로젝트(주로 FastAPI)의 단계 목록과 도구 설정이다. 설치 절차는 `docs/setup-checks.md`에 있다.
이 README와 `tools-requirements.*`는 설치하지 않는다.

| 파일 | 설치 위치 | 소유 |
|---|---|---|
| `stages.existing.json` | `.ai/checks/stages.json` (`--project-kind existing`) | 프로젝트 |
| `stages.new.json` | `.ai/checks/stages.json` (`--project-kind new`) | 프로젝트 |
| `ruff-rules.json` | `.ai/checks/ruff-rules.json` | 프로젝트 |
| `mypy.ini` | `.ai/checks/mypy.ini` | 프로젝트 |
| `baseline.json` | `.ai/checks/baseline.json` (빈 기준선, 공유 배치용) | 프로젝트 |
| `tools-requirements.in`, `.lock` | 설치하지 않는다. 개인 도구 환경을 만들 때 쓴다 | — |

## 단계

| 단계 | 도구 | 프로필 | 비교 | 메모 |
|---|---|---|---|---|
| format | `ruff format --check --output-format json` | fast, all | 예 | 파일을 넘기면 그 파일만 |
| lint | `ruff check --output-format json` + `ruff-rules.json` | fast, all | 예 | 파일을 넘기면 그 파일만 |
| architecture | `lint-imports --config .ai/checks/importlinter.ini` | fast, all | 예 | `PYTHONPATH={cwd}`로 최상위 패키지를 찾는다. src 레이아웃(패키지마다 `src/`가 따로 있는 모노레포)은 그 폴더들을 단계 env의 `PYTHONPATH`에 적는다. 키트도 그 폴더에서 최상위 패키지를 찾는다 |
| types | `mypy --config-file .ai/checks/mypy.ini` | all | 예 | 캐시는 `.ai/runs/cache/mypy` |
| deps | `deptry . --extend-exclude "\.ai/"` | all | 아니오 | 새 프로젝트만. 의존성 정의와 import가 맞는지 본다 |
| tests | `pytest --junitxml` | fast, all | 아니오 | 서비스 없이 도는 테스트만. 실패는 늘 실패다 |
| weakening | 키트 내장 | all | — | 새 무시 주석·skip·검사 범위를 줄이는 도구 설정·지운 테스트·보호 파일 변경 |
| fix-lint, fix-format | `ruff check --fix`, `ruff format` | fix | — | 바뀐 `.py`·`.pyi` 파일만 고친다(`suffixes`). 파일을 고치는 유일한 프로필 |

'비교'는 기존 위반을 빼고 새 위반만 실패로 치는지다. 개인 배치는 `base_ref`와의 merge-base에서 같은 명령을
돌려 비교하고(결과는 캐시한다), 공유 배치는 `baseline.json`과 비교한다.

검사는 파일을 바꾸지 않는다. 그래서 Ruff에 `--no-cache`, lint-imports에 `--no-cache`, pytest에
`-p no:cacheprovider`를 주고, `PYTHONDONTWRITEBYTECODE=1`을 둔다.

Ruff 단계에는 `--extend-exclude .ai --force-exclude`도 준다. 공유 배치에서는 `.ai/`가 git에 있어 Ruff가 키트
코드까지 검사하고, pre-commit은 스테이징한 파일을 경로로 넘기는데 Ruff는 넘겨받은 경로에 제외 설정을
적용하지 않기 때문이다. `--force-exclude`가 있어야 프로젝트가 제외한 파일(예: 마이그레이션)도 계속 빠진다.

### 기존 프로젝트(`stages.existing.json`)

프로젝트에 이미 있는 도구는 그 프로젝트가 고정한 버전과 호출 방식을 쓴다. 프로젝트에 없는 도구(mypy,
import-linter)는 개인 도구 환경에서 부른다. `<<FILL: ...>>`로 둔 값은 project, base_ref, commands,
단계마다의 cwd, 테스트 경로, import_check, venvs다. 테스트가 실제 DB·Redis를 가리키지 않게
`env`·`env_remove`도 정한다.

프로젝트가 고정한 Ruff의 `format`에 `--output-format`이 없으면(0.12.12에는 `--extend-exclude`도 없다, 2026-10-29
팀 저장소에서 확인) format 단계는 `ruff-format` 종류로 돌 수 없다. `command` 종류로 바꾸고 팀 CI가 포맷을
보는 폴더만 넘긴다. merge-base 비교가 빠지므로 그 폴더가 기준 브랜치에서 이미 포맷돼 있는지 먼저 본다.
fix-format에서도 `--extend-exclude .ai`를 뺀다.

개인 도구 환경(네트워크는 설치할 때 한 번만 쓴다):

```sh
mkdir -p .ai/checks/tools
cp <템플릿>/templates/stacks/python/tools-requirements.lock .ai/checks/tools/requirements.lock
uv venv --python <프로젝트와 같은 Python> .ai/checks/tools/.venv
uv pip sync --python .ai/checks/tools/.venv/bin/python .ai/checks/tools/requirements.lock
```

uv 캐시에 이미 있으면 `uv pip sync --offline`도 된다. mypy는 `--python-executable`로 프로젝트 가상환경을 보고,
pydantic 플러그인은 도구 환경의 pydantic을 쓴다. 두 pydantic 버전을 맞춘다. 잠금 파일이 바뀌면 merge-base
결과 캐시도 새로 만든다.

### 새 프로젝트(`stages.new.json`)

모든 도구를 `.venv/bin`에서 바로 실행한다(`.venv/bin/python`, `.venv/bin/mypy`, `.venv/bin/lint-imports`,
`.venv/bin/deptry`). check는 `.venv`를 만들거나 맞추지 않으니, 먼저 `uv sync --locked`로 만든다. `uv run`은 쓰지
않는다. `--no-sync`여도 없는 `.venv`를 만들고 Python을 내려받을 수 있기 때문이다. `.venv`가 없으면 단계는
미완료(2)이고, `venvs`에 `.venv`가 있어서 doctor가 2를 내며 이 명령을 알려 준다. Ruff, mypy, import-linter,
pytest, pydantic, deptry를 프로젝트의 dev 의존성에 넣는다. `<<FILL: ...>>`는 project, base_ref, 최상위 패키지
이름이다. 기준선은 빈 `baseline.json`으로 시작한다.

- deps 단계는 `deptry .`로 `pyproject.toml`의 의존성과 코드의 import를 맞춰 본다. 빠진 의존성(DEP001), 쓰지 않는
  의존성(DEP002), 간접 의존성을 직접 import하는 것(DEP003) 등을 잡는다. `.ai/`는 뺀다. 공유 배치는 `.ai`를
  커밋하는데, deptry가 키트의 `kit` import를 빠진 의존성으로 읽기 때문이다.
- pytest 설정은 `pyproject.toml`에 둔다(pytest 9의 TOML 설정):

  ```toml
  [tool.pytest]
  strict = true
  markers = ["integration: needs services"]
  filterwarnings = ["error"]
  ```

  `strict`는 설정 오타, 등록하지 않은 마커, 통과해 버린 xfail, 겹치는 매개변수 id를 오류로 만든다.
  `filterwarnings = ["error"]`는 경고를 실패로 바꾼다. DB·Redis 같은 서비스가 필요한 테스트에는 `integration`
  마커를 붙인다. check의 tests 단계는 서비스 없이 돌아야 하니, 그런 테스트가 생기면 tests 단계 cmd에 `-m`,
  `not integration`을 더하고 검증 지도(`.ai/project/verification.md`)에 따로 돌리는 때를 적는다.

## Ruff 규칙 묶음

`select`를 명시한다. Ruff 0.16에서 기본 규칙이 59개에서 413개로 바뀌었고 0.17에서 또 바뀌었다. 목록을 적어 두면
버전이 올라도 규칙이 조용히 바뀌지 않는다. 다만 고른 묶음 안에도 새 안정 규칙이 들어오니, Ruff를 올릴 때마다 본다.
키트의 Ruff 규칙은 프로젝트가 고정한 Ruff 버전에서 동작하는 것만 쓴다.

| 묶음 | 켜는 이유 |
|---|---|
| F, E, W | 파이썬 오류와 기본 스타일 |
| I | import 순서 |
| UP | 지원하는 Python 버전의 문법 |
| B, SIM, C4, PIE, PERF | 흔한 버그와 불필요하게 복잡하거나 느린 코드 |
| RUF | Ruff 고유 규칙. RUF100은 필요 없어진 무시 주석을 잡는다 |
| ASYNC | async 엔드포인트 안의 블로킹 호출 |
| FAST | FastAPI의 Annotated 의존성, 중복된 response_model, 안 쓰는 경로 매개변수 |
| S, BLE, DTZ | 보안 규칙, 모든 예외를 삼키는 except, 시간대 없는 datetime |
| T20, ERA, ARG | 에이전트가 흔히 남기는 print, 주석 처리한 코드, 안 쓰는 인자 |
| LOG, PT | logging과 pytest의 잘못된 사용 |
| PGH | 뭉뚱그린 무시 주석을 막는다. 무시하려면 규칙 코드를 적어야 한다 |
| TID | 절대 import만 쓴다. banned_api로 금지 모듈과 고치는 방법을 알린다 |
| INP | 폴더마다 `__init__.py`. 없으면 그래프 기반 검사가 namespace package를 놓칠 수 있다(확인하지 않았다) |
| PL | 복잡도 한도 |

켜지 않는 묶음: TC(Pydantic·SQLAlchemy·FastAPI는 실행 중에 타입 주석이 필요하다), ANN(mypy strict가 맡는다),
COM·ISC·Q(포매터와 부딪힌다).

- `ignore`: E501·W191은 포매터가 맡는다. PLR0913·PLR0917(인자 개수)과 PLR2004(매직 값)는 잡음이 많다.
- `per_file_ignores`: 테스트 폴더(`**/tests/**`)에서는 assert(S101), 테스트용 비밀번호 문자열(S105·S106),
  안 쓰는 fixture 인자(ARG001), `__init__.py` 없는 폴더(INP001), 금지 모듈(TID251), 매직 값(PLR2004)을 허용한다.
- `allowed_confusables`: 한국어 문장에 쓰는 작은따옴표와 전각 문장부호를 RUF001~003에서 뺀다.
  “ ”는 Ruff 0.16.8이 잡지 않아서 넣지 않는다.
- `ban_relative_imports = "all"`: 상대 import를 막는다.
- `project_ignore`: 기존 코드에 많다는 것은 끄는 이유가 아니다. 기준선이 기존 위반을 빼 주므로 규칙을 켜 두고
  새 코드부터 바꾼다. 이 프로젝트에서 규칙이 틀렸거나 팀이 합의한 관례일 때만 `"코드": "이유"`로 넣는다.
  예: 팀이 라우터마다 `response_model`을 적지 않기로 정했으면 FAST001. 기존 위반 수를 코드별로 세어 보여 주고 사용자가 고른다.
- `banned_api`: 비워 두고 설치할 때 채운다. 아키텍처 조각의 "외부 호출은 clients에서만" 결정이 채운다
  (`templates/arch/layered/README.md`).

규칙 세트는 `--config` 인자로 넘어가 프로젝트의 Ruff 설정 위에 덧씌워진다. 팀 설정 파일은 바꾸지 않는다.
프로젝트 설정의 `ignore`·`extend-ignore`·`per-file-ignores`는 키트의 검사에 적용되지 않는다. 키트가 `ignore`와
`per-file-ignores`를 늘(비어 있어도) 넘기고, `select`가 규칙 선택을 새로 시작하기 때문이다. `extend-per-file-ignores`만은
Ruff 0.16.8이 `--config`로 덮어쓰지 않고 덧붙이기만 해서 그대로 적용된다. 그래서 새로 넣은 `extend-per-file-ignores`는
weakening 단계가 `config-weakening`으로 잡는다. 다만 읽는 설정 파일은 `pyproject.toml`, `ruff.toml`, `.ruff.toml`뿐이다.
Ruff의 `extend`는 다른 설정 파일을 불러오고 그 파일의 `extend-per-file-ignores`도 적용되는데, 이름이 이 셋이 아닌
파일(`lenient.toml` 등)에 더한 줄은 읽지 않는다. `extend = ...` 줄을 새로 넣는 것만 잡고, 이미 있던 `extend`가
가리키는 파일을 고치는 것은 놓친다.

## mypy

`strict`, `warn_unreachable`, 추가 오류 코드 일곱 개(`ignore-without-code`, `redundant-expr`, `truthy-bool`,
`possibly-undefined`, `unused-awaitable`, `deprecated`, `exhaustive-match`), `pydantic.mypy` 플러그인이다.
mypy 2.4.0이 일곱 코드를 모두 받는 것을 확인했다. pydantic을 쓰지 않는 프로젝트는 플러그인 줄과
`[pydantic-mypy]` 절을 지운다. 스텁이 없는 SDK는 모듈마다 `ignore_missing_imports`를 둔다.

## audit·mutate 프로필 더하기

`check`에 넣지 않는 검사다. 필요하면 `stages.json`에 단계를 더하고 `python3 .ai/checks/check.py audit`처럼 부른다.
기본으로는 둘 다 설정하지 않는다. `stages.json`은 보호 파일이라 더한 뒤 사용자가 approve를 다시 실행한다.

**audit**: 의존성 취약점 검사. 네트워크가 필요하다. Codex 기본 샌드박스처럼 네트워크가 꺼진 곳에서는
실패로 끝난다. 아래 명령은 조사 메모에서 가져왔고 실행해 보지 않았다.

```json
{
  "name": "audit",
  "kind": "command",
  "profiles": ["audit"],
  "cmd": ["uv", "audit", "--locked", "--preview-features", "audit-command"],
  "timeout": 600,
  "fix_hint": "취약한 의존성을 고친 버전으로 올린다. 사용자와 상의한다"
}
```

uv 프로젝트가 아니면 `pip-audit`을 개인 도구 환경에 넣고 같은 꼴의 단계로 부른다.

**mutate**: tidy-tests의 `falsify.py`로 테스트가 실제로 막는 변이를 잰다. 오래 걸리니 요청할 때만 돌린다.
변이 목록(`mutants.jsonl`) 쓰는 법은 `~/.agents/skills/tidy-tests/SKILL.md`에 있다. 경로에 `~`를 쓰지 않는다.
check는 셸을 거치지 않아서 펼쳐지지 않는다.

```json
{
  "name": "mutate",
  "kind": "command",
  "profiles": ["mutate"],
  "cmd": [
    "python3", "~/.agents/skills/tidy-tests/scripts/falsify.py",
    "--repo", "{live}", "--mutants", "{live}/.ai/project/mutants.jsonl",
    "--out", "{run_dir}/kills.json", "--cwd", "server",
    "--", ".venv/bin/pytest", "-q", "tests"
  ],
  "timeout": 3600,
  "fix_hint": "살아남은 변이를 잡는 테스트를 더한다. tidy-tests 절차를 따른다"
}
```

`falsify.py`는 모든 변이를 잡으면 0, 살아남은 변이가 있으면 1, 판단할 수 없으면 3으로 끝난다.
`command` 단계는 0을 통과, 1을 실패, 그 밖의 코드(사용법 오류 2, 실행하지 못한 126·127, 시그널)를 미완료로 본다.
그래서 `falsify.py`의 3도 미완료다.
