# Structured Loaders

## OpenAPI

`specimpact ingest-openapi <yaml-or-json>` extracts operations, endpoint/method, inline request
fields, inline response fields, and schema names into the common local graph collections.
Evidence locations use YAML property node marks, so repeated field names in metadata, request
bodies, and responses retain their scoped source lines.
Malformed OpenAPI mapping structures are rejected as input errors without a traceback.

## SQL DDL

`specimpact ingest-ddl <sql>` extracts tables, columns, and straightforward constraints into the
common local graph collections. The parser intentionally supports simple `CREATE TABLE` statements
and does not attempt full SQL dialect coverage. Column evidence lines are calculated inside each
table definition.

## CSV And Excel

`specimpact ingest-csv <csv>` and `specimpact ingest-excel <xlsx>` extract simple tables. A header
row is required. Excel supports ordinary worksheets and table-like SIer sheets.
Corrupt workbooks are rejected as input errors without a traceback.

For legacy spreadsheets, free-layout Excel, merged cells, and mixed logical regions, use:

```powershell
specimpact ingest-dirty-excel <workbook-or-directory>
```

The dirty path preserves original files, normalizes cells with styles and merged ranges, renders
cell-addressed Markdown/HTML, detects regions, and writes graph proposals before analysis.
See [input_preparation.md](input_preparation.md).

Individual structured and tabular ingest commands use stable filename-based document IDs. If a
second source with the same filename resolves to a different path, ingest fails with a document-ID
collision instead of replacing graph records silently.
