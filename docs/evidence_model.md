# Evidence Model

Evidence records include a stable ID, document/section/chunk references, short quote, type,
supported entity or relation references, and source location. Full document bodies are not logged
as evidence.

Evidence references persisted `sections.jsonl` and `chunks.jsonl` records. Local writes use a
temporary file followed by atomic replacement.
