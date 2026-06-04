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
row is required. Excel supports ordinary worksheets only; arbitrary layouts and merged-cell
interpretation are intentionally unsupported.
Corrupt workbooks are rejected as input errors without a traceback.

Individual structured and tabular ingest commands use stable filename-based document IDs. If a
second source with the same filename resolves to a different path, ingest fails with a document-ID
collision instead of replacing graph records silently.
