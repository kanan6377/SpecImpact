# Evidence Model

Schema-v2 analysis snapshots add a SourceAnchor with the ingested document hash, quote hash,
file/line and available sheet/cell addresses. Labelled specification assertions bind property
values to these anchors. Reference validity is distinct from property/path/rule verification.
Snapshots retain normalized Evidence; they do not imply an archived binary copy of every input.
See [Specification kernel](specification_kernel.md).

Evidence records include a stable ID, document/section/chunk references, short quote, type,
supported entity or relation references, and source location. Full document bodies are not logged
as evidence.

Evidence references persisted `sections.jsonl` and `chunks.jsonl` records. Local writes use a
temporary file followed by atomic replacement.
