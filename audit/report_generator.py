"""Generate an HTML audit report from comparison results."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from audit.comparator import CompetitionComparison

log = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


def generate_report(
    comparisons: list[CompetitionComparison],
    output_path: Path,
) -> Path:
    """Render the HTML audit report and write it to output_path."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
    )
    env.filters["fmt"] = lambda v, f=".1f": format(v, f) if isinstance(v, (int, float)) else str(v)
    env.filters["sign"] = _sign_fmt
    env.filters["pct"] = lambda v: f"{v * 100:.1f}%" if isinstance(v, (int, float)) else str(v)

    template = env.get_template("report.html.j2")

    # Build summary stats
    total_comps = len(comparisons)
    total_tasks = sum(len(c.tasks) for c in comparisons)
    total_comparisons = sum(
        sum(tc.pilots_matched for tc in c.tasks) for c in comparisons
    )
    total_exact = sum(
        sum(tc.exact_matches for tc in c.tasks) for c in comparisons
    )
    total_close = sum(
        sum(tc.close_matches for tc in c.tasks) for c in comparisons
    )
    total_mismatch = sum(
        sum(tc.mismatches for tc in c.tasks) for c in comparisons
    )

    html = template.render(
        comparisons=comparisons,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        total_comps=total_comps,
        total_tasks=total_tasks,
        total_comparisons=total_comparisons,
        total_exact=total_exact,
        total_close=total_close,
        total_mismatch=total_mismatch,
        match_rate=f"{total_exact / total_comparisons * 100:.1f}" if total_comparisons else "N/A",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    log.info("Report written to %s", output_path)
    return output_path


def _sign_fmt(val: float | int | None, decimals: int = 1) -> str:
    if val is None:
        return "-"
    fmt = f".{decimals}f"
    if val > 0:
        return f"+{val:{fmt}}"
    return f"{val:{fmt}}"
