# Managed Maintenance

Maintenance runs must preserve human edits outside managed blocks.

Use the managed markers emitted by the bootstrap scripts:

- `<!-- repo-agent-bootstrap:file-kind=... -->`
- `<!-- repo-agent-bootstrap:provenance=... -->`
- `<!-- repo-agent-bootstrap:managed:start -->`
- `<!-- repo-agent-bootstrap:managed:end -->`

Rules:

- replace only the managed block
- keep user prose before or after the managed block intact
- if a file has no managed block yet, append the generated block instead of deleting existing content
- surface drift instead of silently rewriting unrelated content
