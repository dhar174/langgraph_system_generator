---
name: "LNF: Agent & docs ecosystem sync"
about: Track work that keeps AGENTS.md, copilot-instructions.md, custom agent files, instructions, skills, MemoryBank, and LangChain/LangGraph resources mutually consistent and discoverable
title: "[LNF Docs Sync]: "
labels: documentation, lnf
assignees: ""
---

<!--
  Use this template when a contributor or AI agent notices that a capability,
  resource, or workflow is documented in one place but missing from — or
  inconsistent with — another part of the LNF docs/agent ecosystem.

  Key surfaces in this repo:
    - AGENTS.md                          ← contributor & agent onboarding
    - .github/copilot-instructions.md    ← GitHub Copilot context
    - .github/agents/*.agent.md          ← custom Copilot agents
    - .github/instructions/*.md          ← Copilot instruction files
    - .github/skills/*/SKILL.md          ← repo-level agent skills
    - skills/*/SKILL.md                  ← shared/mirrored skills
    - memory-bank/                       ← persistent agent memory
-->

## Summary

<!-- One sentence: what is out of sync or undocumented? -->

## Problem

<!-- Describe the gap.  Which resource is missing, stale, or not cross-linked?
     Example: "The `langchain-docs` MCP server is available to all custom agents
     but is not mentioned in AGENTS.md or any agent file, so contributors have
     no idea it exists." -->

## Affected surfaces

Check every surface that needs updating.

### Core onboarding & context
- [ ] `AGENTS.md`
- [ ] `.github/copilot-instructions.md`

### Custom agents (`/.github/agents/`)
<!-- List the specific agent files that need updating, e.g. lnf-rag.agent.md -->
- [ ] All LNF specialist agents (`lnf-*.agent.md`)
- [ ] Other affected agents:

### Instruction files (`/.github/instructions/`)
- [ ] `memory-bank.instructions.md`
- [ ] `langchain-python.instructions.md`
- [ ] Other affected instruction files:

### Skills
- [ ] `.github/skills/langchain/SKILL.md` (or equivalent)
- [ ] `.github/skills/langgraph-*/SKILL.md` (or equivalent)
- [ ] `skills/langchain/SKILL.md` (mirrored copy, if present)
- [ ] Other affected skill files:

### MemoryBank
- [ ] `memory-bank/activeContext.md`
- [ ] `memory-bank/systemPatterns.md`
- [ ] `memory-bank/techContext.md`
- [ ] `memory-bank/tasks/_index.md`
- [ ] Other MemoryBank files:

## Resources to add or cross-link

Check all resources that should be documented or referenced.

### Internal resources
- [ ] MemoryBank (`memory-bank/` directory and its core files)
- [ ] `.github/instructions/memory-bank.instructions.md`
- [ ] `.github/instructions/langchain-python.instructions.md`
- [ ] LNF specialist agents in `.github/agents/` (`lnf-*.agent.md`)
- [ ] LangChain/LangGraph skills in `.github/skills/`
- [ ] Mirrored LangChain/LangGraph skills in `skills/`

### MCP servers
- [ ] Built-in `langchain-docs` MCP server (provides live LangChain & LangGraph docs to agents)
- [ ] Other MCP servers relevant to this change:

### External documentation
- [ ] LangChain Python docs: <https://python.langchain.com/docs/>
- [ ] LangChain API reference: <https://python.langchain.com/docs/api_reference>
- [ ] LangGraph docs: <https://langchain-ai.github.io/langgraph/>
- [ ] LangGraph API reference: <https://langchain-ai.github.io/langgraph/reference/>
- [ ] LangSmith docs: <https://docs.smith.langchain.com/>
- [ ] Other external links:

## Requested changes

Describe the specific content additions or updates needed.

### AGENTS.md
<!-- What section(s) need to be added or updated? -->

### .github/copilot-instructions.md
<!-- What context is missing for Copilot? -->

### Custom agent files
<!-- Which agents need new tool references, `mcp-servers` entries, or body sections? -->

### Instruction files
<!-- What guidance is missing or stale? -->

### Skills
<!-- Which SKILL.md files need updating or creation? -->

### MemoryBank
<!-- Which memory-bank files need updating? -->

## Why this matters

<!-- Explain the downstream impact of leaving this undocumented.
     Examples:
     - AI agents cannot discover or use `langchain-docs` MCP server correctly.
     - New contributors reading AGENTS.md get an incomplete picture of available tools.
     - Context fragmentation slows LNF generation quality. -->

## Acceptance criteria

- [ ] All checked surfaces above have been updated
- [ ] Every mentioned resource includes at minimum: file path (internal) or URL (external)
- [ ] `AGENTS.md` explicitly lists the resource in a discoverable section
- [ ] `.github/copilot-instructions.md` includes the resource in agent context
- [ ] Any custom agent that benefits from the resource references it in its body
- [ ] MemoryBank files reflect the current documented state
- [ ] Where a skill exists in both `.github/skills/` and `skills/`, both copies are in sync

## Related issues / PRs

<!-- Link any related issues or pull requests here. -->

## Additional context

<!-- Any other notes, screenshots, or examples. -->
