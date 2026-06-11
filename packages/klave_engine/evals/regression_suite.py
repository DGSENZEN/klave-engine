"""End-to-end regression suite: build the demo fixture, run the pipeline,
evaluate detections / graph / takeoff, and write eval_summary artifacts."""

import tempfile
from pathlib import Path

from klave_engine.common.config import get_settings
from klave_engine.common.io import write_json, write_text
from klave_engine.evals.detection_eval import evaluate_detections
from klave_engine.evals.fixtures import DEMO_GOLD, write_demo_project
from klave_engine.evals.graph_eval import detail_resolution_summary, evaluate_graph
from klave_engine.evals.takeoff_eval import evaluate_takeoff
from klave_engine.pipeline import run_full_pipeline


def run_regression_suite(project_root: Path | None = None, reports_dir: Path | None = None) -> dict:
    settings = get_settings()
    reports_dir = reports_dir or settings.reports_dir

    if project_root is None:
        project_root = Path(tempfile.mkdtemp(prefix="klave_eval_")) / "demo_project_001"
    write_demo_project(project_root)
    result = run_full_pipeline(project_root, settings)
    if result.graph is None or result.quantity_report is None or result.risk_report is None:
        raise RuntimeError("Pipeline did not produce graph/quantity/risk outputs")

    detection_results = evaluate_detections(result.detections, DEMO_GOLD["detections"])
    graph_results = evaluate_graph(result.graph, DEMO_GOLD["semantic_node_counts"])
    takeoff_results = evaluate_takeoff(result.quantity_report, DEMO_GOLD["quantities"])
    risk_types = {f.risk_type for f in result.risk_report.findings}
    missing_risks = [r for r in DEMO_GOLD["expected_risk_types"] if r not in risk_types]

    summary = {
        "project_id": result.manifest.project_id,
        "detection_eval": [r.model_dump() for r in detection_results],
        "graph_eval": [r.model_dump() for r in graph_results],
        "detail_resolution": detail_resolution_summary(result.graph),
        "takeoff_eval": [r.model_dump() for r in takeoff_results],
        "expected_risk_types_missing": missing_risks,
        "all_passed": (
            all(r.f1 == 1.0 for r in detection_results)
            and all(r.passed for r in graph_results)
            and all(r.passed for r in takeoff_results)
            and not missing_risks
        ),
    }

    write_json(reports_dir / "eval_summary.json", summary)
    write_text(reports_dir / "eval_summary.md", _render_markdown(summary))
    return summary


def _render_markdown(summary: dict) -> str:
    lines = [
        "# Evaluation Summary",
        "",
        f"Overall: {'PASS' if summary['all_passed'] else 'FAIL'}",
        "",
        "## Detections",
        "",
        "| Type | Expected | Predicted | P | R | F1 |",
        "|---|---|---|---|---|---|",
    ]
    for r in summary["detection_eval"]:
        lines.append(
            f"| {r['detection_type']} | {r['expected_count']} | {r['predicted_count']} "
            f"| {r['precision']} | {r['recall']} | {r['f1']} |"
        )
    lines += ["", "## Graph", "", "| Node type | Expected | Actual | Pass |", "|---|---|---|---|"]
    for r in summary["graph_eval"]:
        lines.append(
            f"| {r['node_type']} | {r['expected_count']} | {r['actual_count']} "
            f"| {'yes' if r['passed'] else 'NO'} |"
        )
    lines += ["", "## Takeoff", "", "| Quantity | Expected | Actual | %err | Pass |",
              "|---|---|---|---|---|"]
    for r in summary["takeoff_eval"]:
        lines.append(
            f"| {r['quantity_name']} | {r['expected_value']:g} | {r['actual_value']:g} "
            f"| {r['percentage_error']:g} | {'yes' if r['passed'] else 'NO'} |"
        )
    if summary["expected_risk_types_missing"]:
        lines += ["", "## Missing expected risk types"] + [
            f"- {r}" for r in summary["expected_risk_types_missing"]
        ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    result = run_regression_suite()
    print("PASS" if result["all_passed"] else "FAIL")
