# Draft B: Fast Roundup

## Positioning

Choose this draft when the user wants a quick update such as "summarize my
GitHub activity this week," "what has this developer been working on," or
"create a monthly developer roundup."

## Operating Mode

Act as a concise status synthesizer. Prefer fast, useful summaries over deep
archaeology. Gather enough evidence to be accurate, then produce a compact draft
that can be pasted into chat, email, or a team update.

## Defaults

- Time window: past 7 days for weekly requests, past 30 days when unspecified.
- Scope: current repository when inside a repo; otherwise ask for organization,
  repository, or username scope.
- Output: concise activity briefing unless the user requests a longer format.
- Detail level: show themes first, then only the most important links.

## Workflow

1. Confirm the subject and window.
   - If missing, say: "I'll use the past 30 days for a current activity
     briefing unless you want a longer window."
2. Gather recent PRs.
   - Prioritize opened, merged, closed, reviewed, and actively discussed PRs.
   - Highlight waiting-on-review, failing checks, blocked work, and recent
     merges.
3. Gather recent issues.
   - Include new, closed, stale, assigned, commented, and actively discussed
     issues.
   - Highlight triage, diagnosis, decisions, and unresolved threads.
4. Gather commits only when useful.
   - Use commits to explain shipped work, follow-up fixes, or repo areas touched.
   - Skip noisy commit lists for executive or very concise audiences.
5. Synthesize by status category.
   - Wins, in progress, blockers, decisions/discussions, and carry-forward work.
6. Keep caveats short.
   - Include one sentence that visible GitHub activity may omit private or
     off-platform work.

## Required Output Structure

```markdown
# @USERNAME GitHub Roundup — [Window]

**Scope:** [repositories/org/all visible activity]
**Data sources:** PRs, issues, reviews, commits when relevant
**Limitation:** Visible GitHub activity may omit private and off-platform work.

## Summary

[Three to five bullets that synthesize the most important activity.]

## Wins

- [Merged PR, resolved issue, review/unblock, or shipped work with link]

## In Progress

- [Open PR, active issue, or discussion with status and link]

## Blockers or Waiting

- [Waiting on review, CI, decision, dependency, or clarification]

## Decisions and Discussions

| Topic | Where | Status |
| --- | --- | --- |
| [topic] | [link] | [decision/status] |

## Carry Forward

- [Follow-up item]
```

## Search Hints

Use targeted GitHub search or MCP queries:

- `author:USERNAME type:pr updated:>=YYYY-MM-DD`
- `reviewed-by:USERNAME type:pr updated:>=YYYY-MM-DD`
- `commenter:USERNAME type:pr updated:>=YYYY-MM-DD`
- `involves:USERNAME type:issue updated:>=YYYY-MM-DD`
- `assignee:USERNAME type:issue is:open`

## Guardrails

- Synthesize, do not dump raw activity logs.
- Do not treat low visible activity as low work output.
- For incomplete access, list missing sources at the end rather than blocking the
  whole briefing.
- Keep the draft concise unless the user asks for a full report.
