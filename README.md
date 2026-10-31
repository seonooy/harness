# Codex Harness

Codex로 일할 때 쓰는 작은 스킬 모음이다. 작업 폴더의 터미널에서 실행한다. 모델을 부르지 않고, 있는 파일은 덮어쓰지 않는다.

```bash
git clone https://github.com/seonooy/harness && bash harness/install.sh && rm -rf harness && codex
```

## 스킬

| 부르는 말 | 하는 일 |
|---|---|
| `$start` | 시킨 조사를 하고 `notes/briefing.md`에 쌓는다 |
| `$plan` | `notes/plan.md`에 결정과 근거를 남기고, 사용자가 설명하고 승인하면 티켓으로 나눈다 |
| `$build` | 티켓마다 테스트 표, 구현, 검토, 커밋. 겹치지 않으면 worktree 병렬 |
| `$finish` | 점검, 문서 대조, 사용자 설명 |
| `$eval` | 골든셋이나 점수표로 재고 기준선과 전후 값을 남긴다 |
| `$handoff` | 상태를 `.handoff/`에 저장하고 새 세션에서 이어 한다 |

나머지 스킬은 위 여섯이 필요할 때 불러 쓴다.

## 출처

`skills/`의 폴더에 `LICENSE`와 `SOURCE.md`가 있으면 그 출처와 라이선스를 따른다. 나머지는 이 저장소의 MIT 라이선스를 따른다.
