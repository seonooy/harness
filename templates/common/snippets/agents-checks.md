## Checks

- 작업 중: `python3 .ai/checks/check.py fast` (경로를 붙이면 포맷·린트는 그 파일만 본다)
- 완료를 말하기 전: `python3 .ai/checks/check.py all`
- 결과 코드: 0 통과, 1 실패, 2 미완료(환경 미준비·시간 초과·해석 불가·테스트 0개·허용 안 된 skip). 0만 통과다.
- `ERROR <단계>: <고치는 방법>` 줄과 그 줄이 가리키는 로그를 읽고 원인을 고친다.
  `INFO` 줄의 기존 위반은 고치지 않는다.
- 문서·지침만 바꿨으면 `python3 .ai/checks/check.py doctor`와 참조 확인만 한다.
- 워크트리가 연결되지 않았다고 나오면 그 줄의 `harness.py link` 명령을 실행한다.
- 하지 않는 것:
  - 무시 주석 추가(`noqa`, `type: ignore` 같은 것)
  - 보호 파일 수정(`.ai/checks/`의 설정·기록·키트, `.codex/`)
  - 테스트 삭제, skip·xfail 추가
  - 도구 설정(`pyproject.toml`·`setup.cfg`·`conftest.py` 등)에서 검사 범위 줄이기(exclude, per-file-ignores,
    addopts, deselect 같은 것)
  - `git commit --no-verify`, `git push --no-verify`
- `harness.py approve`·`proposal apply`·`baseline adopt` 실행과 `.ai/checks/approvals.json` 수정은 사용자만 한다.
  보호 파일을 바꿔야 하면 `.ai/proposals/<이름>/`에 제안을 두고, 이유를 적어 사용자에게 적용을 요청한다.
- 문서: 목적 `.ai/project/intent.md`, 구조 `.ai/project/architecture.md`,
  검증 지도 `.ai/project/verification.md`, 변경 규칙 `.ai/project/rules.md`
- 절차: 구현·수정을 시작하기 전에 `kit-change` 스킬을 연다. 검증은 `kit-verify` 스킬을 따른다.
  - 완료조건은 통과해야 할 테스트나 명령으로 적는다. 같은 실패를 3번 고쳐도 그대로면 멈추고 보고한다.
  - 계약·데이터·판정이 바뀌면 구현 전에 `kit-verify`의 design으로 계약마다 테스트를 계획하고 사용자 승인을 받는다.
  - 구현이 끝나면 `kit-deslop`(군더더기 코드)과 `kit-no-comments`(주석)로 diff를 정리한다.
    여러 모듈에 걸치거나 새 모듈·공개 인터페이스를 만드는 변경은 `kit-quality-review`의 기준으로 리뷰한다.
  - 패키지의 아키텍처 스타일이나 패키지 사이 관계를 정하거나 바꿀 때는 `kit-architecture`를 따른다.
- 사람이 부르는 수동 스킬(`$이름`)은 직접 부르지 않는다. 맞는 때가 오면 답 끝에 한 줄로 권하고,
  같은 작업에서 거절하면 다시 권하지 않는다.
  - 여러 PR로 나뉘거나 조각끼리 서로 막거나 여러 세션에 걸칠 작업: `to-spec` → `to-tickets` → 티켓마다 `implement`
    (브랜치 하나로 묶으면 `implement-spec`). `docs/agents/issue-tracker.md`가 없으면 `setup-matt-pocock-skills`부터
  - 용어·결정이 정해지지 않았을 때 `grill-with-docs`, 구조를 깊게 만들 후보를 찾을 때 `improve-codebase-architecture`
  - 테스트가 기준에서 벗어나 보일 때 `tidy-tests`, 같은 실수가 되풀이된 세션 끝에 `retro`
- 스킬이 더 필요하면 후보와 이유를 사용자에게 말한다. 후보와 기준은 템플릿의 `docs/skill-guide.md`(템플릿 위치는
  `.ai/checks/install.json`의 `kit.template`)에 있다. 사용자가 좋다고 하면 `harness.py skills add`로 넣고, 사용자가 approve한다.
