# Development Rules

## Workflow

- Every change starts from a GitHub issue.
- Never implement work without a ticket.
- Work only on the current issue scope.
- Do not invent new requirements.

## Before Coding

- Read the issue completely.
- Inspect only files relevant to the issue.
- Understand existing patterns before changing code.
- If the requirement is unclear, ask before implementing.

## Coding

- Make the smallest change that solves the issue.
- Follow existing architecture and conventions.
- Do not refactor unrelated code.
- Do not introduce new dependencies without approval.

## Validation

- Run relevant tests before finishing.
- Fix failures caused by your changes.
- Report test failures clearly.

## Git

- Keep changes focused.
- Do not commit generated files or unrelated modifications.

## Output
yes
- Be concise.
- Do not dump large explanations.
- At the end, summarize:
    - files changed
    - tests executed
    - remaining concerns

## vexp - Context-Aware AI Coding <!-- vexp v2.6.3 -->
vexp runs entirely on this machine: local daemon, index in `.vexp/`.
`run_pipeline` transmits nothing to any external service.
- `run_pipeline({ "task": "..." })` - orientation in one call (ranked pivot
  files with line ranges + blast radius + session notes) when a task does NOT
  name the files/symbols to touch. If it does, SKIP vexp - use your normal tools.
- `get_skeleton` - file structure at 70-90% token savings for files you only
  need to understand, not edit.
- `verify_done` - call once BEFORE declaring a multi-file task complete:
  returns mechanically broken references (imports of removed names, parse
  errors), untouched dependents of the files you changed (file:line), and
  the impacted tests - RUN those tests before declaring done.
- vexp may append a one-line hint to a prompt when orientation would help;
  otherwise it stays silent.

### Query shape (do this)
Anchor the task on real identifiers (ClassName, functionName) or file paths:
`run_pipeline({ "task": "fix JWT expiry in AuthService.validateToken" })`
<!-- /vexp -->