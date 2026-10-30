# ddd 조각

루트 패키지를 hexagonal(포트와 어댑터) 스타일로 시작하는 결정 문서 틀과, 그 결정을 검사로 옮기는 규칙 틀이다.
하위 패키지의 스타일이나 경계 나누기는 나중에 `kit-architecture`로 더하거나 바꾼다.
도메인 언어를 적는 용어집과 결정 기록 자리도 함께 둔다. 설치 절차는 `docs/setup-checks.md`에 있다.
이 README는 설치하지 않는다.

| 파일 | 설치 위치 | 소유 |
|---|---|---|
| `architecture.md` | `.ai/project/architecture.md` | 프로젝트 |
| `python/importlinter.ini` | `.ai/checks/importlinter.ini` | 프로젝트 |
| `GLOSSARY.md` | `GLOSSARY.md`(저장소 루트) | 프로젝트 |
| `adr/README.md` | `docs/adr/README.md` | 프로젝트 |

- `GLOSSARY.md`와 `docs/adr/`는 grill-with-docs·improve-codebase-architecture 스킬이 찾는 이름과 자리다. 그 스킬들이
  domain-modeling 스킬을 불러 용어를 정하는 대화에서 이 파일들을 직접 고친다. 개인 배치에서는 둘 다
  `.git/info/exclude`에 들어가고, 워크트리에 연결된다.
- 원본 스킬(Matt Pocock)이 v1.3.0에서 `CONTEXT.md`를 `GLOSSARY.md`로, `CONTEXT-MAP.md`를 `GLOSSARY-MAP.md`로 바꿨다.
  전역 스킬을 v1.3.0으로 올리면서(2026-10-23) 이 조각도 새 이름을 쓴다.
- 예전에 `CONTEXT.md`로 설치한 프로젝트는 다시 설치하기 전에 파일 이름을 `GLOSSARY.md`로 바꾼다. 그대로 다시 설치하면
  빈 `GLOSSARY.md`가 옛 파일 옆에 새로 생긴다. 옛 `/CONTEXT.md` 제외 줄은 설치 기록에 남으므로 git에 섞이지 않는다.

## 구조

```
bootstrap                      조립: 설정을 읽고 어댑터를 만들어 넣는다. 전부 import해도 된다
http | worker | adapters       바깥: 서로 import하지 않는다
application                    유스케이스와 포트
domain                         모델, 불변식, 순수 계산
```

import-linter `layers` 계약 하나가 이 그림을 그대로 검사한다. 위 줄은 아래 줄을 import해도 되고, 아래 줄은 위 줄을,
같은 줄의 형제는 서로를 import하지 못한다. 그래서 "application과 domain은 adapters를 모른다"와 "진입은 어댑터를
직접 쓰지 않는다"가 따로 계약 없이 함께 잡힌다.

## 기본 규칙과 검사

| 규칙 | 검사 | 메모 |
|---|---|---|
| `<루트>-layers` | import-linter `layers` 계약, `exhaustive = True` | 목록에 없는 하위 패키지도 위반이다. 쓰지 않을 층만 `(이름)`으로 둔다. 기준 브랜치에 아직 없는 모듈은 그대로 적는다(키트가 트리마다 그 트리에 없는 모듈을 계약에서 빼고 돌린다) |
| `<루트>-domain-pure` | import-linter `forbidden` 계약 | `source_modules`에 application과 domain, `forbidden_modules`에 웹 프레임워크와 이 프로젝트의 외부 변환기·JVM 연결·저장소 라이브러리를 적는다. 아무도 import하지 않는 이름이면 조용히 통과하니 철자를 확인한다 |
| `<루트>-ports-in-application`, `<루트>-invariants-in-domain` | 리뷰 | `.agents/skills/kit-architecture/styles/hexagonal.md`의 리뷰 체크리스트(Tactical DDD 포함) |

- 계약 조각의 정본은 `.agents/skills/kit-architecture/styles/hexagonal.md`이고, 이 조각의 `importlinter.ini`는 그 조각을
  루트 이름으로 채운 것이다. 외부 변환기·JVM 연결·저장소 라이브러리는 `<루트>-domain-pure`의 `forbidden_modules`에 더한다.
- context가 둘 이상이 되면 `kit-architecture`의 `relations/independent.md`(또는 events-only, separate-service)를 따른다.
- 도메인 모델을 pydantic으로 쓰는 프로젝트가 많다. pydantic을 domain에 허용할지는 프로젝트가 정하고 ADR로 남긴다.
  허용하면 `domain-pure`의 `forbidden_modules`에 넣지 않는다.

## 이미 있는 코드에 들일 때

이미 있는 코드는 처음부터 이 그림과 맞지 않는 경우가 많다. 그래도 계약은 목표 구조로 쓴다.

- 개인 배치는 merge-base에 이미 있던 위반을 판정에서 뺀다. 그래서 설치 직후에도 새로 만든 위반만 실패한다.
  `INFO architecture` 줄의 숫자가 남은 구조 부채다.
- 목표 층이 아직 패키지로 없으면 지금 있는 모듈 이름으로 가장 가까운 계약을 쓰고, 옮길 순서를 정한다.
  옮긴 뒤에 계약을 목표 이름으로 바꾼다. 계약을 바꾸는 일은 `kit-change`의 테스트 계획 승인을 거친다.
