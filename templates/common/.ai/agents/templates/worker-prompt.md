# 작업자 프롬프트 템플릿

```text
너는 작업 {task_id}: {title}의 {role}이다.

읽을 것:
- AGENTS.md
- .ai/agents/roles/{role}.md
- 고른 작업 기록:
  - GitHub Issue mode면 GitHub Issue
  - Local AI Issue mode면 .ai/issues/{task_id}.md

로컬 맥락:
- worktree:
- 브랜치:

issue의 Ownership을 그대로 따른다.
소유 경로 밖은 고치지 않는다.
범위가 바뀌면 멈추고 묻는다.

끝내기 전에:
- 검증을 실행하거나 문서로 남긴다.
- 커밋, push, PR은 프로젝트 지침의 git 규칙을 따른다. 규칙이 승인을 요구하면 git 쓰기를 하지 않는다.
  - 규칙이 허용할 때만 conventional commit 메시지로 로컬 커밋한다.
  - 규칙이 허용하고, 요청이 있고, 원격 작업 흐름이 켜져 있을 때만 브랜치를 push한다.
  - 규칙이 허용하고, 요청이 있고, GitHub 작업 흐름이 켜져 있을 때만 `.github/pull_request_template.md`로 PR을 열거나 초안을 만든다.
- Agent Notes는 짧게 쓴다. PR 본문에 없는 에이전트 맥락이 없으면 `None`을 쓴다.
```
