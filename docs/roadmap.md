# Roadmap

## v0.1.0-alpha: Excel Impact Review MVP

- Japanese SIer-style sample Excel project
- Excel folder ingestion
- Excel Health Check
- Change request analysis
- Evidence-backed reports
- Markdown / Excel / JSON output

## v0.2.0: Better Excel Profiling

- Improved sheet classification
- Header row detection
- Revision history extraction
- Alias candidate review
- Better warnings for dirty Excel files

## v0.3.0: SIer Excel Profiles

- Screen design profile
- API definition profile
- Table definition profile
- Validation rule profile
- External IF profile
- Test case profile

## v0.4.0: Excel Diff Impact

- before/after Excel comparison
- semantic design diff
- graph diff
- impact review from Excel changes

## v0.5.0: Review Board GUI

- Impact Review Board
- Evidence viewer
- Alias review UI
- relation confirmation/rejection
- Excel report export from GUI

## v1.0.0: Stable Local-first Excel Impact Review

- Stable schema
- Stable CLI
- Stable report format
- documented limitations
- real-world sample coverage

## v2.0.0: Dirty Excel Impact Management

- Dirty Excel workbook normalization with original preservation
- Sheet classification and logical region detection
- LLM/heuristic region proposals with evidence validation
- Alias inference and review from observed graph data
- Change Atom parsing and LLM-first impact retrieval
- Impact decision board with accepted/rejected/implemented/tested/closed states
- Dirty SIer Excel benchmark under `examples/dirty_sier_excel`
