"""Risk report markdown rendering."""

from klave_engine.risks.rules import RiskReport

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def risk_report_to_markdown(report: RiskReport) -> str:
    lines = [
        "## Risk Report",
        "",
        f"Findings: {len(report.findings)} "
        + " ".join(f"({sev}: {count})" for sev, count in report.counts_by_severity.items()),
        "",
    ]
    ordered = sorted(
        report.findings, key=lambda f: (_SEVERITY_ORDER[f.severity.value], f.risk_id)
    )
    for finding in ordered:
        lines += [
            f"### [{finding.severity.value.upper()}] {finding.risk_type} ({finding.risk_id})",
            "",
            finding.message,
            "",
            f"**Recommended action:** {finding.recommended_human_action}",
            "",
        ]
    if not report.findings:
        lines.append("No risks detected.")
    return "\n".join(lines) + "\n"
