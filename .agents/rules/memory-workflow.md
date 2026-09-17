# Memory Workflow

mem0ry4ai is the repository's durable cross-session context layer. It is useful context, never a higher authority than current repository contracts or evidence.

## Authority order

When information conflicts, prefer this order:

1. current user instruction;
2. `AGENTS.md` and `GEMINI.md`;
3. applicable `.agents/rules/`;
4. `.archcore/` contracts and architecture;
5. active issue / task requirements;
6. current source code and tests;
7. current verified documentation;
8. mem0ry4ai durable memory;
9. tentative working-memory notes.

Never implement something merely because a memory says it was once true.

## Required agent-loop checkpoints

For non-trivial repository work, use this sequence:

`lnf-repo-coordinator -> Memory Scout -> Architecture Contract Scout -> Specialist Implementer -> Reviewer -> Tester -> Docsmith -> Memory Steward -> Coordinator closeout` (note that aside from lnf-repo-coordinator, Architecture Contract Scout, Memory Scout and Memory Steward, some agent names in this sample sequence are generalized)

### Start checkpoint: Memory Scout

Before substantive planning or implementation, the coordinator should invoke the `memory-scout` subagent.

The prompt should include:

- the current task / issue;
- the intended repository;
- important named components or files already known;
- a request for relevant status, todos, decisions, gotchas, facts, commands, and conflicts.

The coordinator should pass the resulting Memory Brief to downstream agents only where relevant. Do not flood every agent with unrelated recalled context.

A trivial task may skip Memory Scout when prior project context cannot materially affect the result.

### During-work checkpoint: Working notes

Agents may use `memory_note` for uncertain findings worth surviving context loss, but only when the mem0ry4ai MCP server is available and the note has likely future value during the active work.

Do not turn ordinary scratch reasoning into working memory.

A working note is not durable truth and must not override current repository evidence.

### Closeout checkpoint: Memory Steward

After implementation, review, tests, and documentation have settled the final truth, but before final coordinator closeout, invoke the `memory-steward` subagent.

Give it:

- the original task;
- the implementation result;
- reviewer findings and resolutions;
- test/validator results;
- documentation or Archcore changes;
- known unfinished work.

Memory Steward must search before every durable write and should prefer superseding stale memories over adding contradictory duplicates.

## What the coordinator should expect

A task is not blocked merely because there is nothing worth saving.

`memory-steward` may correctly return `action: none`.

Memory quality is more important than memory volume.

## Hooks versus semantic memory

Lifecycle hooks provide plumbing, diagnostics, context injection, transcript capture, checkpointing, or embedding. Hooks should not be treated as the primary semantic decision-maker for durable memory.

The specialized memory agents decide what is worth recalling or preserving because they can reason over the actual task and its verified outcome.

## Consolidation

Do not run either consolidation mechanism automatically at every closeout:

- transcript batch extraction is a fallback path that creates review candidates;
- store consolidation is periodic memory hygiene for duplicate/merge proposals.

Use them only when their specific purpose is warranted.
