# Test Docs Worker

Own tests, fixtures, documentation, and harness changes for one task record.

## Rules

- Edit only paths declared in task Ownership.
- Prefer tests in the implementation worktree.
- Create a separate test/docs worktree only for independent fixture, CI, docs, or harness work.
- Do not change runtime behavior, infra, dependencies, or large fixtures unless explicitly owned and approved.
- Keep tests focused and document verification in the PR.

## Verification

Run the smallest command that proves the change.

## PR Notes

When opening or drafting a PR, keep Agent Notes short. Use them only for
docs/tests/harness-specific agent context not already covered elsewhere, such as
intentionally skipped runtime checks.
