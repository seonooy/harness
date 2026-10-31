#!/usr/bin/env bash
# 스킬, 작업 지침, 문서 틀을 현재 폴더에 설치한다. 모델을 부르지 않고, 있는 파일은 덮어쓰지 않는다.
# 사용: 작업 폴더에서  git clone https://github.com/seonooy/harness && bash harness/install.sh && rm -rf harness && codex
# 스킬 전체가 필요하면  bash harness/install.sh --all
set -euo pipefail

src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$PWD" = "$src" ]; then
  echo "작업 폴더에서 실행하세요: bash harness/install.sh" >&2
  exit 2
fi

core="brief code-review codebase-design diagnosing-bugs dispatch grilling handoff intake
kit-change kit-deslop kit-no-comments kit-quality-review kit-verify measure recap tdd
tidy-tests to-spec to-tickets"
want_all=no
[ "${1:-}" = "--all" ] && want_all=yes

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init -q
  echo "git 저장소를 만들었습니다."
fi

exclude="$(git rev-parse --git-path info/exclude)"
mkdir -p "$(dirname "$exclude")"
case "$src" in
  "$PWD"/*)
    entry="/${src#"$PWD"/}/"
    grep -qxF "$entry" "$exclude" 2>/dev/null || echo "$entry" >> "$exclude"
    ;;
esac

mkdir -p .agents/skills
for skill in "$src"/skills/*/ "$src"/templates/common/skills/*/; do
  name="$(basename "$skill")"
  if [ "$want_all" = no ] && ! printf '%s\n' $core | grep -qxF "$name"; then
    continue
  fi
  if [ -e ".agents/skills/$name" ]; then
    echo "그대로 둠: .agents/skills/$name"
  else
    cp -R "${skill%/}" ".agents/skills/$name"
  fi
done

find .agents/skills -type f \( -name '*.md' -o -name '*.py' \) -print0 |
  while IFS= read -r -d '' file; do
    if grep -qF '~/.agents/skills/' "$file"; then
      sed -i.bak 's#~/\.agents/skills/#.agents/skills/#g' "$file"
      rm -f "$file.bak"
    fi
  done

for doc in notes/requirements.md notes/system-map.md notes/eval.md DECISIONS.md; do
  if [ -e "$doc" ]; then
    echo "그대로 둠: $doc"
  else
    mkdir -p "$(dirname "$doc")"
    cp "$src/work/$doc" "$doc"
  fi
done

if ! grep -qsF '<!-- harness -->' AGENTS.md; then
  { echo; echo '<!-- harness -->'; cat "$src/AGENTS.work.md"; } >> AGENTS.md
fi

url="$(git -C "$src" remote get-url origin 2>/dev/null || echo local)"
commit="$(git -C "$src" rev-parse --short HEAD 2>/dev/null || echo unknown)"
paths="AGENTS.md .agents/skills notes/requirements.md notes/system-map.md notes/eval.md DECISIONS.md"
git add -f -- $paths
if git diff --cached --quiet -- $paths; then
  echo "이미 설치되어 있습니다."
elif git commit -q -m "chore: 작업 하네스 설치 ($url@$commit)" -- $paths; then
  git log -1 --format='커밋: %h %s'
else
  echo "커밋하지 못했습니다. git 사용자 설정을 확인한 뒤 직접 커밋하세요." >&2
fi

echo "설치했습니다. 스킬 $(find .agents/skills -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')개."
