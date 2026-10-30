# Setup: 검사 키트

대상 프로젝트에 검사 키트를 들이는 절차다. 키트를 들이면 `check` 명령 하나가 포맷·린트·아키텍처·타입·
빠른 테스트와 약화 감시를 돌린다.

예: "agent-harness-template 보고 python·layered, 개인 배치로 셋업해줘."

## 조각

설치는 common + 언어 조각 하나 + 아키텍처 조각 하나 + project 조각이다. 언어는 python, 아키텍처는 layered와 ddd가 있다.

| 조각 | 담는 것 | 소유 |
|---|---|---|
| `templates/common` | 실행기(`checks/`), 절차 스킬 `kit-change`·`kit-verify`·`kit-architecture`, 코드 품질 스킬 `kit-deslop`·`kit-no-comments`·`kit-quality-review` | 키트 |
| `templates/stacks/python` | 단계 목록 두 벌, Ruff 규칙, mypy 설정, 빈 기준선 | 프로젝트 |
| `templates/arch/layered` | `architecture.md` 틀, import-linter 계약 틀 | 프로젝트 |
| `templates/arch/ddd` | 헥사고날 `architecture.md` 틀, import-linter 계약 틀, 용어집 `GLOSSARY.md`, 결정 기록 `docs/adr/` | 프로젝트 |
| `templates/project` | `intent.md`, 검증 지도, 변경 규칙 | 프로젝트 |

설치하지 않고 에이전트가 손으로 옮기는 것도 있다.

- `templates/common/snippets/agents-checks.md`: 지침 파일의 "## Checks" 절
- `templates/local-ai/snippets/agents-override.md`: 팀 지침 파일이 있는 저장소의 개인 지침 틀

키트 소유 파일은 설치할 때마다 템플릿 내용으로 바뀐다. 프로젝트에서 고치지 않는다. 프로젝트 소유 파일은
처음 설치할 때만 쓰고, 안의 `<<FILL: ...>>`를 채운다. 남아 있으면 `check doctor`가 2를 낸다.
설치 기록은 `.ai/checks/install.json`이다(조각, 배치, 파일마다 소유와 sha256, 템플릿 커밋).

## 설치되는 곳

두 배치 모두 같은 경로를 쓴다. doctor와 스킬이 이 경로를 읽는다.

| 경로 | 내용 |
|---|---|
| `.ai/checks/` | `check.py`, `harness.py`, `kit/`, `stages.json`, `ruff-rules.json`, `mypy.ini`, `importlinter.ini`, `baseline.json`, `install.json` |
| `.ai/project/` | `intent.md`, `architecture.md`, `verification.md`, `rules.md` |
| `.agents/skills/kit-*` | 절차·코드 품질 스킬(Codex) |
| `.ai/runs/` | 실행 결과, 비교 캐시. 어느 배치든 git 밖이다. 키트의 `.ai/.gitignore`가 막는다 |

## 배치

| | 개인 배치 | 공유 배치 |
|---|---|---|
| 쓸 때 | 팀 저장소에 내 하네스만 둔다 | 혼자 하는 새 프로젝트, 팀이 키트를 채택한 뒤 |
| git | 설치한 파일을 모두 `.git/info/exclude`에 넣는다. git이 추적하는 파일을 덮어야 하면 설치가 멈춘다. 팀이 이미 git으로 관리하는 `docs/adr/`처럼 프로젝트 파일만 드는 폴더는 팀 것을 그대로 쓴다(넣지도, 숨기지도, 워크트리에 연결하지도 않는다) | 설치한 뒤 바로 모두 커밋한다. 실행 결과는 `.ai/.gitignore`가 어느 클론에서나 git 밖에 둔다 |
| 단계 목록 | `--project-kind existing` → `stages.existing.json`. 프로젝트의 기존 도구와 호출 방식을 쓴다 | `--project-kind new` → `stages.new.json`. 모든 도구를 `.venv/bin`에서 바로 실행한다. `.venv`는 `uv sync --locked`로 먼저 만든다 |
| '새 위반' | `base_ref`와의 merge-base에서 같은 검사를 돌린 결과에 없는 위반. 다른 파일에서 옮겨 온 위반(코드·메시지·줄 글이 같고 원래 파일에서는 없어진 것)은 새 위반이 아니다 | `baseline.json`에 없는 위반. 기준선은 줄어들기만 한다 |
| 워크트리 | `harness.py link`로 개인 파일을 연결한다 | 커밋된 파일이 그대로 있다 |

- 단계 목록의 `placement`가 배치와 같아야 한다. 배치와 프로젝트 종류를 엇갈려 고르면(예: 기존 프로젝트를
  공유 배치로) 단계 목록의 `placement`, `baseline`, `protected`를 다른 쪽 틀에 맞춰 고친다.
- 공유 배치의 `stages.new.json`은 `.github/workflows/**`도 보호한다.

## 절차

설계 4.13의 일곱 단계에 스킬 고르기를 더한 여덟 단계다. 템플릿 경로는 `T`로 쓴다. 명령은 모두 대상 저장소 루트에서 실행한다.
`harness.py install`은 `--target`이 가리키는 저장소에, 나머지 `harness.py` 명령은 지금 폴더가 든 저장소에 작업한다.

### 1. 대상 확인

`docs/target-project-checklist.md`의 "검사 칸 조사"를 따른다. 언어·프레임워크, 기존 린트·타입·테스트·CI 설정,
팀 지침 파일과 개인 하네스 파일, exclude, 워크트리를 본다.

### 2. 설치와 문서 초안

```sh
python3 T/templates/common/checks/harness.py install --target . --stack python --arch layered \
  --placement personal --project-kind existing
```

- `--arch`는 루트 패키지의 첫 스타일이다. 요청을 받아 저장하는 일이 대부분이면 `layered`, 업무 규칙(불변식)이 많은
  도메인 중심이면 `ddd`(hexagonal)다. ddd는 용어집 `GLOSSARY.md`를 코드와 문서의 도메인 용어로 채운다. 둘 다 되돌리기
  어려운 구조 결정을 `docs/adr/`에 남긴다. 하위 패키지의 스타일이나 경계 나누기는 나중에 `kit-architecture`로 한다.
- `architecture.md`의 `## 패키지` 표에 루트 한 줄이 들어 있다. 고른 이유를 채운다. 계약 id는 `<패키지 짧은 이름>-<규칙>`이다.

- 새 프로젝트는 `--placement shared --project-kind new`다. 새 저장소라도 팀·회사 저장소에 올릴 수 있으면
  설치 전에 배치를 사용자에게 묻는다(`docs/target-project-checklist.md`의 "배치").
- 설치가 끝나면 다음 순서를 알려 준다: 채우기 → 사용자의 `approve`.
- `.ai/project/intent.md`와 `architecture.md`를 채운다. 에이전트가 기존 문서와 코드를 읽고 쓴다. 코드는
  계층 사이 import를 대조해서 본다. 사용자는 확인만 한다.
- 새 프로젝트는 intent와 고른 아키텍처로 쓰고, 빈 패키지 뼈대(`__init__.py`)를 만든다. 계약이 가리키는
  계층이 실제로 있어야 lint-imports가 돈다. 테스트도 하나 둔다. 수집된 테스트가 0개면 미완료다.
- 새 프로젝트는 검사 도구(Ruff, mypy, import-linter, pytest, pydantic, deptry)를 `pyproject.toml`의 dev 의존성에
  넣고 `uv lock`, `uv sync --locked`로 `.venv`를 먼저 만든다. check는 `.venv/bin`의 도구를 바로 실행할 뿐 `.venv`를
  만들거나 맞추지 않는다(`uv run`은 `--no-sync`여도 없는 `.venv`를 만든다). `.venv`가 없으면 단계는 미완료(2)이고
  `doctor`가 `uv sync --locked`를 알려 준다. `.venv`를 만들기 전에 `templates/stacks/python/README.md`의
  "새 프로젝트" 절을 열고, 그 pytest 설정과 deps 단계를 그대로 쓴다.

### 3. 규칙 설정

`architecture.md`의 `[검사]` 규칙만 설정으로 옮긴다. `[리뷰]` 규칙은 옮기지 않는다.

- `.ai/checks/importlinter.ini`: 쓰기 전에 고른 아키텍처의 README(`templates/arch/layered/README.md` 또는
  `templates/arch/ddd/README.md`)에서 "기본 규칙과 검사" 절을 연다. 계약 id를 `[검사: architecture/<id>]`와 맞추고,
  계약마다 `name`과 `broken_contract_guidance`(고치는 방법)를 둔다.
- `.ai/checks/ruff-rules.json`: 채우기 전에 `templates/stacks/python/README.md`의 "Ruff 규칙 묶음" 절을 연다.
  `banned_api`와 clients 폴더의 `per_file_ignores`를 채운다. 기존 프로젝트면 키트
  규칙으로 기준 브랜치를 한 번 검사해 코드별 개수를 보여 준다. 기존 코드의 습관은 끄는 근거가 아니다.
  규칙이 이 프로젝트에서 틀렸거나 팀이 합의한 관례인 것만 사용자가 골라 `project_ignore`에 이유와 함께 넣는다.
- `.ai/project/verification.md`(변경 → 최소 검증)와 `rules.md`(프로젝트 고유 변경 규칙)를 채운다.
  기존 프로젝트의 검증 절차와 변경 절차가 있으면 여기로 옮긴다.

### 4. 실행기 연결

`.ai/checks/stages.json`의 `<<FILL: ...>>`를 채운다. 기존 프로젝트는 commands, 단계마다의 cwd, 테스트 경로,
import_check, venvs, base_ref다. 테스트가 개발 DB·Redis를 가리키지 않게 `env`·`env_remove`도 정한다.

`venvs`에 적은 가상환경의 `bin` 폴더는 도구가 도는 동안 `PATH` 맨 앞에 놓인다(`uv run`이나 가상환경 활성화가 하는
일이다). 테스트가 `alembic` 같은 프로그램을 이름으로 불러도 호출한 쪽의 `PATH`가 아니라 프로젝트의 것이 잡힌다.
`VIRTUAL_ENV`는 정하지 않는다.

프로젝트에 없는 도구(mypy, import-linter)는 개인 도구 환경에 둔다. 네트워크를 쓰니 사용자에게 알리고 진행한다.

```sh
mkdir -p .ai/checks/tools
cp T/templates/stacks/python/tools-requirements.lock .ai/checks/tools/requirements.lock
uv venv --python <프로젝트와 같은 Python> .ai/checks/tools/.venv
uv pip sync --python .ai/checks/tools/.venv/bin/python .ai/checks/tools/requirements.lock
```

그다음 단계가 도는지 본다.

```sh
python3 .ai/checks/check.py fast
```

개인 배치의 `check all`과 `doctor`는 보호 파일의 지문 기록(`protected.json`)이 생기기 전까지 실패(1)를 낸다.
6단계의 approve 뒤에 확인한다. 공유 배치에는 이 기록이 없다. 공유 배치에서 설치할 때 이미 있는 위반은
`baseline.json`에 이유와 함께 적는다.

### 5. 스킬 고르기

`docs/skill-guide.md`의 기준으로 이 프로젝트에 맞는 스킬을 고른다. 미리 정해 둔 목록은 없다. 고른 스킬과
이유를 사용자에게 보이고 확인받은 뒤 `python3 .ai/checks/harness.py skills add <스킬 폴더>`로 넣고, 지침 파일의
`## 스킬` 절에 "이럴 때 이 스킬"을 한 줄씩 적는다. 넣을 게 없으면 8단계 보고에 "넣은 스킬 없음"과 이유를 적는다.
쓰다가 필요해지면 그때 더한다.

### 7. 팀 제안 준비(개인 배치)

검사 설정을 공유 위치(`pyproject.toml` 등)로 옮기고 CI 단계를 더하는 변경을 `.ai/proposals/<날짜>-checks/`에
패치(`git diff`)와 README로 준비한다. 올리거나 커밋하지 않는다. 브랜치·커밋·PR은 사용자가 승인할 때만 한다.

### 8. 보고

- 바뀐 파일
- `check all` 결과(종료 코드, 걸린 시간)
- 기존 위반 수(개인 배치는 INFO 줄의 수, 공유 배치는 기준선 항목 수)
- 남은 `[리뷰]` 규칙
- 넣은 스킬과 이유(없으면 "넣은 스킬 없음"과 이유)
- 다음에 쓸 말 예시: "kit-change로 <작업> 해줘", "kit-verify로 지금 diff 검증해줘"

## 지침 파일

- 팀 지침 파일이 없으면: `AGENTS.md`를 만들고 "## Checks" 절을 넣는다. 개인 배치면 이 파일을
  exclude와 `install.json`의 `private_paths`·`links`에 넣는다.
- 팀 지침 파일이 있으면: 팀 파일은 건드리지 않는다. `templates/local-ai/snippets/agents-override.md`를 틀로
  `AGENTS.override.md`를 만들고 그 아래에 "## Checks" 절을 넣는다.
  이미 있는 개인 지침은 지우지 않고 "## Checks" 절과 빠진 안내만 더한다. 이 파일은 common 조각의
  개인 파일·링크 목록에 이미 있다.
- "## Checks" 절은 짧게 둔다. Codex는 지침 파일 합계를 32 KiB로 자른다.

## 워크트리

개인 파일은 git에 없으니 `git worktree add`로 만든 워크트리에는 생기지 않는다. 새 워크트리에서 한 번 실행한다.

```sh
python3 <메인 체크아웃>/.ai/checks/harness.py link
```

- `install.json`의 `links`와 `stages.json`의 `venvs`를 메인 체크아웃으로 가는 절대 링크로 만든다.
- 연결 전에는 `check`와 `doctor`가 2와 위 명령을 알려 준다.
- `approve`는 메인 체크아웃에서 실행한다.

## 승인

검사를 약하게 만드는 변경(새 무시 주석, skip·xfail, 검사 범위를 줄이는 도구 설정, 지운 테스트, 보호 파일
변경)은 `check all`의 weakening 단계가 실패로 잡는다. 꼭 필요하면 사용자가 `.ai/checks/approvals.json`에 적는다. 에이전트는 승인을 스스로
만들지 않는다.

```json
{"approvals": [{"kind": "suppression", "path": "app/x.py", "text": "그 줄 내용", "reason": "허용하는 이유"}]}
```

- `kind`는 `suppression`, `skip`, `config-weakening`, `deleted-test`, `protected` 중 하나다. `text`는 그 줄의
  내용이고, `deleted-test`는 비운다. `protected`의 `text`는 배치마다 다르다(아래).
- `config-weakening`은 도구 설정 파일(`pyproject.toml`, `ruff.toml`, `.ruff.toml`, `pytest.ini`, `setup.cfg`,
  `tox.ini`, `conftest.py`)에 새로 넣은 줄 가운데 검사 범위를 줄이는 키를 정하는 줄이다. 키는 Ruff의
  `extend`(다른 설정 파일을 불러온다), `exclude`, `extend-exclude`, `extend-per-file-ignores`, `extend-ignore`,
  pytest의 `addopts`, `deselect`, `testpaths`, `norecursedirs`, `python_files`, `python_classes`,
  `python_functions`, `collect_ignore`, `collect_ignore_glob`, deptry의 `extend_exclude`, `per_rule_ignores`다.
  키를 쓰거나 대입하는 줄뿐 아니라 그 키의 값에 든 줄도 잡는다:
  키 이름의 TOML 표(`[tool.ruff.lint.extend-per-file-ignores]`)와 그 아래 줄, 여러 줄 목록에 더한 항목, INI의
  이어지는 줄(`addopts =` 아래 들여 쓴 `--deselect ...`), `conftest.py`의 `collect_ignore.append(...)`.
- 키를 쓰거나 대입하는 줄(`extend-exclude = ["app/x.py"]`)은 `text`가 그 줄 그대로다. 자리 때문에 잡힌 줄(표 머리와
  그 아래 줄, 목록에 더한 항목, 이어지는 줄, `collect_ignore.append(...)`)은 그 줄을 연 키를 앞에 붙인
  `<키>: <그 줄>`이 `text`다. 같은 `"tests",`도 `testpaths`에 더하면 `testpaths: "tests",`, `extend-exclude`에 더하면
  `extend-exclude: "tests",`라서 승인이 따로 필요하다. 승인할 `text`는 weakening 로그의 `|` 뒤에 있다. JSON 안에서는
  따옴표를 `\"`로 쓴다.

  ```json
  {"kind": "config-weakening", "path": "pyproject.toml", "text": "testpaths: \"tests\",", "reason": "허용하는 이유"}
  ```
- 이미 있던 항목을 다시 쓴 줄은 새 줄로 치지 않는다. 같은 변경 묶음에서 지운 줄과 공백, 끝의 쉼표, 끝의 주석만 다른
  줄은 같은 항목이다(`"a"` 뒤에 항목을 이으려고 `"a",`가 된 줄). 따옴표 안의 공백과 `#`은 항목의 일부다.
  `pytest.ini`, `setup.cfg`, `tox.ini`는 `#`과 `,`가 값의 일부여서 줄 앞뒤의 공백만 무시한다.
- 승인으로 넘어간 변경은 `check all`이 `INFO weakening: 승인으로 넘어갔다: ...` 줄로 보여 준다.

**개인 배치:** `protected`는 `text`를 비운다. `approvals.json`도 git 밖의 보호 파일이라, 적은 뒤 approve를
다시 실행한다.

**공유 배치:** 보호 파일이 모두 커밋돼 있으니 지문 기록이 없다. approve는 아무것도 쓰지 않고, doctor는
`protected.json`을 찾지 않는다. 보호 파일을 바꾼 브랜치에서 사용자가 승인을 적어 그 변경과 함께 커밋한다.

- `protected`의 `text`는 승인하는 파일 내용의 sha256이다(`shasum -a 256 <파일>`, Linux는 `sha256sum`).
  weakening 로그에도 지금 내용의 sha256이 있다. 그 뒤 파일을 또 바꾸면 승인도 새 sha256으로 고친다.
  지운 보호 파일은 `text`를 비운다.
- `approvals.json`의 변경은 보호 파일 변경으로 치지 않는다. 승인을 승인할 수는 없기 때문이다. 대신
  리뷰어가 브랜치의 diff와 INFO 줄로 승인을 본다.

## 알려진 한계

- pre-commit은 스테이징 영역이 아니라 작업 트리를 검사한다. 일부만 스테이징했으면 결과가 다를 수 있다.
- 공유 배치의 CI는 merge-base를 찾아야 하니 기준 브랜치까지 받는다(예: `actions/checkout`의 `fetch-depth: 0`).
- 도구 설정 약화(`config-weakening`)는 위 파일의 위 키만 본다. 이런 것은 잡지 못한다:
  - 한 줄 인라인 테이블 안의 키(`lint = { extend-exclude = ["app/x.py"] }`)
  - 다른 도구의 키(deptry의 `ignore`, coverage의 `omit`, `[[tool.mypy.overrides]]`의 `ignore_errors` 등)
  - Ruff의 `include`
  - Python 코드가 만드는 값(`collect_ignore = legacy()`이면 `legacy()`가 돌려주는 목록을 늘리는 것)
  - 목록에 없는 설정 파일(`mypy.ini`, `.coveragerc` 등)
  - Ruff의 `extend`로 불러온 파일. `extend = "lenient.toml"` 줄을 새로 넣는 것은 잡지만, 이미 있던 `extend`가
    가리키는 파일에 `[lint.extend-per-file-ignores]` 같은 것을 더하는 것은 따라가 읽지 않는다
  - 이름이 목록에 없는 기준 파일. `extend`가 가리키는 파일의 이름이 `pyproject.toml`, `ruff.toml`, `.ruff.toml`이
    아니면(`lenient.toml` 등) 그 안에 더한 줄을 읽지 않는다
- 거꾸로 패키징의 `exclude`처럼 검사와 상관없는 줄도 잡는다. 그때는 사용자가 승인한다. `pyproject.toml` 전체는
  보호하지 않는다. 의존성을 바꿀 때마다 승인이 필요해지기 때문이다.
- 프로젝트의 Ruff 설정에 이미 있던 `extend-per-file-ignores`는 키트의 검사에도 적용된다. Ruff가 `--config`로 그
  표를 지우지 못하기 때문이다. 새로 넣은 것만 `config-weakening`으로 잡는다. 이름이 목록에 없는 `extend` 기준
  파일에 넣은 것은 위 한계대로 잡지 못한다(`templates/stacks/python/README.md`).

## 정리

- `.ai/runs/<시각>-<프로필>-*` 폴더는 실행 한 번의 로그와 `result.json`이다. 오래된 것은 지워도 된다.
  `.ai/runs/cache`(merge-base 결과와 mypy 캐시)는 지워도 다시 만들어진다.
- 검사 도구(Ruff, mypy, import-linter, pytest)를 올리면 `.ai/runs/cache`를 지운다. 개인 도구 환경의 잠금 파일이
  바뀌면 merge-base 결과를 다시 만들지만, 프로젝트 가상환경의 도구 버전은 캐시 키에 들지 않는다.

## 키트를 지울 때

- `.git/info/exclude`의 `# agent-harness-template check kit` 아래 줄은 지워도 되고 남겨도 된다.
