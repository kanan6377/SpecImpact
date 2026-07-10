---
name: specimpact-ingest
description: Ingest local design sources and review host-proposed Dirty Excel graph regions.
---

# Ingest

Confirm that the source is inside the workspace. Select the correct mode and call `ingest_sources`
with one idempotency key. Poll `get_job`; do not retry under a new key while it is running.

Process each Dirty Excel Region through `prepare_graph_context` and `submit_graph_extraction`.
Use only the prepared Evidence IDs and node references. Respect elicitation or the localhost Grant
fallback. Report unresolved mentions and unsupported drawings rather than hiding them.
