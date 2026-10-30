# Worker Prompt Template

```text
You are {role} for task {task_id}: {title}.

Read:
- AGENTS.md
- .ai/agents/roles/{role}.md
- The selected task record:
  - GitHub Issue when in GitHub Issue mode
  - .ai/issues/{task_id}.md when in Local AI Issue mode

Local context:
- Worktree:
- Branch:

Follow the issue Ownership exactly.
Do not edit outside owned paths.
Stop and ask if scope changes.

Before finishing:
- Run or document verification.
- Commits, pushes, and PRs follow the git rules in the project instructions. If the rules require approval, do not make git writes without that approval.
  - Commit locally with a conventional commit message, only when the rules allow.
  - Push the branch if asked and remote workflow is enabled, only when the rules allow.
  - Open or draft a PR with `.github/pull_request_template.md` if asked and GitHub workflow is enabled, only when the rules allow.
- Keep Agent Notes short. Use `None` unless there is agent-specific context not already covered by the PR body.
```
