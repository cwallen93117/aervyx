# OSS Reuse Evaluation And Integration Plan

## Goal

Choose the fastest, least fragile Phase 1 path by reusing proven open-source scoring and viewing software wherever it materially reduces risk or implementation time.

## Summary Decision Matrix

### AirScore

- Source: https://github.com/geoffwong/airscore
- Observed upstream shape: legacy web application with Perl modules such as `Gap.pm` and `IGC.pm`, plus PHP-style entry points such as `add_track.php`
- Role in FlightComp Phase 1: primary reference and schema-workflow alignment target
- Direct integration in Phase 1: no
- Practical reuse in Phase 1:
  - align event, task, upload, and results concepts with AirScore competition workflow
  - mirror AirScore-style scoring configuration fields such as nominal values and penalties
  - use AirScore task and result terminology in the API and UI where sensible
- Why not direct integration now:
  - direct embedding would force a second incompatible runtime and deployment model into the MVP
  - the current project stack is FastAPI plus Next.js, so a hard merge would add fragility instead of reducing it
- Deferred possibility:
  - import/export adapters or service-level interoperability after the Phase 1 MVP is stable

### IGCWebview2

- Source: https://github.com/GlidingWeb/IgcWebview2
- Observed upstream shape: JavaScript and HTML viewer intended for browser-based IGC viewing, with interactive mapping and altitude graphing behavior
- Role in FlightComp Phase 1: visualization reference and possible component-pattern source
- Direct integration in Phase 1: partial, reference-first
- Practical reuse in Phase 1:
  - borrow its track-viewer interaction model for uploaded flight review
  - reuse its ideas for task overlays, responsive viewing, and browser-first rendering behavior
  - adapt the viewer concepts onto MapLibre GL instead of Google Maps so the new stack stays consistent
- Deferred possibility:
  - port selected viewer logic into reusable React components if that proves faster than reimplementation

### igc_lib

- Source: https://github.com/marcin-osowski/igc_lib
- Observed upstream shape: Python library for parsing IGC logs, thermal extraction, and anomaly detection
- Role in FlightComp Phase 1: Python ingest reference and parser-validation aid
- Direct integration in Phase 1: targeted if packaging is practical, otherwise adapter/reference
- Practical reuse in Phase 1:
  - align the backend IGC ingest flow with its parsing and suspicious-log handling concepts
  - use its anomaly-detection ideas to shape upload metadata and validation flags
  - prefer compatible parsed-track structures so deeper reuse remains easy
- Deferred possibility:
  - swap the custom parser stub for a wrapped `igc_lib` integration if dependency behavior and licensing fit cleanly in the service image

### igc-xc-score

- Source: https://github.com/mmomtchev/igc-xc-score
- Observed upstream shape: JavaScript scoring tool usable from the CLI or as an embeddable library, with GeoJSON-oriented output and multiple implemented scoring rules
- Role in FlightComp Phase 1: scoring-helper reference and possible sidecar tool
- Direct integration in Phase 1: partial, likely through a thin adapter if needed
- Practical reuse in Phase 1:
  - reuse its GeoJSON-oriented output ideas for track and scoring visualization
  - reuse its deterministic scoring-helper patterns where they match task-analysis needs
  - evaluate a small Node sidecar or script bridge if it accelerates scoring verification for uploaded tracks
- Limits for Phase 1:
  - its built-in rule set is focused on XC and record-style scoring, not a full AirScore-style task competition workflow
  - therefore it is not the sole scoring engine for the MVP

### MapLibre GL

- Source: https://maplibre.org/maplibre-gl-js/docs/
- Role in FlightComp Phase 1: direct production dependency
- Direct integration in Phase 1: yes
- Practical reuse in Phase 1:
  - task builder map
  - turnpoint search and selection map
  - task overlay rendering
  - uploaded pilot track visualization

## Phase 1 Integration Decision

The project will use a hybrid reuse approach:

- direct dependency: MapLibre GL
- reference-plus-adapter: AirScore
- reference-plus-porting ideas: IGCWebview2
- targeted helper integration or adapter: `igc_lib`
- targeted helper integration or sidecar verification: `igc-xc-score`

## Concrete Implementation Commitments

Phase 1 code should reflect these choices by doing the following:

- use AirScore-aligned names and scoring configuration fields in the backend schema
- preserve immutable IGC evidence and parsed trackpoint separation
- shape map and track visualization around proven IGCWebview2 behaviors
- keep the scoring service modular so `igc_lib` or `igc-xc-score` adapters can be inserted without rewriting the API surface
- document exactly which parts are direct dependencies versus concept reuse

## Deferred OSS Work

The following are intentionally deferred until after the Phase 1 MVP is stable:

- direct AirScore runtime interoperability
- bulk import/export bridges with existing AirScore installs
- deeper IGCWebview2 code porting beyond viewer behavior patterns
- production sidecarization of `igc-xc-score` unless it becomes the clear fastest path during scoring implementation