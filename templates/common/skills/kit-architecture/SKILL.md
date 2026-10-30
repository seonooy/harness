---
name: kit-architecture
description: 패키지의 아키텍처 스타일(layered·hexagonal), 패키지 사이 관계(independent·events-only·separate-service), 패키지 안 패턴(pipeline·plugin·task-queue)을 정하거나 바꿀 때 쓰는 절차. 보호 파일은 제안으로 만들고 사람이 proposal apply로 적용한다.
---

# 아키텍처 정하고 바꾸기

`.ai/project/architecture.md`의 표 세 개가 이 프로젝트의 결정이다.

- `## 패키지`: 패키지마다 스타일(layered 또는 hexagonal)과 이유(ADR 번호)
- `## 패키지 사이`: 경계를 나눈 패키지들의 관계(independent, events-only, separate-service)
- `## 패턴`: 패키지 안 모듈 하나에 쓰는 패턴(pipeline, plugin, task-queue)과 이유(ADR 번호)

스타일·관계·패턴의 정본은 이 폴더의 문서다. 고른 것 하나만 읽는다.

- `.agents/skills/kit-architecture/styles/layered.md`: MVC·계층
- `.agents/skills/kit-architecture/styles/hexagonal.md`: 헥사고날과 그 안의 Tactical DDD
- `.agents/skills/kit-architecture/relations/independent.md`: 경계 나누기(Strategic DDD)
- `.agents/skills/kit-architecture/relations/events-only.md`: 경계 사이는 이벤트로만
- `.agents/skills/kit-architecture/relations/separate-service.md`: 별도 서비스(MSA)
- `.agents/skills/kit-architecture/patterns/pipeline.md`: 파이프-필터(단계를 차례로 지나는 처리)
- `.agents/skills/kit-architecture/patterns/plugin.md`: 전략·플러그인(등록표로 구현 고르기)
- `.agents/skills/kit-architecture/patterns/task-queue.md`: 작업 큐·컨슈머(무거운 일을 워커로)

## 언제 쓰나

- 셋업할 때 루트 패키지의 스타일을 정할 때
- 새 패키지나 새 경계가 필요할 때(`kit-change` 3단계)
- 바꾸자는 신호가 보일 때(`kit-change` 11단계의 규칙 제안). 신호의 예:
  - 한 패키지에서 프레임워크·저장소 코드가 업무 규칙과 섞인다 → hexagonal
  - 단순 CRUD인데 헥사고날 층이 비어 있거나 한 겹 감싸기만 한다 → layered
  - 두 패키지가 서로의 내부를 import한다 → independent
  - 동기 호출로 묶인 경계가 같이 깨진다 → events-only
  - 따로 배포하거나 따로 늘려야 한다 → separate-service
  - 단계 본문 여럿이 한 파일에 모이거나 단계 하나만 다시 돌려야 한다 → pipeline
  - 구현을 가르는 if문이 여러 곳에 있다 → plugin
  - 요청 안에서 끝나지 않는 일을 뒤로 보내야 한다 → task-queue

## 패키지가 자리 잡는 곳

- 같은 경계 안의 하위 패키지는 부모 스타일의 층 하나에 들어간다. 부모가 hexagonal이면 보통 진입·어댑터 층이다.
  그 패키지는 부모의 application·domain을 쓰고, 부모는 그 패키지를 모른다. 부모의 `layers` 계약에 그 이름을 넣는다.
- 경계를 나누면 루트는 context 목록이 된다(bootstrap, context들, shared). 루트에 있던 모듈은 context 하나로 옮기고,
  옮기는 순서는 ADR에 적는다. 관계 문서의 "모양"에 루트 목록을 두는 법이 있다.
- 경계 사이의 기본은 독립이다. 관계 표의 줄은 허용(이벤트 모듈, 공유 계약)과 관계 종류를 적는다.
- 한 패키지에 스타일은 하나다.
- 패턴은 패키지 스타일의 한 층 안에 있는 모듈 하나에 쓰고, 스타일은 그대로 둔다. 패턴 표의 줄은 그 모듈(`자리`)과
  패턴 이름이고, 계약 id는 그 모듈의 짧은 이름으로 시작한다(`app.services.pipeline` → `pipeline-shape`). 한 모듈에 패턴은 하나다.

## 순서

1. 신호와 근거(파일과 import 몇 줄)를 사용자에게 보이고 결정을 받는다. 에이전트가 혼자 바꾸지 않는다.
2. `docs/adr/`에 ADR 한 장을 쓴다: 무엇을, 왜, 기존 코드를 옮기는 순서.
3. `architecture.md`의 표와 `## 규칙` 줄을 고친다. 규칙 줄은 고른 문서의 것을 패키지(패턴이면 그 모듈) 이름으로 채운다.
   hexagonal을 처음 쓰면 루트의 `GLOSSARY.md`(용어집)를 만든다.
4. 보호 파일은 직접 고치지 않고 제안으로 만든다. `.ai/proposals/<날짜>-<이름>/` 아래에
   - `README.md`: 첫 줄이 이유다. 예: `ADR 0003: app.admin을 layered로`
   - `files/.ai/checks/importlinter.ini`: 고른 문서의 계약 조각을 그 패키지(패턴이면 그 모듈)로 채워 넣은 새 전체 내용.
     그 패키지의 이전 스타일 계약은 뺀다.
   - 필요하면 `files/.ai/checks/ruff-rules.json`(금지 API)

   계약 id는 `<패키지 짧은 이름>-<규칙>`이다(`app.notes` → `notes-layers`). 기준 브랜치나 다른 워크트리에 아직 없는
   모듈도 그대로 적는다. 키트가 트리마다 그 트리에 없는 모듈을 계약에서 빼고 돌리고, 뺀 것을 `INFO architecture` 줄로
   알린다. `(이름)`은 쓰지 않을 층에만 쓴다.
5. 사용자에게 `python3 .ai/checks/harness.py proposal apply <이름>`을 돌려 달라고 한다. 사람만 돌린다.
   공유 배치면 이어서 `python3 .ai/checks/harness.py baseline adopt --stage architecture --reason "ADR <번호>"`도 사람이 돌린다.
6. `python3 .ai/checks/check.py doctor`와 `python3 .ai/checks/check.py all`을 돌린다. 기존 코드의 위반은 INFO로 빠지고
   새 위반이 없어야 한다.
7. 기존 코드를 옮기는 일은 프로젝트의 작업 기록(이슈, tasks, worklog 중 쓰는 곳)에 남긴다.
