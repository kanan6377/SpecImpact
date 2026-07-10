# Evidence Graph

> Markdown projection only. Local `.specimpact/*.jsonl` is authoritative. Nodes, relations,
> aliases, and proposals must be read from SpecImpact resources or reports before rendering.

## Scope

- Workspace: `<workspace>`
- Project ID: `<project_id>`
- Source: `<source_id or source path>`
- Graph status: `<ready|empty|stale|pending review>`

## Evidence Nodes

| Artifact | Type | Evidence IDs | Source metadata |
| --- | --- | --- | --- |
| `<display_name> (<artifact_id>)` | `<artifact_type>` | `<evidence_ids>` | `<source location>` |

## Relations

| From | Relation | To | Status | Evidence IDs |
| --- | --- | --- | --- | --- |
| `<from>` | `<relation>` | `<to>` | `<relation_status>` | `<evidence_ids>` |

## Pending Human Review

- Graph proposals: `<proposal IDs and evidence>`
- Alias candidates: `<candidate IDs and evidence>`
- Do not mark entries accepted until the matching SpecImpact mutation succeeds.
