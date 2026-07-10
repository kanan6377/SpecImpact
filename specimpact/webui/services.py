"""Backward-compatible Web imports for the UI-independent application service."""

from specimpact.application import service as _application

MUTATING_ACTIONS = _application.MUTATING_ACTIONS
aliases_data = _application.aliases_data
copy_demo = _application.copy_demo
demo_source = _application.demo_source
design_documents_data = _application.design_documents_data
dirty_excel_data = _application.dirty_excel_data
evidence_data = _application.evidence_data
external_preview = _application.external_preview
graph_data = _application.graph_data
impact_decisions_data = _application.impact_decisions_data
integration_data = _application.integration_data
project_overview = _application.project_overview
report_data = _application.report_data
review_queue_data = _application.review_queue_data
run_history = _application.run_history
source_library_data = _application.source_library_data
store_for = _application.store_for
tool_result = _application.tool_result

# These names remain patchable for downstream tests and integrations.
evaluate_dataset = _application.evaluate_dataset
release_validate = _application.release_validate


def execute(project, action, params):
    return _application.execute(
        project,
        action,
        params,
        _dependencies={
            "evaluate_dataset": evaluate_dataset,
            "release_validate": release_validate,
        },
    )


__all__ = [
    "MUTATING_ACTIONS",
    "aliases_data",
    "copy_demo",
    "demo_source",
    "design_documents_data",
    "dirty_excel_data",
    "evidence_data",
    "execute",
    "external_preview",
    "graph_data",
    "impact_decisions_data",
    "integration_data",
    "project_overview",
    "report_data",
    "review_queue_data",
    "run_history",
    "source_library_data",
    "store_for",
    "tool_result",
]
