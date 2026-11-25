# Working rules

- Work on `dev-sp` for this project. Do not create a feature branch or another worktree unless the user explicitly requests it.
- Verify the checkout, branch, HEAD, and dirty files before editing. Do not switch unrelated worktrees or overwrite another task's changes.
- Complete each coherent change on `dev-sp` with a scoped commit. Include only that change's files. Use `git revert <commit>` to undo a committed change while preserving later work.
- Keep test code and candidate implementations in the same branch and record their validation status. Logs and generated replay results may live outside Git; identify the source commit and content hashes.
- Report the local commit and the device's active commit separately. A shared branch name, an uploaded test copy, or a successful replay does not establish deployment or activation.
- NEVER write unit tests after writing code. Prefer E2E validation with repeatable commands and verifiable artifacts. Before isolated testing, list the ways the system can fail.
