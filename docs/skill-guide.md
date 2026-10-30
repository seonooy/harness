# 스킬 고르기

프로젝트에 넣을 스킬은 미리 정해 두지 않는다. 프로젝트를 셋업할 때 그 프로젝트에 맞는 것을 고르고,
쓰다가 필요해지면 그때 더한다. 이 문서는 고르는 기준과 후보 목록이다. 정답 목록이 아니다.

## 원칙

- 키트의 스킬 여섯 개는 늘 들어간다. 절차 `kit-change`·`kit-verify`·`kit-architecture`와 코드 품질 `kit-deslop`·
  `kit-no-comments`·`kit-quality-review`다. 나머지는 그 프로젝트에서 실제로 할 일이 있을 때만 넣는다.
- 전역에 이미 있는 스킬(`~/.agents/skills`, 플러그인)은 프로젝트에 또 넣지 않는다.
  Codex는 이름이 같은 스킬을 둘 다 보여 준다.
- 고른 스킬과 이유를 사용자에게 보이고 확인받은 뒤 넣는다. 지침 파일의 `## 스킬` 절에 "이럴 때 이 스킬"을
  한 줄씩 적는다.
- 엄격하게 막지 않는다. 넣지 않은 스킬도 전역에 있으면 부를 수 있다. 넣는 것은 이 프로젝트에서 자주 쓸
  스킬을 에이전트가 알아서 찾게 하는 일이다.
- 스킬은 **자동**(모델이 알아서 부른다)과 **수동**(사람이 `/이름`으로만 부른다)으로 나뉜다. 수동 스킬은
  `SKILL.md`에 `disable-model-invocation: true`와 `agents/openai.yaml`에
  `policy.allow_implicit_invocation: false`(Codex)를 함께 둔다. 수동 스킬은 다른 스킬이 부르지 못하고, 수동 스킬이
  자동 스킬을 부를 수는 있다. 출처는 `mattpocock/skills`의 `.agents/invocation.md`다.

## 고르는 기준

| 프로젝트 사정 | 볼 후보 |
|---|---|
| 계약을 테스트로 먼저 정한다(대부분) | tdd. 테스트가 기준대로 짜였는지 가끔 점검하려면 `$tidy-tests` |
| 명세에서 여러 작업으로 나눠 구현한다 | `$to-spec` → `$to-tickets` → 티켓마다 `$implement`, 브랜치 하나로 묶으면 `$implement-spec`. 이때도 `kit-change`를 따르고, 테스트 계획·리뷰·커밋은 `kit-change`의 "명세·티켓으로 구현할 때"대로 한다 |
| 도메인 모델이 중심이다(ddd 조각) | grill-with-docs, improve-codebase-architecture |
| 웹 화면이 있다 | gstack의 qa·browse, shadcn-ui |
| HTTP API·CLI가 있어 실제로 띄워 확인해야 한다 | pstack create-verification-skill(응용) |
| 같은 실수를 에이전트가 되풀이한다 | pstack correct(응용) |
| 중요한 변경을 다른 모델로도 리뷰하고 싶다 | pstack interrogate(응용). 한 모델의 품질 리뷰는 키트의 `kit-quality-review`가 한다 |
| 문서·글이 많다 | humanize |
| PR을 자주 쓴다 | pr |
| 에이전트 설명을 따라가기 어렵다 | wait-what |
| 에이전트가 이상하게 굴었던 세션을 돌아보고 싶다 | retro |

## 후보

| 스킬 | 출처 · 라이선스 | 하는 일 |
|---|---|---|
| tdd | Matt Pocock · MIT | 자동. 합의한 경계(seam)에서만, 한 번에 테스트 하나씩. 공개 인터페이스로만 확인하고 기대값은 코드와 따로 정한다. 경계마다 테스트 크기(단위·통합·E2E·없음)를 테스트 기준(`~/.agents/skills/tidy-tests/references/test-criteria.md`, 로컬 수정)으로 정한다. `kit-change` 5단계가 테스트를 쓰기 전에 이 스킬을 열고, `kit-verify`의 design이 계획 전에 테스트 기준을 연다 |
| to-spec, to-tickets, implement-spec, implement | Matt Pocock · MIT | 수동. 대화를 명세로, 명세를 서로 막는 관계가 적힌 티켓으로 나누고, 준비된 티켓을 worktree마다 동시에 구현한 뒤 마지막에 리뷰를 한 번 한다. `to-spec`은 모듈마다 테스트 크기와 E2E로 지킬 사용자 흐름을 테스트 기준으로 정한다(로컬 수정). 이슈 트래커가 필요해서 저장소마다 `$setup-matt-pocock-skills`를 먼저 한다 |
| code-review | Matt Pocock · MIT | 자동. 기준 커밋 이후 변경을 저장소 규칙과 명세 두 축으로 리뷰한다. |
| tidy-tests | 이 저장소 `skills/` | 수동. 테스트가 테스트 기준대로 짜였는지 점검하고, 변이로 보호 범위를 확인하며 계약 테스트로 정리한다. 테스트 기준 파일도 이 스킬에 있다 |
| grill-with-docs, grill-me | Matt Pocock `mattpocock/skills` v1.3 · MIT | 수동. 함께 답할 질문을 한 차례로 묶어 추천 답과 함께 묻는다. grill-with-docs는 `GLOSSARY.md`·`docs/adr`도 고친다. `grilling`(과 `domain-modeling`)을 부른다 |
| improve-codebase-architecture | Matt Pocock · MIT | 수동. 용어집과 ADR을 보며 구조를 깊게 만들 후보를 HTML 보고서로 보이고, 고른 것을 함께 다듬는다. `codebase-design`·`domain-modeling`·`grilling`을 부른다 |
| pr | Matt Pocock · MIT(요약 그림은 Dex Horthy `show-me`) | 자동. PR 본문을 가장 작은 그림 요약, 수정 전후 증거, 되돌리기 가능성과 영향 범위로 쓴다 |
| wait-what | Matt Pocock · MIT, 한국어로 고침 | 수동. 방금 설명을 맥락을 붙여 짧고 쉬운 말로 다시 하게 한다 |
| retro | Matt Pocock · MIT | 수동. 작업 기록을 읽고 코드가 아니라 작업 환경(길잡이, 자동 검사, 지침)을 고칠 후보를 낸다. 기계적인 위반은 지침보다 검사로 만든다. 문제가 있었던 세션에만 쓴다. `writing-for-agents`를 부른다 |
| grilling, domain-modeling, codebase-design, writing-for-agents | Matt Pocock · MIT | 자동. 위 스킬들이 부르는 도우미다. 따로 불러도 된다 |
| setup-matt-pocock-skills | Matt Pocock · MIT | 수동. 이 저장소의 이슈 트래커·라벨·용어집 자리를 정한다. 원본의 티켓 스킬(`to-spec`, `to-tickets`, `triage`)을 쓸 때만 필요하다 |
| shadcn-ui, stitch-* | 각 저장소 | 웹 UI 컴포넌트와 디자인 |
| pstack의 correct · how · why · blast-radius · create-verification-skill · interrogate | `cursor/plugins`의 `pstack` · MIT | 실수를 검사로 올리기, 코드 동작·이유 설명, 작은 변경이 깨는 곳 증명, 실사용 검증 스킬 만들기, 여러 모델 리뷰 | 아래 참고 |
| superpowers | `obra/superpowers` · MIT | brainstorming, writing-plans, systematic-debugging 같은 절차. 2026-10-23부터 구현 계획과 구현은 위의 Matt Pocock 흐름을 쓴다 |

### pstack을 쓸 때

pstack은 Cursor용으로 쓰여 있어(Task 도구, Grok 모델 이름) Codex에서는 그대로 돌지 않는다.
필요한 스킬만 응용해서 프로젝트 스킬로 만든다. 한국어로, 도구 이름 없이 다시 쓰고,
`SOURCE.md`에 출처(저장소·버전·MIT 고지)를 남긴다.

코드 품질 쪽은 이미 키트에 응용해 넣었다. 플러그인을 함께 켜면 같은 일을 두 번 하니 키트 쪽만 쓴다.

| 원본 | 키트에서 |
|---|---|
| cursor-team-kit `deslop` | `kit-deslop` |
| pstack `no-comments` + Comment Sicko | `kit-no-comments`. 서브에이전트는 diff가 클 때만 쓴다 |
| cursor-team-kit `thermo-nuclear-code-quality-review`, pstack interrogate의 품질 렌즈 | `kit-quality-review` |
| pstack `architect` | 여러 모델 경쟁 없이 설계 경고 목록과 "두 안 비교"만 `kit-change` 3단계에 넣었다 |
| pstack 원칙 스킬(model-the-domain, laziness-protocol, subtract-before-you-add, boundary-discipline, type-system-discipline, fix-root-causes, minimize-reader-load) | `kit-change` 5단계의 구현 원칙 다섯 줄 |
| pstack `poteto-mode`(언제 무엇을 부를지) | 늘 읽히는 Checks 절과 `kit-change`의 흐름. 따로 켜지 않는다 |

## 넣고 빼기

```sh
python3 .ai/checks/harness.py skills add ~/.agents/skills/grill-with-docs
python3 .ai/checks/harness.py skills list
python3 .ai/checks/harness.py skills remove grill-with-docs
```

- `add`는 스킬 폴더를 `.agents/skills/<이름>`에 복사한다(Codex가 읽는 곳). `--name`으로 이름을 바꿀 수 있다.
- 개인 배치에서는 이 경로를 `.git/info/exclude`와 `install.json`에 넣는다. `install.json`이 보호 파일이라
  넣고 뺀 뒤에는 사용자가 approve를 다시 한다. 다른 워크트리에서는 `harness.py link`를 다시 돌린다.
- 공유 배치에서는 넣은 스킬을 팀과 함께 커밋한다.
- 복사본이라 원본이 바뀌어도 따라가지 않는다. 새 판이 필요하면 `remove` 뒤 다시 `add`한다.
- 키트보다 먼저 손으로 넣어 둔 개인 스킬(`.agents/skills/<이름>`)은 그 경로로 `add`하면 복사 없이 등록만 한다.
  등록해야 다른 워크트리에서 `harness.py link`로 함께 연결된다.
- 외부 스킬은 그 폴더의 라이선스 파일도 함께 둔다. 없으면 `SOURCE.md`에 출처와 라이선스를 적는다.

## 선택: 이 프로젝트에서만 숨기기

전역 스킬이 너무 많아 헷갈리면 숨길 수 있다. 꼭 하지 않아도 된다.

- Codex: 스킬 끄기는 사용자 전역 `~/.codex/config.toml`의 `[[skills.config]]`(`path`, `enabled = false`)만 문서에 있다.
  프로젝트마다 끄는 방법은 문서에 없다.
- 확인한 날: 2026-10-20(Codex의 build-skills 문서).

## 지침 파일의 `## 스킬` 절

키트의 스킬과 수동 스킬을 언제 쓰고 권하는지는 "## Checks" 절(`templates/common/snippets/agents-checks.md`)에 있다.
설치하면 모든 프로젝트에 들어가니 `## 스킬` 절에 되풀이하지 않고, 그 밖에 이 프로젝트에서 고른 스킬만 적는다.

```markdown
## 스킬

- 테스트 먼저: `tdd`, PR 본문: `pr`
- 화면을 띄워 확인할 때: `gstack`의 qa·browse
```
