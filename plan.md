# Plan: Developer Activity Story Skill Drafts

## Task Understanding

Create a new skill proposal for analyzing a GitHub user or developer's visible
work across pull requests, issues, commits, reviews, repositories, and
collaboration threads. The task explicitly asks for three competing drafts with
different approaches, plus reviewer instructions to score, rate, and rank the
three drafts.

## Reference Notes

- `repo-story-time` contributes repository archaeology, narrative structure,
  commit-history analysis, and evidence-backed storytelling.
- `roundup` contributes audience-aware status briefing, source synthesis,
  configurable scope, and concise weekly/monthly update patterns.
- `my-pull-requests` contributes narrow PR status extraction, review/check
  status, and actionable follow-up framing.
- `daily-issues-report` contributes issue-focused recency filters, stale-topic
  surfacing, and report-oriented summaries.
- `skill-creator` guidance favors concise skill bodies, strong frontmatter
  triggers, progressive disclosure, and bundled references for longer variants.

## Draft Strategy

Three competing approaches are included under
`.github/skills/developer-activity-story/references/`:

1. `draft-a-evidence-first-story.md`
   - Best for comprehensive narrative analysis.
   - Optimizes for evidence trails, privacy/fairness caveats, and story arcs.
2. `draft-b-fast-roundup.md`
   - Best for quick recurring updates.
   - Optimizes for short time windows, lightweight data gathering, and audience
     briefings.
3. `draft-c-impact-profile.md`
   - Best for self-review, performance review, promo packets, hiring packets,
     and maintainer/contributor profiles.
   - Optimizes for structured impact categories, scoreable evidence, and clear
     limitations.

The root `SKILL.md` is intentionally a review harness that explains when to use
this candidate skill and directs reviewers/users to choose among the drafts.

## TODOs

- [x] Read Memory Bank project context.
- [x] Read skill-creator guidance and validation scripts.
- [x] Review local `repo-story-time` skill.
- [x] Fetch referenced `roundup`, `my-pull-requests`, and
  `daily-issues-report` materials.
- [x] Initialize `.github/skills/developer-activity-story/`.
- [x] Write this plan and TODO list.
- [x] Write Draft A: evidence-first story.
- [x] Write Draft B: fast roundup.
- [x] Write Draft C: impact profile.
- [x] Validate the new skill with the repository skill validator.
- [x] Review repository diff for accidental unrelated changes.
- [ ] Run final validation tools.
- [ ] Open a PR that asks reviewers to score, rate, and rank the drafts.
- [ ] Add a PR comment repeating the reviewer scoring request.

## Reviewer Scoring Request

Reviewers should score each draft from 1 to 5 on:

- Discovery quality: frontmatter and trigger clarity.
- Workflow usefulness: ability to guide an agent through real user requests.
- Evidence discipline: links, source traceability, and limitation handling.
- Privacy and fairness: avoids unsupported productivity judgments and sensitive
  inferences.
- Concision and maintainability: avoids unnecessary context bloat.

Each reviewer should rank all three drafts and only suggest concrete changes for
the draft they score highest.
