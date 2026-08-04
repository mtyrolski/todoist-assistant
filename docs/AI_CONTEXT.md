# Durable AI project context

Todoist Assistant stores durable, project-specific AI memory in ordinary Todoist
tasks. This makes the memory visible, editable, portable, and subject to the same
project boundaries as the work it describes.

## Task contract

A valid context task must satisfy both rules:

1. Its label is `ai_context` (shown as `@ai_context` in task text and parts of the
   Todoist UI).
2. Its title starts with the two literal characters `* `: an asterisk followed by
   one space.

For example:

```text
Title:       * Release policy
Description: Production releases require legal approval and a staged smoke test.
Label:       ai_context
```

`*Release policy` is not protected because it has no space. A task with the label
but without the prefix is ignored as invalid context. A `* ` task without the label
is protected from plugin deletion but is not sent to AI operations.

For automatic writes, the title must be a concise, explicit topic summary and the
description is required as a standalone explanation containing all durable detail a
future AI operation needs. Together they must make the task understandable without
reading its comments or the task that caused it to be created. Older or manually
authored title-only context remains readable so a later inline update can repair it.
Use several focused context tasks instead of one large project biography—for example,
`* Architecture`, `* Release policy`, and `* Stakeholders`.

## Dynamic aggregation

Context is not copied into a static cache. Before each AI operation that needs it,
Todoist Assistant fetches active tasks again and builds a fresh, lossless grouping:

```text
Project: Platform (3 context task(s))
- * Architecture: Events cross service boundaries through the public API.
- * Release policy: Run staging verification before production.
- * Stakeholders: Legal approves public announcements.
```

The aggregation contains every valid active context task in the selected project,
including its task ID and last-update timestamp in the structured payload. This has
two consequences:

- Editing a context task in Todoist affects the next AI operation without a separate
  synchronization step.
- Multiple context tasks accumulate; one does not replace the others.

AI breakdown receives only context from the task's exact project. Dashboard AI chat
receives current context grouped across projects so it can resolve the project named
in the conversation. Valid context is explicitly marked as high-priority,
authoritative project data: AI applies it before assumptions, transient activity
signals, and generic defaults. It is never treated as executable instructions, and
the current explicit user request plus system constraints still take precedence.
Prompt input is bounded to 100 tasks or 24,000 characters; when that boundary is
reached the prompt says that additional context was omitted.

## Automatic creation and updates

After analyzing a project, Codex may create or update context only when it discovers
a stable, reusable fact that should improve future work. Suitable examples include:

- architectural constraints and supported interfaces;
- durable delivery or review policies;
- explicit project goals, scope boundaries, or stakeholder decisions;
- recurring domain terminology that changes how tasks should be planned.

It must not store transient status, one-period metrics, guesses, credentials, routine
activity summaries, or a restatement of the current task.

AI breakdown can return at most three context updates in one response. Chat exposes
the constrained helper:

```python
upsert_ai_context(
    project_id,
    content,
    description="Complete standalone explanation",
    task_id=None,
)
```

Omit `task_id` to create a new topic. Pass an ID only when it belongs to an existing
valid context task in the same project. Cross-project and ordinary-task IDs are
rejected. Automatic creation requires both a title and a non-empty description.

## Non-regression guarantees

Automatic updates are monotonic: they may extend context, but they do not erase it.

- A proposed title change updates the existing task title inline while preserving the
  protected `* ` prefix.
- A shorter fragment already contained in the description is a no-op.
- A more complete statement containing the old description may replace the old text
  because all previous information remains present.
- Otherwise, new detail is appended after the existing description.
- An exact-title upsert updates the existing task instead of creating a duplicate.
- A merge above 12,000 description characters is rejected. Codex must create another
  focused context task instead of truncating existing knowledge.
- An update whose exact field-level `from`/`to` audit would exceed the safe
  single-comment bound is rejected before changing the task; Codex must create a
  separate focused context task instead.

These are literal preservation guarantees. They cannot prove that every generated
fact is correct, so context remains visible in Todoist and can always be reviewed or
edited by the user.

The title and description are always the current source of truth. Comments are never
used to store AI context. Creation and no-op upserts create no context comments. Only
after an existing context task is actually changed, Todoist Assistant adds one audit
comment to that same task. The comment lists each changed field and its exact `from`
and `to` values, leaving a permanent review trail without making AI depend on comment
history.

## Protection and lifecycle

Todoist Assistant treats every title beginning with literal `* ` as non-removable:

- the central plugin delete method refuses to delete it;
- stale-task cleanup skips it even if the configured exempt-label list changes;
- `ai_context` is also present in the default stale-task exempt labels;
- AI breakdown does not propagate `ai_context` to generated ordinary subtasks.

Protection applies to Todoist Assistant operations, not to Todoist itself. A user can
still complete, rename, move, or delete a task directly in Todoist. Completed or
deleted context is no longer part of the next active-task aggregation.

## Inspection helpers

Dashboard AI's constrained Python environment exposes:

```python
ai_context(project_id=None, project_name=None)
project_ai_context(project_id=None, project_name=None)
```

`ai_context` returns individual entries. `project_ai_context` performs a fresh fetch
and returns the grouped project payload with `contextCount` and every entry. Prefer the
grouped helper when checking whether the assistant has all current project knowledge.

## Verification

Automated coverage includes exact-prefix behavior, stale and delete protection,
multi-project aggregation, duplicate suppression, required self-contained creation,
monotonic merging, inline title/description updates, update-only audit comments, size
limits, cross-project update rejection, AI-breakdown prompt priority, and
dashboard-chat injection.

Run the complete repository gate with:

```bash
make test_all
```

Live smoke tests should use an empty project, record every created task ID, and delete
the exact IDs afterward through the raw Todoist API because the plugin correctly
refuses to remove protected fixtures. If an observer is running, do not attach
`ai-breakdown` to a temporary live task unless observer-created children are also
tracked and cleaned.
