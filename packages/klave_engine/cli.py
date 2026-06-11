"""Klave Engine CLI: stage-by-stage or full pipeline runs."""

from pathlib import Path

import typer

from klave_engine.common.config import get_settings
from klave_engine.common.logging import configure_logging

app = typer.Typer(name="klave", help="CPU-only construction drawing intelligence MVP")


@app.command()
def ingest(project_root: Path) -> None:
    """Scan a project folder and write its manifest."""
    from klave_engine.ingestion.project_loader import ingest_project

    settings = get_settings()
    configure_logging(settings.log_level)
    manifest = ingest_project(project_root, processed_dir_name=settings.processed_dir_name)
    typer.echo(f"Ingested {len(manifest.source_files)} drawing file(s) into {project_root}")


@app.command()
def convert(project_root: Path) -> None:
    """Convert DWG sources to DXF via the configured external converter."""
    from klave_engine.ingestion.manifest import load_manifest
    from klave_engine.pipeline import convert_drawings

    settings = get_settings()
    configure_logging(settings.log_level)
    manifest = load_manifest(project_root, settings.processed_dir_name)
    results = convert_drawings(manifest, settings)
    for result in results:
        typer.echo(f"{result.source_path}: {result.status.value}")
    if not results:
        typer.echo("No DWG files to convert")


@app.command()
def parse(project_root: Path) -> None:
    """Parse DXF files into normalized entities."""
    from klave_engine.ingestion.manifest import load_manifest
    from klave_engine.pipeline import parse_drawings

    settings = get_settings()
    configure_logging(settings.log_level)
    manifest = load_manifest(project_root, settings.processed_dir_name)
    drawings = parse_drawings(manifest, settings)
    total = sum(len(d.entities) for d in drawings)
    typer.echo(f"Parsed {len(drawings)} drawing(s), {total} normalized entities")


@app.command()
def process(project_root: Path) -> None:
    """Run the full pipeline: ingest, convert, parse, graph, detect, report."""
    from klave_engine.pipeline import run_full_pipeline

    result = run_full_pipeline(project_root)
    typer.echo(
        f"Processed {result.manifest.project_id}: "
        f"{len(result.entities)} entities, {len(result.detections)} detections, "
        f"{len(result.risk_report.findings) if result.risk_report else 0} risks"
    )


@app.command()
def report(project_root: Path) -> None:
    """Print the generated summary report."""
    summary_path = Path(project_root) / "reports" / "summary.md"
    if not summary_path.exists():
        typer.echo("No summary report found; run `klave process` first", err=True)
        raise typer.Exit(code=1)
    typer.echo(summary_path.read_text(encoding="utf-8"))


@app.command()
def demo(project_root: Path) -> None:
    """Create the synthetic demo project (deterministic DXF fixture)."""
    from klave_engine.evals.fixtures import write_demo_project

    paths = write_demo_project(Path(project_root))
    for path in paths:
        typer.echo(f"Wrote {path}")


if __name__ == "__main__":
    app()
