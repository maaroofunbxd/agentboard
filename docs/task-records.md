# Task record shapes

Three patterns cover most agent handoff needs. They are **related by idea** (goal, progress, next step) but **not one merged format** — each optimizes for a different scope.

## Summary

| | **HANDOFF.md** (templates) | **Work Kit** (`.workkit/tasks/*.md`) | **`work` records** (`records/*-KEY-*.md`) |
|---|---------------------------|--------------------------------------|-------------------------------------------|
| Scope | One active task per repo | Many tasks per repo, any repo | One file per ticket / own-work branch |
| Authority | You or the agent edit the file | `workkit` CLI + Markdown | `unbxd work start` / `work note` / git on branch |
| Ticket / Jira | Optional text | Optional `source:` metadata | **Built in** (URL, status, sites, excerpt) |
| Coordination | None (use `agents` separately) | Hooks only | **`agents open`** + board via unbxdtools |
| Audit of prod changes | No | No | **`journal/*.jsonl`** (opsjournal), separate from the record |

**Verdict:** Do **not** force Work Kit and `work` records into one schema. For Unbxd, **`work` records are authoritative** for ticket work. For arbitrary OSS repos, use **`templates/HANDOFF.md`** + **agentboard**. Work Kit's section list is a useful **checklist** when writing handoffs, not a migration target for `work`.

## `templates/` — single-task handoff (generic)

Files: `HANDOFF.md`, `PROJECT.md`, optional `AGENTS.md` merge.

- **PROJECT.md** — stable repo facts (purpose, constraints, verified commands).
- **HANDOFF.md** — current task only: goal, status, decisions, files, **one next action**, waiting-on.

Best for: side projects, libraries, any repo without `unbxd work`.

## Work Kit — multi-task Markdown (generic CLI)

Metadata: `- status:`, `- title:`, `- source:`, timestamps.

Sections: Goal → Context and decisions → Attempts and verification → Blockers → Notes → Next action.

Best for: several parallel agent tasks in one repo when you want `list` / `validate` / `resume` without Jira.

Overlap with HANDOFF: same narrative sections, stricter template and multiple files. Overlap with `work` records: Notes + next-step discipline only; **no** ticket/sites/`## Left` checklist.

## `work` records — ticket operations (Unbxd)

Created by `unbxd work start` (from Jira or own-work). Typical shape:

```markdown
# CW-1234: Summary line

- ticket: … (type, priority, status, assignee)
- branch: CW-1234
- sites: …
- started: … by …
- done: …   # when finished

## What

> excerpt from ticket …

## Left        # optional: open checkboxes for resume

- [ ] …

## Learned     # optional: durable runbook notes

…

## Notes

- timestamp: …
```

Plus beside the record (same branch): **`*.waits.jsonl`** for `agents open` (PR, board post, deadline, decision).

**Different on purpose:**

- **Metadata** is operational (ticket, branch, sites), not Work Kit's generic `source:` line.
- **`## What`** is ticket truth, not a free-form Goal.
- **`## Left`** is a resumable checklist (`unbxd work show`); Work Kit uses **Next action** (single step) instead.
- **`## Learned`** is runbook knowledge; Work Kit uses **Context and decisions** + **Attempts and verification**.
- **Notes** are the same idea (timestamped lines via `unbxd work note`).

### Optional alignment (documentation only)

When writing a `work` record or HANDOFF by hand, this mapping helps agents without changing files on disk:

| Work Kit section | `work` record |
|------------------|---------------|
| Goal | Title + `## What` |
| Context and decisions | `## Learned` + early Notes |
| Attempts and verification | Notes (what was tried / verified) |
| Blockers | `## Left` unchecked items or Notes |
| Next action | Top unchecked `## Left` item or last Note's "next:" |
| Waiting on | `agents open` / `*.waits.jsonl`, not the Markdown body |

No code change required unless you later want `workkit resume` to read `records/*.md` (a dedicated adapter, not a shared spec).
