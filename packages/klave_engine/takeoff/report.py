"""Quantity report serialization: CSV and markdown."""

import csv
import io
from pathlib import Path

from klave_engine.common.io import write_text
from klave_engine.takeoff.quantities import QuantityReport


def quantity_report_to_csv(report: QuantityReport, path: Path) -> Path:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["quantity", "value", "unit", "confidence", "source_detection_count"])
    for item in report.items:
        writer.writerow(
            [item.name, item.value, item.unit, round(item.confidence, 3),
             len(item.source_detections)]
        )
    return write_text(path, buffer.getvalue())


def quantity_report_to_markdown(report: QuantityReport) -> str:
    lines = [
        "## Quantity Report",
        "",
        f"Assumed unit: `{report.assumed_unit}`",
        "",
        "| Quantity | Value | Unit | Confidence |",
        "|---|---|---|---|",
    ]
    for item in report.items:
        lines.append(
            f"| {item.name} | {item.value:g} | {item.unit} | {item.confidence:.2f} |"
        )
    if report.warnings:
        lines += ["", "**Warnings:**"] + [f"- {w}" for w in report.warnings]
    return "\n".join(lines) + "\n"
