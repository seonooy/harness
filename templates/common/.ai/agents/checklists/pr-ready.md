# PR Ready Checklist

Use this before pushing or opening a PR.

- [ ] Task record scope is satisfied.
- [ ] Acceptance Criteria are satisfied.
- [ ] Ownership was respected.
- [ ] No unrelated files changed.
- [ ] Verification ran, or the limitation is documented.
- [ ] PR template is complete.
- [ ] Numbered steps, task links, and review notes are in ascending order.
- [ ] Agent Notes are short, or `None` if there is no agent-specific context.
- [ ] Follow-up work is listed in Notes or a new task candidate.
- [ ] No secrets, `.env` values, or local-only paths were committed outside Agent Notes.

## After PR Opened

- [ ] PR targets the intended base branch and links the task record when applicable.
- [ ] `gh pr checks` or GitHub UI shows required checks completed or pending.
- [ ] CodeRabbit review was checked when enabled.
- [ ] Codex review was checked when enabled, or requested with `@codex review`.
- [ ] Automated review findings were fixed or explicitly deferred.
- [ ] Agent-specific follow-ups are in Agent Notes only when not already covered elsewhere.
