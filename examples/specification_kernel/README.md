# Typed specification walkthrough

This deliberately small, authored fixture distinguishes an API's input constraint, a database's
capacity and a byte-oriented external interface. It is an engineering demonstration, not an
independent enterprise benchmark. Run from a disposable workspace; replace `<repo>` below.

```powershell
specimpact init
specimpact ingest <repo>/examples/specification_kernel/docs --aliases <repo>/examples/specification_kernel/aliases.yml
specimpact analyze <repo>/examples/specification_kernel/change.md --no-llm
specimpact analysis show
specimpact relations list
```

Initially relations are unconfirmed, so the typed analysis requests investigation. Read the
three original documents and confirm each appropriate relation explicitly:

```powershell
specimpact relations set-status <relation-id> confirmed
specimpact analyze <repo>/examples/specification_kernel/change.md --no-llm
specimpact analysis show
specimpact analysis replay
```

Expected after relation review: the API's maximum 128 conflicts with 256; the column capacity
512 satisfies this particular length requirement; the 128-byte external interface requires
encoding/conversion investigation. No source document is edited and no LLM call is needed.
`expected.json` is checked by the end-to-end test after explicit fixture relation confirmation.

The graph source archive and normalized Evidence remain local. `analysis export` includes
Evidence quotes and should be handled like the original design documents. Review decisions are
bound to an immutable analysis; changed prerequisites require new review.
