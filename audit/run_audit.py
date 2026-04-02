"""CLI entry point: import Highland Challenge competitions into Aervyx and generate audit report.

Usage:
    python -m audit.run_audit [OPTIONS]

Options:
    --year YEAR       Import only this year's competition
    --dry-run         Parse and validate only, no API calls
    --skip-import     Skip import, use existing state file for report
    --report-only     Alias for --skip-import
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from audit import config
from audit.fsdb_parser import discover_competitions, parse_fsdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("audit")


def main() -> None:
    parser = argparse.ArgumentParser(description="Highland Challenge scoring audit")
    parser.add_argument("--year", type=str, help="Import only this year (e.g. 2025)")
    parser.add_argument("--dry-run", action="store_true", help="Parse/validate only")
    parser.add_argument("--skip-import", action="store_true", help="Skip import, report from state")
    parser.add_argument("--report-only", action="store_true", help="Alias for --skip-import")
    parser.add_argument("--state-file", type=str, help="Path to import_state.json")
    parser.add_argument("--output", type=str, help="Output report path")
    args = parser.parse_args()

    skip_import = args.skip_import or args.report_only
    state_path = Path(args.state_file) if args.state_file else config.OUTPUT_DIR / "import_state.json"
    report_path = Path(args.output) if args.output else config.OUTPUT_DIR / "audit_report.html"

    # --- Phase 1: Discover and parse FSDB files ---
    log.info("Discovering competitions in %s", config.HIGHLAND_ROOT)
    competitions = discover_competitions(config.HIGHLAND_ROOT)
    log.info("Found %d competition FSDB files", len(competitions))

    # Filter by year if requested
    if args.year:
        competitions = [
            (path, folder) for path, folder in competitions
            if args.year in folder or args.year in path.stem
        ]
        log.info("Filtered to %d competitions for year %s", len(competitions), args.year)

    # Parse all FSDB files
    parsed: list[tuple[Path, str, object]] = []
    for fsdb_path, folder_name in competitions:
        log.info("Parsing %s (%s)", fsdb_path.name, folder_name)
        try:
            comp = parse_fsdb(fsdb_path)
            log.info(
                "  %s: %d pilots, %d tasks",
                comp.name, len(comp.participants), len(comp.tasks),
            )
            for task in comp.tasks:
                results_with_pts = [r for r in task.participant_results if r.points > 0]
                log.info(
                    "    Task %s: %d results (%d with points)",
                    task.name, len(task.participant_results), len(results_with_pts),
                )
            parsed.append((fsdb_path, folder_name, comp))
        except Exception as exc:
            log.error("Failed to parse %s: %s", fsdb_path, exc, exc_info=True)

    if not parsed:
        log.error("No competitions parsed successfully")
        sys.exit(1)

    if args.dry_run:
        log.info("=== DRY RUN COMPLETE ===")
        log.info("Parsed %d competitions, %d total tasks, %d total pilots",
                 len(parsed),
                 sum(len(c.tasks) for _, _, c in parsed),
                 sum(len(c.participants) for _, _, c in parsed))
        # Print summary
        for fsdb_path, folder_name, comp in parsed:
            log.info("  %s (%s): %d pilots, %d tasks, formula=%s",
                     comp.name, folder_name, len(comp.participants),
                     len(comp.tasks), comp.formula.id)
        return

    # --- Phase 2: Import (or load state) ---
    if skip_import:
        log.info("Skipping import, loading state from %s", state_path)
        if not state_path.exists():
            log.error("State file not found: %s", state_path)
            sys.exit(1)
        from audit.importer import load_import_state
        import_states = load_import_state(state_path)
    else:
        # Validate credentials
        if not config.API_USERNAME or not config.API_PASSWORD:
            log.error("Missing API credentials. Set AERVYX_USERNAME and AERVYX_PASSWORD in audit/.env")
            sys.exit(1)

        from audit.api_client import AervyxClient
        from audit.pilot_registry import PilotRegistry
        from audit.importer import import_competition, save_import_state, ImportResult

        client = AervyxClient(config.API_BASE_URL, config.API_USERNAME, config.API_PASSWORD)
        log.info("Logging into %s", config.API_BASE_URL)
        client.login()
        log.info("Authenticated successfully")

        registry = PilotRegistry(client)

        import_results: list[ImportResult] = []
        for fsdb_path, folder_name, comp in parsed:
            comp_folder = fsdb_path.parent.parent  # Go up from "3. FS Scoring"
            log.info("=== Importing: %s ===", comp.name)
            result = import_competition(client, registry, comp, comp_folder)
            import_results.append(result)
            if result.errors:
                for err in result.errors:
                    log.warning("  Error: %s", err)

        save_import_state(import_results, state_path)
        # Convert to dicts for the comparison phase
        import_states = [
            {
                "name": r.competition_name,
                "event_id": r.event_id,
                "pilot_map": {str(k): v for k, v in r.pilot_map.items()},
                "task_map": {str(k): v for k, v in r.task_map.items()},
                "errors": r.errors,
                "skipped": r.skipped,
                "skip_reason": r.skip_reason,
            }
            for r in import_results
        ]

    # --- Phase 3: Compare and report ---
    log.info("=== Generating comparison report ===")
    from audit.api_client import AervyxClient
    from audit.comparator import compare_competition, CompetitionComparison
    from audit.report_generator import generate_report

    # Need a client for fetching results (even in report-only mode)
    if not config.API_USERNAME or not config.API_PASSWORD:
        log.error("Missing API credentials for fetching results")
        sys.exit(1)

    client = AervyxClient(config.API_BASE_URL, config.API_USERNAME, config.API_PASSWORD)
    client.login()

    # Build name → parsed comp mapping
    comp_by_name = {comp.name: comp for _, _, comp in parsed}

    comparisons: list[CompetitionComparison] = []
    for state in import_states:
        name = state["name"]
        comp = comp_by_name.get(name)
        if comp is None:
            log.warning("No parsed FSDB data for %s, skipping comparison", name)
            comparisons.append(CompetitionComparison(
                name=name, skipped=True, skip_reason="No FSDB data"
            ))
            continue

        if state.get("skipped") and not state.get("event_id"):
            comparisons.append(CompetitionComparison(
                name=name, skipped=True, skip_reason=state.get("skip_reason", "skipped"),
                event_id=state.get("event_id"),
            ))
            continue

        pilot_map = {int(k): v for k, v in state.get("pilot_map", {}).items()}
        task_map = {int(k): v for k, v in state.get("task_map", {}).items()}

        log.info("Comparing: %s (event_id=%s)", name, state.get("event_id"))
        try:
            cc = compare_competition(client, comp, pilot_map, task_map)
            cc.event_id = state.get("event_id")
            cc.errors = state.get("errors", [])
            comparisons.append(cc)
        except Exception as exc:
            log.error("Comparison failed for %s: %s", name, exc, exc_info=True)
            comparisons.append(CompetitionComparison(
                name=name, errors=[str(exc)], event_id=state.get("event_id"),
            ))

    generate_report(comparisons, report_path)
    log.info("=== Audit complete: %s ===", report_path)


if __name__ == "__main__":
    main()
