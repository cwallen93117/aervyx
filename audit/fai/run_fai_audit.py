"""CLI entry point: scrape FAI competitions, import into Aervyx, score, and audit.

Usage:
    python -m audit.fai.run_fai_audit [OPTIONS]

Options:
    --event SLUG      Only process this event (by slug)
    --skip-import     Skip import, use existing state for comparison
    --skip-download   Skip IGC download (use existing files)
    --dry-run         Scrape and validate only, no API calls
    --report-only     Only generate report from existing state
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from audit import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("audit.fai")


def main() -> None:
    parser = argparse.ArgumentParser(description="FAI competition scoring audit")
    parser.add_argument("--event", type=str, help="Only process this event slug")
    parser.add_argument("--skip-import", action="store_true", help="Skip import phase")
    parser.add_argument("--skip-download", action="store_true", help="Skip IGC download")
    parser.add_argument("--dry-run", action="store_true", help="Scrape only, no API calls")
    parser.add_argument("--report-only", action="store_true", help="Report from existing state")
    parser.add_argument("--state-file", type=str, help="Path to import state JSON")
    parser.add_argument("--output", type=str, help="Output report path")
    args = parser.parse_args()

    output_dir = config.OUTPUT_DIR / "fai"
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = Path(args.state_file) if args.state_file else output_dir / "fai_import_state.json"
    report_path = Path(args.output) if args.output else output_dir / "fai_audit_report.html"

    from audit.fai.event_catalog import EVENTS, FaiEvent

    # Filter events
    events = EVENTS
    if args.event:
        events = [e for e in events if e.slug == args.event]
        if not events:
            log.error("No event found with slug: %s", args.event)
            sys.exit(1)

    log.info("=== FAI Scoring Audit ===")
    log.info("Processing %d events", len(events))

    # --- Phase 1: Scrape ---
    from audit.fai.scraper_airtribune import scrape_event as scrape_airtribune
    from audit.fai.scraper_civlcomps import scrape_event as scrape_civlcomps
    from audit.fsdb_parser import FsdbCompetition

    scraped: list[tuple[FaiEvent, FsdbCompetition]] = []

    if not args.report_only:
        for event in events:
            log.info("--- Scraping: %s (%s) ---", event.name, event.platform)
            try:
                if event.platform == "airtribune":
                    comp = scrape_airtribune(event)
                elif event.platform == "civlcomps":
                    comp = scrape_civlcomps(event)
                else:
                    log.error("Unknown platform: %s", event.platform)
                    continue

                log.info(
                    "  Scraped: %d pilots, %d tasks",
                    len(comp.participants), len(comp.tasks),
                )
                for task in comp.tasks:
                    log.info(
                        "    %s: %d results, %d turnpoints",
                        task.name,
                        len(task.participant_results),
                        len(task.turnpoints),
                    )
                scraped.append((event, comp))
            except Exception as exc:
                log.error("Failed to scrape %s: %s", event.name, exc, exc_info=True)

        if not scraped:
            log.error("No events scraped successfully")
            sys.exit(1)

        if args.dry_run:
            log.info("=== DRY RUN COMPLETE ===")
            for event, comp in scraped:
                log.info("  %s: %d pilots, %d tasks, formula=%s",
                         comp.name, len(comp.participants), len(comp.tasks), comp.formula.id)
            return

    # --- Phase 2: Download IGC ---
    from audit.fai.igc_downloader import download_and_extract, get_task_igc_dir

    igc_dirs_by_event: dict[str, dict[int, Path]] = {}  # event.slug → {task_id → dir}

    if not args.report_only and not args.skip_import:
        for event, comp in scraped:
            igc_dirs: dict[int, Path] = {}
            for task in comp.tasks:
                igc_url = event.igc_urls.get(task.fsdb_id)
                igc_dir = get_task_igc_dir(event.slug, task.fsdb_id)
                if igc_url and not args.skip_download:
                    log.info("  Downloading IGC for task %s (%s)", task.name, igc_url)
                    try:
                        download_and_extract(igc_url, igc_dir)
                    except Exception as exc:
                        log.warning("  IGC download failed for task %s: %s", task.name, exc)
                igc_dirs[task.fsdb_id] = igc_dir
            igc_dirs_by_event[event.slug] = igc_dirs

    # --- Phase 3: Import ---
    skip_import = args.skip_import or args.report_only

    if skip_import:
        log.info("Skipping import, loading state from %s", state_path)
        if not state_path.exists():
            log.error("State file not found: %s", state_path)
            sys.exit(1)
        from audit.fai.fai_importer import load_import_state
        import_states = load_import_state(state_path)
    else:
        if not config.API_USERNAME or not config.API_PASSWORD:
            log.error("Missing API credentials in audit/.env")
            sys.exit(1)

        from audit.api_client import AervyxClient
        from audit.pilot_registry import PilotRegistry
        from audit.fai.fai_importer import import_fai_competition, save_import_state, ImportResult

        client = AervyxClient(config.API_BASE_URL, config.API_USERNAME, config.API_PASSWORD)
        log.info("Logging into %s", config.API_BASE_URL)
        client.login()
        log.info("Authenticated")

        registry = PilotRegistry(client)

        import_results: list[ImportResult] = []
        for event, comp in scraped:
            log.info("=== Importing: %s ===", comp.name)
            igc_dirs = igc_dirs_by_event.get(event.slug, {})
            try:
                result = import_fai_competition(
                    client, registry, comp, event.timezone, igc_dirs
                )
                import_results.append(result)
                if result.errors:
                    for err in result.errors:
                        log.warning("  Error: %s", err)
            except Exception as exc:
                log.error("Import failed for %s: %s", comp.name, exc, exc_info=True)
                import_results.append(ImportResult(
                    competition_name=comp.name,
                    errors=[str(exc)],
                ))

        save_import_state(import_results, state_path)
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

    # --- Phase 4: Compare and Report ---
    log.info("=== Generating comparison report ===")
    from audit.api_client import AervyxClient
    from audit.comparator import compare_competition, CompetitionComparison
    from audit.fai.fai_report import generate_fai_report

    if not config.API_USERNAME or not config.API_PASSWORD:
        log.error("Missing API credentials for fetching results")
        sys.exit(1)

    client = AervyxClient(config.API_BASE_URL, config.API_USERNAME, config.API_PASSWORD)
    client.login()

    # Build name → comp mapping
    comp_by_name: dict[str, FsdbCompetition] = {}
    if not args.report_only:
        for event, comp in scraped:
            comp_by_name[comp.name] = comp
    else:
        # In report-only mode we don't have scraped data — need to re-scrape
        # or load from cache. For now, try scraping again.
        for event in events:
            try:
                if event.platform == "airtribune":
                    comp = scrape_airtribune(event)
                else:
                    comp = scrape_civlcomps(event)
                comp_by_name[comp.name] = comp
            except Exception as exc:
                log.warning("Re-scrape failed for %s: %s", event.name, exc)

    comparisons: list[CompetitionComparison] = []
    for state in import_states:
        name = state["name"]
        comp = comp_by_name.get(name)
        if comp is None:
            comparisons.append(CompetitionComparison(
                name=name, skipped=True, skip_reason="No scraped data",
            ))
            continue

        if state.get("skipped") and not state.get("event_id"):
            comparisons.append(CompetitionComparison(
                name=name, skipped=True,
                skip_reason=state.get("skip_reason", "skipped"),
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

    generate_fai_report(comparisons, report_path)
    log.info("=== Audit complete: %s ===", report_path)


if __name__ == "__main__":
    main()
