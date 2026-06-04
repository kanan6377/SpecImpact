# Optional Integrations

## Neo4j

The default backend remains local JSONL. `specimpact backend set neo4j --uri <uri>` records an
optional Neo4j target without making Neo4j or a cloud service a default dependency. Switch back
with `specimpact backend set local`.

## Obsidian

`specimpact export-obsidian <directory>` reuses the latest Markdown report.

## Review Import And Diff

`specimpact review import <json>` stores reviewer decisions locally. Use
`specimpact baseline create <name>` and `specimpact graph diff <name>` for relation comparison.
