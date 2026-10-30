# 개인 작업 지침

이 파일, `.ai/`, `.agents/skills/kit-*`는 이 클론에만 둔 개인 하네스다. git에 올리지 않는다.
팀 지침 파일이 이미 있는 저장소에서 쓴다. Codex는 이 파일을 직접 읽는다.

## 시작할 때

1. 팀 지침 `AGENTS.md`(있으면)를 먼저 읽는다.
   Codex는 같은 폴더에 이 파일이 있으면 `AGENTS.md`를 읽지 않는다. 그래서 직접 읽는다.
2. `git status --short --branch`와 작업에 관련된 코드를 확인한다.
3. `.ai/project/intent.md`로 프로젝트의 목적과 지금 단계를 확인한다.
4. 구현·수정은 `kit-change`, 검증은 `kit-verify` 스킬을 따른다.

팀 규칙과 이 파일이 부딪히면 팀 규칙이 이긴다. git 쓰기(commit·push·branch)는 팀 규칙과
사용자가 허락한 범위에서만 한다.

<!-- 아래에 templates/common/snippets/agents-checks.md의 "## Checks" 절을 그대로 넣는다. -->
