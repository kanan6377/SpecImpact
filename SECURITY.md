# Security Policy

SpecImpact is local-first. Please report security issues privately to:

`https://github.com/kanan6377/SpecImpact/security/advisories/new`

The same contact is recorded in `specimpact/resources/publication.json`. The packaged value is used
by the installed-wheel release gate.

Do not include confidential design documents, credentials, or API keys in a report.

Treat localhost ApprovalGrant tokens as secrets even though they expire after ten minutes and are
single-use. Reports about MCP workspace escape, symlink handling, CSRF/Origin validation, content
withholding, redaction, Agent Hooks, or Plugin configuration should include metadata-only
reproduction steps and synthetic documents.

## Supported Version

Security fixes target the latest v1.x release.
