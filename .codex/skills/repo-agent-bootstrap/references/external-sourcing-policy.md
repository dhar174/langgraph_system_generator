# External Sourcing Policy

This skill can vendor third-party prompts, skills, hooks, or workflows, but only conservatively.

Required before vendoring:

1. pinned commit SHA or version tag
2. source repository URL
3. original file path
4. license/provenance note
5. repo-specific reason the asset is worth importing

Prefer generating original content when:

- the repo is unusual enough that a generic asset would need heavy rewriting
- licensing is ambiguous
- the external asset is broad but the repo needs only a small focused workflow

Reject imports that reference floating revisions such as:

- `main`
- `master`
- `latest`
- unqualified default branches
