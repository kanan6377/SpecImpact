# Integrations

## Neo4j

The default backend remains local JSONL. `specimpact backend set neo4j --uri <uri>` records an
optional Neo4j target without making Neo4j or a cloud service a default dependency. Switch back
with `specimpact backend set local`.

## Obsidian

SpecImpact can export an Obsidian review vault from the local JSONL graph. SpecImpact remains the
source of truth; Obsidian is used for dependency exploration, canvas review, and human notes.

```powershell
specimpact export-obsidian .\vault
specimpact export-obsidian .\vault --report-only
```

The standard export writes:

- `SpecImpact/Dashboard.md`
- `SpecImpact/Artifacts/*.md`
- `SpecImpact/Evidence/*.md`
- `SpecImpact/Changes/*.md` when an analysis run exists
- `SpecImpact/Canvases/*.canvas` when an analysis run exists

Artifact notes include frontmatter, Obsidian links, relation lists, and evidence links. The
standard Obsidian Graph View can show dependencies, Canvas can show the latest impact review, and
Dataview can list open review statuses.

`--report-only` preserves the legacy behavior and copies only the latest Markdown report.

## Review Import And Diff

`specimpact review import <json>` stores reviewer decisions locally. Use
`specimpact baseline create <name>` and `specimpact graph diff <name>` for relation comparison.
