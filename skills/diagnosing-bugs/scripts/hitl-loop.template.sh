#!/usr/bin/env bash
# 사람이 끼는(human-in-the-loop) 재현 루프.
# 이 파일을 복사하고, 아래 단계를 고친 다음 실행한다.
# 에이전트가 스크립트를 실행하고, 사용자는 자기 터미널의 안내를 따른다.
#
# 사용법:
#   bash hitl-loop.template.sh
#
# 도우미 함수 두 개:
#   step "<지시>"                 → 지시를 보여 주고 Enter를 기다린다
#   capture VAR "<질문>"          → 질문을 보여 주고 답을 VAR에 읽어 들인다
#
# 마지막에 캡처한 값을 에이전트가 파싱할 수 있게 KEY=VALUE로 출력한다.
#
# `capture`는 받은 값을 에이전트가 읽는 터미널에 그대로 다시 출력한다.
# 그러니 관찰한 것만 capture하고, 로그인은 사용자가 `step`으로 직접 하게 둔다.

set -euo pipefail

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [끝나면 Enter] " _
}

capture() {
  local var="$1" question="$2" answer
  printf '\n>>> %s\n' "$question"
  read -r -p "    > " answer
  printf -v "$var" '%s' "$answer"
}

# --- 아래를 고친다 ------------------------------------------------------

step "http://localhost:3000에서 앱을 열고 로그인하세요."

capture ERRORED "'Export' 버튼을 누르세요. 에러가 났나요? (y/n)"

capture ERROR_MSG "에러 메시지를 붙여 넣으세요(없으면 'none'):"

# --- 위를 고친다 --------------------------------------------------------

printf '\n--- 캡처한 값 ---\n'
printf 'ERRORED=%s\n' "$ERRORED"
printf 'ERROR_MSG=%s\n' "$ERROR_MSG"
