"use client";

import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { SectionCard } from "../SectionCard";
import type {
  AirspaceCategoryOption,
  AirspaceSourceRecord,
  EventFormState,
  EventRecord,
  EventTab,
  MapAirspaceRegion,
  PilotRecord,
  ScoringPresetRecord,
  TurnpointRecord,
  TurnpointSourceRecord,
  TurnpointUploadResponse,
} from "./types";

const builtInFormulaOptions = [
  { value: "GAP2021", label: "GAP 2021" },
  { value: "GAP2020", label: "GAP 2020" },
  { value: "GAP2018", label: "GAP 2018" },
  { value: "GAP2016", label: "GAP 2016" },
  { value: "GAP2008", label: "GAP 2008" },
  { value: "OzGAP2005", label: "OzGAP 2005" },
  { value: "PWC2016", label: "PWC 2016" },
] as const;
const builtInFormulaValues: Set<string> = new Set(builtInFormulaOptions.map((o) => o.value));

const CUSTOM_FORMULAS_KEY = "aervyx_custom_scoring_formulas";

type CustomFormula = { value: string; label: string; preset: FormulaPreset };

function loadCustomFormulas(): CustomFormula[] {
  try {
    const raw = localStorage.getItem(CUSTOM_FORMULAS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveCustomFormulas(formulas: CustomFormula[]) {
  localStorage.setItem(CUSTOM_FORMULAS_KEY, JSON.stringify(formulas));
}

/* ---------- Formula preset defaults per GAP version ---------- */

type FormulaPreset = Partial<EventFormState>;

const formulaPresetBase: FormulaPreset = {
  nominal_goal_percent: 0.2,
  nominal_distance_km: 60,
  nominal_time_hours: 1.5,
  nominal_launch: 0.95,
  minimum_distance_km: 5,
  score_back_time_minutes: 15,
  goal_ss_penalty: 1.0,
  stopped_glide_bonus: 0,
  jump_the_gun_factor: 0,
  jump_the_gun_max_seconds: 0,
  time_points_if_not_in_goal: 0,
  leading_weight_factor: 1.0,
  turnpoint_radius_tolerance: 0.005,
  turnpoint_radius_minimum_absolute_tolerance_m: 5,
  number_of_decimals_task_results: 1,
  number_of_decimals_competition_results: 0,
  scoring_altitude: "GPS",
  final_glide_decelerator: "none",
  use_distance_points: true,
  use_time_points: true,
  use_leading_points: false,
  use_arrival_position_points: false,
  use_arrival_time_points: false,
  use_departure_points: false,
  use_1000_points_for_max_day_quality: false,
  normalize_1000_before_day_quality: false,
  use_difficulty_for_distance_points: true,
  use_distance_squared_for_lc: false,
  use_semi_circle_control_zone_for_goal_line: false,
  use_proportional_leading_weight_if_nobody_in_goal: false,
  redistribute_removed_time_points_as_distance_points: false,
  use_best_score_for_ftv_validity: false,
  use_constant_leading_weight: false,
  use_pwca2019_for_lc: false,
  use_flat_decline_of_timepoints: false,
  day_quality_override: 0,
  min_time_span_for_valid_task_minutes: 0,
};

const formulaPresets: Record<string, FormulaPreset> = {
  GAP2021: {
    ...formulaPresetBase,
    use_flat_decline_of_timepoints: true,
    redistribute_removed_time_points_as_distance_points: true,
    use_distance_squared_for_lc: true,
    use_semi_circle_control_zone_for_goal_line: true,
    use_difficulty_for_distance_points: true,
    time_points_if_not_in_goal: 0.8,
    score_back_time_minutes: 15,
    stopped_glide_bonus: 5,
    jump_the_gun_factor: 2,
    jump_the_gun_max_seconds: 300,
    min_time_span_for_valid_task_minutes: 45,
  },
  GAP2020: {
    ...formulaPresetBase,
    use_flat_decline_of_timepoints: true,
    redistribute_removed_time_points_as_distance_points: true,
    use_distance_squared_for_lc: true,
    use_semi_circle_control_zone_for_goal_line: true,
    use_difficulty_for_distance_points: true,
    time_points_if_not_in_goal: 0.8,
    score_back_time_minutes: 15,
    stopped_glide_bonus: 5,
    jump_the_gun_factor: 2,
    jump_the_gun_max_seconds: 300,
    min_time_span_for_valid_task_minutes: 45,
  },
  GAP2018: {
    ...formulaPresetBase,
    use_difficulty_for_distance_points: true,
    use_distance_squared_for_lc: true,
    use_semi_circle_control_zone_for_goal_line: true,
    time_points_if_not_in_goal: 0,
    score_back_time_minutes: 15,
    stopped_glide_bonus: 4,
    jump_the_gun_factor: 2,
    jump_the_gun_max_seconds: 300,
    min_time_span_for_valid_task_minutes: 45,
  },
  GAP2016: {
    ...formulaPresetBase,
    use_difficulty_for_distance_points: true,
    use_arrival_position_points: true,
    time_points_if_not_in_goal: 0,
    score_back_time_minutes: 15,
    stopped_glide_bonus: 4,
    jump_the_gun_factor: 2,
    jump_the_gun_max_seconds: 300,
    min_time_span_for_valid_task_minutes: 45,
  },
  GAP2008: {
    ...formulaPresetBase,
    use_difficulty_for_distance_points: true,
    use_arrival_position_points: true,
    use_departure_points: true,
    time_points_if_not_in_goal: 0,
    score_back_time_minutes: 15,
    stopped_glide_bonus: 0,
  },
  OzGAP2005: {
    ...formulaPresetBase,
    use_difficulty_for_distance_points: true,
    use_arrival_time_points: true,
    use_departure_points: true,
    time_points_if_not_in_goal: 0,
    score_back_time_minutes: 15,
    stopped_glide_bonus: 0,
  },
  PWC2016: {
    ...formulaPresetBase,
    use_leading_points: true,
    use_distance_squared_for_lc: true,
    use_pwca2019_for_lc: false,
    use_difficulty_for_distance_points: true,
    time_points_if_not_in_goal: 0,
    score_back_time_minutes: 5,
    stopped_glide_bonus: 0,
  },
};

/* ---------- Formula description / info per version ---------- */

const formulaDescriptions: Record<string, { summary: string; details: string }> = {
  GAP2021: {
    summary: "Current FAI/CIVL standard (2021+)",
    details:
      "GAP 2021 is the current scoring formula defined by the FAI/CIVL Plenary. Key features compared to earlier versions: " +
      "time validity uses fastest pilot time (not 2nd fastest), flat decline of time points for a more gradual speed score taper, " +
      "removed time points are redistributed as distance points, distance-squared leading coefficient, " +
      "semi-circle goal line control zone, and time_points_if_not_in_goal defaults to 0.8 (pilots not in goal keep 80% of time points). " +
      "This is the recommended formula for CIVL-sanctioned competitions from 2021 onward.",
  },
  GAP2020: {
    summary: "Transitional version between GAP 2018 and 2021",
    details:
      "GAP 2020 introduced several features later adopted in GAP 2021: flat decline of time points, " +
      "redistribution of removed time points as distance points, and distance-squared leading coefficient. " +
      "It is functionally very similar to GAP 2021. Used during the 2020 season before the formal GAP 2021 adoption.",
  },
  GAP2018: {
    summary: "Removed arrival points, added distance-squared LC",
    details:
      "GAP 2018 removed arrival position points from the standard formula (arrival weight goes to speed). " +
      "It introduced the distance-squared leading coefficient and semi-circle goal line control zone. " +
      "Time validity still uses 2nd-fastest pilot time. Time points if not in goal is 0 (only goal pilots get time points). " +
      "Glide bonus is 4. Used for CIVL-sanctioned competitions 2018\u20132019.",
  },
  GAP2016: {
    summary: "Last version with arrival position points by default",
    details:
      "GAP 2016 includes arrival position points in the default weight allocation. " +
      "Uses difficulty-weighted distance points and the standard (non-squared) leading coefficient. " +
      "Time validity uses 2nd-fastest pilot time. Glide bonus is 4. " +
      "Used for CIVL-sanctioned competitions 2016\u20132017.",
  },
  GAP2008: {
    summary: "Classic GAP with arrival + departure points",
    details:
      "GAP 2008 is the classic formula with all four optional point categories active by default: " +
      "distance, time, arrival (position), and departure/start points. " +
      "Uses difficulty-weighted distance. No leading coefficient, no flat decline, no time points redistribution. " +
      "Widely used for hang gliding and paragliding competitions from 2008 through 2015.",
  },
  OzGAP2005: {
    summary: "Australian variant with timed arrival",
    details:
      "OzGAP 2005 is an Australian variant that uses arrival time points (instead of position) " +
      "and departure points. It follows the same core GAP validity and distance difficulty formulas. " +
      "Primarily used in Australian and Oceania competitions.",
  },
  PWC2016: {
    summary: "Paragliding World Cup formula",
    details:
      "PWC 2016 is the Paragliding World Cup scoring formula. It enables leading points with distance-squared LC, " +
      "but does not use arrival or departure points (their weight goes to speed). " +
      "Score-back time defaults to 5 minutes (vs 15 for standard GAP). No glide bonus. " +
      "Used by the PWCA circuit. When combined with use_pwca2019_for_lc, applies the 2019 leading coefficient method.",
  },
};
const scoringAltitudeOptions = [
  { value: "GPS", label: "GPS altitude" },
  { value: "QNH", label: "QNH altitude" },
  { value: "pressure", label: "Pressure altitude" },
] as const;
const finalGlideDeceleratorOptions = [
  { value: "none", label: "None" },
  { value: "default", label: "Default decelerator" },
  { value: "stopped_task", label: "Stopped-task decelerator" },
] as const;
const eventTabItems = [
  { id: "details", label: "Event Details" },
  { id: "turnpoints", label: "Turnpoint Files" },
  { id: "airspace", label: "Airspace / Restricted Fields" },
  { id: "participants", label: "Participants" },
  { id: "scoring", label: "Scoring Parameters" },
] satisfies Array<{ id: EventTab; label: string }>;
const airspaceCategoryOptions = [
  { value: "B", label: "Class B" },
  { value: "C", label: "Class C" },
  { value: "D", label: "Class D" },
  { value: "P", label: "Prohibited" },
  { value: "Q", label: "Danger" },
  { value: "R", label: "Restricted" },
  { value: "TFR", label: "TFR" },
  { value: "OTHER", label: "Other / advisory" },
] satisfies Array<{ value: AirspaceCategoryOption; label: string }>;

type PresetFeedback = { type: "success" | "error" | "pending"; text: string } | null;
type ScoringHelpCopy = { title: string; body: string };

const scoringFieldHelp = {
  scoring_formula: {
    title: "Scoring formula",
    body: "Chooses the GAP ruleset/version. Changing this will update the parameter checkboxes and numeric defaults below to match that version\u2019s standard settings. You can still override individual parameters after selecting a formula.",
  },
  nominal_goal_percent: {
    title: "Nominal goal",
    body: "The share of launched pilots expected to reach goal in a normal task. GAP uses it when computing validity and point allocation.",
  },
  score_back_time_minutes: {
    title: "Score-back time",
    body: "For a stopped task, flights are scored back from the stop time by this many minutes. CIVL guidance commonly uses 5 minutes for paragliding and 15 for hang gliding.",
  },
  goal_ss_penalty: {
    title: "Goal / SS penalty",
    body: "Stored as the speed-section penalty factor. It controls how much credit is kept when a ruleset applies a goal-versus-speed-section penalty.",
  },
  stopped_glide_bonus: {
    title: "Stopped-task glide bonus",
    body: "A stopped-task adjustment used when the chosen ruleset gives extra glide-related credit after a task stop.",
  },
  jump_the_gun_factor: {
    title: "Jump-the-gun factor",
    body: "The penalty rate for starting early. CIVL guidance describes jump-the-gun as a points-per-second early-start penalty.",
  },
  jump_the_gun_max_seconds: {
    title: "Jump-the-gun max",
    body: "The maximum early-start time scored or penalized under the jump-the-gun rule.",
  },
  use_distance_points: {
    title: "Distance points",
    body: "Turns the distance component on or off. When enabled, pilots earn points for the distance they fly along the task.",
  },
  use_time_points: {
    title: "Time points",
    body: "Turns the speed/time component on or off. When enabled, faster valid completions receive time points.",
  },
  use_leading_points: {
    title: "Leading points",
    body: "Enables the leading component. This rewards pilots for leading earlier on the course rather than only finishing fast.",
  },
  use_arrival_position_points: {
    title: "Arrival position points",
    body: "Enables arrival points based on finishing order at ESS or goal, depending on the scoring mode.",
  },
  use_arrival_time_points: {
    title: "Arrival time points",
    body: "Enables arrival points based on arrival time instead of only arrival order.",
  },
  use_departure_points: {
    title: "Departure points",
    body: "Enables the departure/start component. This is the GAP share sometimes called start or departure points.",
  },
  nominal_distance_km: {
    title: "Nominal distance",
    body: "The reference distance for a normal valid task. GAP compares actual task performance against this value when computing validity and weights.",
  },
  nominal_time_hours: {
    title: "Nominal time",
    body: "The reference winning time for a normal task. GAP compares the best task time against this value when computing time validity.",
  },
  nominal_launch: {
    title: "Nominal launch",
    body: "The expected share of registered pilots who launch in a normal task. GAP launch validity compares actual launches against this target.",
  },
  minimum_distance_km: {
    title: "Minimum distance",
    body: "The minimum scored distance floor. It defines the baseline before distance validity and distance-point scaling begin.",
  },
  penalties_text: {
    title: "Task penalty / notes JSON",
    body: "Repo-specific raw formula overrides or notes stored with the event. Use it for extra scoring-engine parameters that do not yet have dedicated fields.",
  },
  day_quality_override: {
    title: "Day quality override",
    body: "Forces a fixed day quality instead of using the value GAP would normally compute from task validity.",
  },
  time_points_if_not_in_goal: {
    title: "Time points if not in goal",
    body: "Controls whether and how time-related points are kept for pilots who do not make ESS or goal.",
  },
  min_time_span_for_valid_task_minutes: {
    title: "Min time span for valid task",
    body: "The minimum elapsed task span required before the task can be treated as valid under this scoring setup.",
  },
  leading_weight_factor: {
    title: "Leading weight factor",
    body: "Scales the size of the leading-points share relative to the other available point weights.",
  },
  turnpoint_radius_tolerance: {
    title: "Turnpoint radius tolerance",
    body: "Adds a small tolerance when cylinder crossings are checked so tiny GPS or geometry differences do not create false misses.",
  },
  turnpoint_radius_minimum_absolute_tolerance_m: {
    title: "Turnpoint minimum absolute tolerance",
    body: "A minimum meter-based floor for the turnpoint tolerance so very small cylinders still get a practical crossing tolerance.",
  },
  number_of_decimals_task_results: {
    title: "Task results decimals",
    body: "How many decimal places task-result scores are shown and rounded to.",
  },
  number_of_decimals_competition_results: {
    title: "Competition results decimals",
    body: "How many decimal places overall competition standings are shown and rounded to.",
  },
  scoring_altitude: {
    title: "Scoring altitude",
    body: "Chooses which altitude reference is used for altitude-sensitive scoring output and checks, such as GPS, QNH, or pressure altitude.",
  },
  final_glide_decelerator: {
    title: "Final glide decelerator",
    body: "Chooses the final-glide decelerator mode used near the end of the task when that rule is active.",
  },
  no_final_glide_decelerator_reason: {
    title: "No final glide decelerator reason",
    body: "A free-text note explaining why the final-glide decelerator is disabled or overridden for the event.",
  },
  use_1000_points_for_max_day_quality: {
    title: "Use 1000 points for max day quality",
    body: "Normalizes the maximum day to 1000 available points before other validity effects are applied.",
  },
  normalize_1000_before_day_quality: {
    title: "Normalize 1000 before day quality",
    body: "Forces the weight breakdown to normalize to 1000 points before day quality scales the task down.",
  },
  use_difficulty_for_distance_points: {
    title: "Use difficulty for distance points",
    body: "Uses GAP difficulty weighting for distance points instead of a simpler linear-only distance distribution.",
  },
  use_distance_squared_for_lc: {
    title: "Use distance squared for LC",
    body: "Uses squared distance inside the leading-coefficient calculation, increasing the influence of deeper course progress.",
  },
  use_semi_circle_control_zone_for_goal_line: {
    title: "Use semi-circle goal line control zone",
    body: "Treats the goal-line control zone as a semi-circle instead of the alternative control-zone interpretation.",
  },
  use_proportional_leading_weight_if_nobody_in_goal: {
    title: "Proportional leading weight if nobody in goal",
    body: "Scales leading weight proportionally when no pilot reaches goal, instead of keeping the full default leading share.",
  },
  redistribute_removed_time_points_as_distance_points: {
    title: "Redistribute removed time points",
    body: "Shifts the point share removed from time points into distance points so total available points stay balanced.",
  },
  use_best_score_for_ftv_validity: {
    title: "Use best score for FTV validity",
    body: "Uses a pilot's best-score set when applying Fixed Total Validity so competition scoring follows the FTV approach.",
  },
  use_constant_leading_weight: {
    title: "Use constant leading weight",
    body: "Keeps the leading-point weight fixed instead of letting it vary with the normal GAP weight allocation behavior.",
  },
  use_pwca2019_for_lc: {
    title: "Use PWCA 2019 for LC",
    body: "Applies the PWCA 2019 leading-coefficient method rather than the default leading setup.",
  },
  use_flat_decline_of_timepoints: {
    title: "Use flat decline of time points",
    body: "Uses a flatter decline curve when reducing time points, so they taper off more gently across the field.",
  },
} as const satisfies Record<string, ScoringHelpCopy>;

type ScoringHelpId = keyof typeof scoringFieldHelp;

function FieldHelp({
  helpId,
  activeHelpId,
  setActiveHelpId,
}: {
  helpId: ScoringHelpId;
  activeHelpId: ScoringHelpId | null;
  setActiveHelpId: (value: ScoringHelpId | null) => void;
}) {
  const copy = scoringFieldHelp[helpId];
  const isOpen = activeHelpId === helpId;
  const popoverId = `scoring-help-${helpId}`;

  return (
    <span className={`field-help${isOpen ? " is-open" : ""}`}>
      <button
        type="button"
        className="field-help-button"
        aria-label={`What does ${copy.title} mean?`}
        aria-expanded={isOpen}
        aria-controls={popoverId}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setActiveHelpId(isOpen ? null : helpId);
        }}
      >
        i
      </button>
      {isOpen ? (
        <span className="field-help-popover" id={popoverId} role="dialog" aria-label={copy.title}>
          <strong>{copy.title}</strong>
          <span>{copy.body}</span>
        </span>
      ) : null}
    </span>
  );
}

function LabelWithHelp({
  label,
  helpId,
  activeHelpId,
  setActiveHelpId,
}: {
  label: string;
  helpId: ScoringHelpId;
  activeHelpId: ScoringHelpId | null;
  setActiveHelpId: (value: ScoringHelpId | null) => void;
}) {
  return (
    <span className="field-label-with-help">
      <span>{label}</span>
      <FieldHelp helpId={helpId} activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
    </span>
  );
}

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") return configured || "/backend";
  return configured ?? "/backend";
}

async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${resolveApiBase()}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  if (!response.ok) {
    throw new Error((await response.text()) || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function blankPreset(id: string): ScoringPresetRecord {
  return { id, label: "", penalty_type: "percentage", value: 0, reason: "" };
}

function scoringFormFromEvent(sourceEvent: EventRecord, currentForm: EventFormState): EventFormState {
  return {
    ...currentForm,
    scoring_formula: sourceEvent.scoring_formula,
    nominal_distance_km: sourceEvent.nominal_distance_km,
    nominal_time_hours: sourceEvent.nominal_time_hours,
    nominal_launch: sourceEvent.nominal_launch,
    minimum_distance_km: sourceEvent.minimum_distance_km,
    nominal_goal_percent: sourceEvent.nominal_goal_percent,
    score_back_time_minutes: sourceEvent.score_back_time_minutes,
    goal_ss_penalty: sourceEvent.goal_ss_penalty,
    day_quality_override: sourceEvent.day_quality_override,
    time_points_if_not_in_goal: sourceEvent.time_points_if_not_in_goal,
    jump_the_gun_factor: sourceEvent.jump_the_gun_factor,
    jump_the_gun_max_seconds: sourceEvent.jump_the_gun_max_seconds,
    stopped_glide_bonus: sourceEvent.stopped_glide_bonus,
    use_1000_points_for_max_day_quality: sourceEvent.use_1000_points_for_max_day_quality,
    normalize_1000_before_day_quality: sourceEvent.normalize_1000_before_day_quality,
    use_distance_points: sourceEvent.use_distance_points,
    use_time_points: sourceEvent.use_time_points,
    use_leading_points: sourceEvent.use_leading_points,
    use_arrival_position_points: sourceEvent.use_arrival_position_points,
    use_arrival_time_points: sourceEvent.use_arrival_time_points,
    use_departure_points: sourceEvent.use_departure_points,
    use_difficulty_for_distance_points: sourceEvent.use_difficulty_for_distance_points,
    use_distance_squared_for_lc: sourceEvent.use_distance_squared_for_lc,
    use_semi_circle_control_zone_for_goal_line: sourceEvent.use_semi_circle_control_zone_for_goal_line,
    use_proportional_leading_weight_if_nobody_in_goal: sourceEvent.use_proportional_leading_weight_if_nobody_in_goal,
    redistribute_removed_time_points_as_distance_points: sourceEvent.redistribute_removed_time_points_as_distance_points,
    use_best_score_for_ftv_validity: sourceEvent.use_best_score_for_ftv_validity,
    use_constant_leading_weight: sourceEvent.use_constant_leading_weight,
    use_pwca2019_for_lc: sourceEvent.use_pwca2019_for_lc,
    use_flat_decline_of_timepoints: sourceEvent.use_flat_decline_of_timepoints,
    scoring_altitude: sourceEvent.scoring_altitude,
    final_glide_decelerator: sourceEvent.final_glide_decelerator,
    no_final_glide_decelerator_reason: sourceEvent.no_final_glide_decelerator_reason,
    min_time_span_for_valid_task_minutes: sourceEvent.min_time_span_for_valid_task_minutes,
    leading_weight_factor: sourceEvent.leading_weight_factor,
    turnpoint_radius_tolerance: sourceEvent.turnpoint_radius_tolerance,
    turnpoint_radius_minimum_absolute_tolerance_m: sourceEvent.turnpoint_radius_minimum_absolute_tolerance_m,
    number_of_decimals_task_results: sourceEvent.number_of_decimals_task_results,
    number_of_decimals_competition_results: sourceEvent.number_of_decimals_competition_results,
  };
}

function airspaceSourceLabel(kind: AirspaceSourceRecord["kind"]): string {
  return kind === "restricted_field" ? "Restricted fields" : kind === "airspace" ? "Airspace" : "";
}

function formatLongDate(value: string): string {
  if (!value) return "";
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const utcDate = new Date(Date.UTC(year, month - 1, day));
  return new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" }).format(utcDate);
}

function parseLongDate(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return "";
  const directMatch = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (directMatch) return trimmed;
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) return null;
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export interface EventsSectionProps {
  events: EventRecord[];
  selectedEventId: number | null;
  selectedEvent: EventRecord | null;
  eventEditorId: number | null;
  eventTab: EventTab;
  setEventTab: (tab: EventTab) => void;
  eventForm: EventFormState;
  setEventForm: (form: EventFormState) => void;
  turnpoints: TurnpointRecord[];
  turnpointSources: TurnpointSourceRecord[];
  airspaces: MapAirspaceRegion[];
  airspaceSources: AirspaceSourceRecord[];
  visibleAirspaces: MapAirspaceRegion[];
  pilots: PilotRecord[];
  canManagePlatform: boolean;
  isAdmin: boolean;
  selectEvent: (event: EventRecord) => void;
  createEventDraft: () => void;
  duplicateSelectedEvent: () => void;
    deleteEvent: () => void;
    saveEvent: (event: FormEvent<HTMLFormElement>) => void;
    saveEventForm: (nextForm: EventFormState, successMessage?: string) => Promise<void>;
    toggleTurnpointSource: (source: TurnpointSourceRecord, enabled: boolean) => void;
    deleteTurnpointSource: (source: TurnpointSourceRecord) => void;
    uploadAirspaceFile: (files: FileList | File[]) => Promise<void> | void;
    deleteAirspaceSource: (source: AirspaceSourceRecord) => void;
    toggleAirspaceSource: (source: AirspaceSourceRecord, updates: { enabled?: boolean; kind?: AirspaceSourceRecord["kind"] }) => void;
    uploadFile: (path: string, file: File) => Promise<unknown>;
  loadEvent: (activeToken: string, eventId: number) => Promise<void>;
  refreshPilotDirectory: (activeToken: string) => Promise<PilotRecord[]>;
  refreshEvents: (activeToken: string) => Promise<EventRecord[]>;
  token: string;
  setMessage: (msg: string) => void;
  setError: (msg: string) => void;
  renderParticipantCards: () => ReactNode;
}

export default function EventsSection(props: EventsSectionProps) {
  const {
    events,
    selectedEventId,
    selectedEvent,
    eventEditorId,
    eventTab,
    setEventTab,
    eventForm,
    setEventForm,
    turnpoints,
    turnpointSources,
    airspaceSources,
    visibleAirspaces,
    canManagePlatform,
    isAdmin,
    selectEvent,
    createEventDraft,
    duplicateSelectedEvent,
      deleteEvent,
      saveEvent,
      saveEventForm,
      toggleTurnpointSource,
      deleteTurnpointSource,
      uploadAirspaceFile,
      deleteAirspaceSource,
      toggleAirspaceSource,
      uploadFile,
    loadEvent,
    refreshPilotDirectory,
    refreshEvents,
    token,
    setMessage,
    setError,
    renderParticipantCards,
  } = props;
  const [scoringPresets, setScoringPresets] = useState<ScoringPresetRecord[]>([]);
  const [presetFeedback, setPresetFeedback] = useState<PresetFeedback>(null);
  const [activeHelpId, setActiveHelpId] = useState<ScoringHelpId | null>(null);
  const [formulaInfoOpen, setFormulaInfoOpen] = useState(false);
  const [customFormulas, setCustomFormulas] = useState<CustomFormula[]>(() => loadCustomFormulas());
  const [savingFormulaName, setSavingFormulaName] = useState("");
  const [showSaveFormula, setShowSaveFormula] = useState(false);
  const scoringFormulaOptions = [
    ...builtInFormulaOptions,
    ...customFormulas.map((cf) => ({ value: cf.value, label: cf.label })),
  ];
  const [scoringTemplateEventId, setScoringTemplateEventId] = useState("");
  const [scoringTemplateFeedback, setScoringTemplateFeedback] = useState<PresetFeedback>(null);
  const [startsOnDisplay, setStartsOnDisplay] = useState("");
  const [endsOnDisplay, setEndsOnDisplay] = useState("");
  const startsOnPickerRef = useRef<HTMLInputElement | null>(null);
  const endsOnPickerRef = useRef<HTMLInputElement | null>(null);
  const scoringTemplateOptions = events.filter((event) => event.id !== eventEditorId);
  const sortedEvents = [...events].sort((a, b) => {
    const da = a.starts_on ? new Date(a.starts_on).getTime() : -Infinity;
    const db = b.starts_on ? new Date(b.starts_on).getTime() : -Infinity;
    return db - da;
  });

  const autoSaveOverlaySettings = (nextForm: EventFormState) => {
    setEventForm(nextForm);
    void saveEventForm(nextForm, "Saved overlay settings.");
  };

  useEffect(() => {
    setStartsOnDisplay(formatLongDate(eventForm.starts_on));
    setEndsOnDisplay(formatLongDate(eventForm.ends_on));
  }, [eventForm.starts_on, eventForm.ends_on]);

  const commitScheduleDate = (field: "starts_on" | "ends_on", displayValue: string) => {
    const parsed = parseLongDate(displayValue);
    if (parsed == null) {
      setError(`Use a valid date like May 30, 2026 for ${field === "starts_on" ? "Starts on" : "Ends on"}.`);
      const fallback = field === "starts_on" ? formatLongDate(eventForm.starts_on) : formatLongDate(eventForm.ends_on);
      if (field === "starts_on") {
        setStartsOnDisplay(fallback);
      } else {
        setEndsOnDisplay(fallback);
      }
      return;
    }
    setError("");
    const nextForm = { ...eventForm, [field]: parsed };
    setEventForm(nextForm);
    if (field === "starts_on") {
      setStartsOnDisplay(formatLongDate(parsed));
    } else {
      setEndsOnDisplay(formatLongDate(parsed));
    }
  };

  const openSchedulePicker = (field: "starts_on" | "ends_on") => {
    const picker = field === "starts_on" ? startsOnPickerRef.current : endsOnPickerRef.current;
    if (!picker) return;
    const inputWithPicker = picker as HTMLInputElement & { showPicker?: () => void };
    if (typeof inputWithPicker.showPicker === "function") {
      inputWithPicker.showPicker();
      return;
    }
    picker.click();
  };

  useEffect(() => {
    let cancelled = false;

    async function loadScoringPresets() {
      if (!token || !selectedEventId || eventTab !== "scoring") {
        if (!cancelled && !selectedEventId) setScoringPresets([]);
        return;
      }
      try {
        const presets = await apiFetch<ScoringPresetRecord[]>(`/api/events/${selectedEventId}/scoring-presets`, token);
        if (!cancelled) setScoringPresets(presets);
      } catch (caught) {
        if (!cancelled) {
          setPresetFeedback({
            type: "error",
            text: caught instanceof Error ? caught.message : "Could not load penalty presets.",
          });
        }
      }
    }

    void loadScoringPresets();
    return () => {
      cancelled = true;
    };
  }, [eventTab, selectedEventId, token]);

  useEffect(() => {
    setScoringTemplateEventId("");
    setScoringTemplateFeedback(null);
    setActiveHelpId(null);
  }, [eventEditorId]);

  async function saveScoringPresets() {
    if (!token || !selectedEventId) return;
    try {
      setPresetFeedback({ type: "pending", text: "Saving penalty presets..." });
      const saved = await apiFetch<ScoringPresetRecord[]>(`/api/events/${selectedEventId}/scoring-presets`, token, {
        method: "PATCH",
        body: JSON.stringify({
          presets: scoringPresets
            .filter((preset) => preset.label.trim())
            .map((preset) => ({
              ...preset,
              reason: preset.reason.trim() || preset.label.trim(),
            })),
        }),
      });
      setScoringPresets(saved);
      setPresetFeedback({ type: "success", text: "Saved penalty presets." });
    } catch (caught) {
      setPresetFeedback({
        type: "error",
        text: caught instanceof Error ? caught.message : "Could not save penalty presets.",
      });
    }
  }

  async function loadScoringTemplate() {
    if (!token || !eventEditorId || !scoringTemplateEventId) return;
    const sourceEventId = Number(scoringTemplateEventId);
    const sourceEvent = events.find((event) => event.id === sourceEventId);
    if (!sourceEvent) {
      setScoringTemplateFeedback({ type: "error", text: "Choose a saved meet before loading scoring parameters." });
      return;
    }
    try {
      setScoringTemplateFeedback({ type: "pending", text: `Loading scoring parameters from ${sourceEvent.name}...` });
      const loadedPresets = await apiFetch<ScoringPresetRecord[]>(`/api/events/${sourceEventId}/scoring-presets`, token);
      setEventForm(scoringFormFromEvent(sourceEvent, eventForm));
      setScoringPresets(loadedPresets);
      setPresetFeedback({
        type: "success",
        text: loadedPresets.length
          ? `Loaded ${loadedPresets.length} penalty preset${loadedPresets.length === 1 ? "" : "s"} from ${sourceEvent.name}.`
          : `Loaded scoring parameters from ${sourceEvent.name}. No penalty presets were saved on that meet.`,
      });
      setScoringTemplateFeedback({
        type: "success",
        text: `Copied scoring parameters from ${sourceEvent.name}. Review them, then save this event and its penalty presets.`,
      });
    } catch (caught) {
      setScoringTemplateFeedback({
        type: "error",
        text: caught instanceof Error ? caught.message : `Could not load scoring parameters from ${sourceEvent.name}.`,
      });
    }
  }

  return (
    <div className="section-stack">
      <SectionCard title="Event selection">
        <div className="event-selector-bar">
          <label className="stack compact event-selector-field">
            <span>Current event</span>
            <select value={selectedEventId ?? (events[0]?.id ?? "")} onChange={(event) => { const nextId = Number(event.target.value); const nextEvent = events.find((candidate) => candidate.id === nextId); if (nextEvent) void selectEvent(nextEvent); }}>
              {events.length === 0 ? <option value="">No events yet</option> : null}
              {sortedEvents.map((event) => (
                <option key={event.id} value={event.id}>
                  {event.location ? `${event.name} - ${event.location}` : event.name}
                </option>
              ))}
            </select>
            </label>
            {canManagePlatform ? (
              <div className="event-selector-actions">
                <button className="ghost-button" type="button" onClick={() => void createEventDraft()}>Create a New Event</button>
                <button className="primary-button" type="button" onClick={() => void saveEventForm(eventForm, `${eventEditorId ? "Updated" : "Created"} event ${eventForm.name || "draft"}.`)}>{eventEditorId ? "Save event" : "Create event"}</button>
                {eventEditorId ? <button type="button" className="ghost-button" onClick={() => void duplicateSelectedEvent()}>Duplicate event</button> : null}
                {isAdmin && eventEditorId ? <button type="button" className="ghost-button danger-button" onClick={() => void deleteEvent()}>Delete event</button> : null}
              </div>
            ) : null}
          </div>
        </SectionCard>
      <div className="tab-row">
        {eventTabItems.map((tab) => (
          <button key={tab.id} type="button" className={eventTab === tab.id ? "tab-button active" : "tab-button"} onClick={() => setEventTab(tab.id)}>
            {tab.label}
          </button>
        ))}
      </div>
      <div className="event-workspace-grid event-workspace-stack">
        {eventTab === "details" ? (
        <SectionCard>
          <form className="stack form-block compact-event-form compact-clusters" onSubmit={saveEvent}>
            <div className="fieldset-grid two-up">
              <fieldset className="fieldset-cluster">
                <legend>Basics</legend>
                <div className="cluster-stack">
                  <label className="stack compact">
                    <span>Event name</span>
                    <input placeholder="Enter event name" value={eventForm.name} onChange={(event) => setEventForm({ ...eventForm, name: event.target.value })} />
                  </label>
                  <label className="stack compact">
                    <span>Location</span>
                    <input placeholder="Enter location" value={eventForm.location} onChange={(event) => setEventForm({ ...eventForm, location: event.target.value })} />
                  </label>
                  <label className="task-advanced-toggle">
                    <input type="checkbox" checked={eventForm.is_public_tracking ?? false} onChange={(event) => setEventForm({ ...eventForm, is_public_tracking: event.target.checked })} />
                    <span>Public live tracking</span>
                  </label>
                  <label className="stack compact">
                    <span>Publicly viewable</span>
                    <select value={eventForm.visibility} onChange={(event) => setEventForm({ ...eventForm, visibility: event.target.value as "public" | "users" | "participants" | "private" })}>
                      <option value="public">Public</option>
                      <option value="users">Viewable by all Aervyx users</option>
                      <option value="participants">Viewable by Event Participants</option>
                      <option value="private">Not viewable</option>
                    </select>
                  </label>
                </div>
              </fieldset>
              <fieldset className="fieldset-cluster">
                <legend>Schedule</legend>
                  <div className="cluster-stack">
                    <label className="stack compact event-schedule-row">
                      <span>Starts on</span>
                      <span className="event-date-field">
                        <input
                          type="text"
                          className="event-date-input"
                          placeholder="May 30, 2026"
                          value={startsOnDisplay}
                          onChange={(event) => setStartsOnDisplay(event.target.value)}
                          onBlur={(event) => commitScheduleDate("starts_on", event.target.value)}
                        />
                        <button type="button" className="event-date-picker-button" aria-label="Open start date picker" onClick={() => openSchedulePicker("starts_on")}>
                          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                            <path d="M7 2h2v3H7V2Zm8 0h2v3h-2V2ZM4 6h16a2 2 0 0 1 2 2v11a3 3 0 0 1-3 3H5a3 3 0 0 1-3-3V8a2 2 0 0 1 2-2Zm0 5v8a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-8H4Zm14-3H6v1h12V8Z" />
                          </svg>
                        </button>
                        <input
                          ref={startsOnPickerRef}
                          type="date"
                          className="event-date-native-input"
                          tabIndex={-1}
                          aria-hidden="true"
                          value={eventForm.starts_on}
                          onChange={(event) => commitScheduleDate("starts_on", event.target.value)}
                        />
                      </span>
                    </label>
                    <label className="stack compact event-schedule-row">
                      <span>Ends on</span>
                      <span className="event-date-field">
                        <input
                          type="text"
                          className="event-date-input"
                          placeholder="June 7, 2026"
                          value={endsOnDisplay}
                          onChange={(event) => setEndsOnDisplay(event.target.value)}
                          onBlur={(event) => commitScheduleDate("ends_on", event.target.value)}
                        />
                        <button type="button" className="event-date-picker-button" aria-label="Open end date picker" onClick={() => openSchedulePicker("ends_on")}>
                          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                            <path d="M7 2h2v3H7V2Zm8 0h2v3h-2V2ZM4 6h16a2 2 0 0 1 2 2v11a3 3 0 0 1-3 3H5a3 3 0 0 1-3-3V8a2 2 0 0 1 2-2Zm0 5v8a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-8H4Zm14-3H6v1h12V8Z" />
                          </svg>
                        </button>
                        <input
                          ref={endsOnPickerRef}
                          type="date"
                          className="event-date-native-input"
                          tabIndex={-1}
                          aria-hidden="true"
                          value={eventForm.ends_on}
                          onChange={(event) => commitScheduleDate("ends_on", event.target.value)}
                        />
                      </span>
                    </label>
                    <label className="stack compact">
                      <span>Timezone</span>
                      <input placeholder="Enter timezone" value={eventForm.timezone} onChange={(event) => setEventForm({ ...eventForm, timezone: event.target.value })} />
                    </label>
                    <div className="inline-grid">
                      <label className="stack compact">
                        <span>Default start gates</span>
                        <input type="number" min={1} value={eventForm.default_start_gate_count} onChange={(event) => setEventForm({ ...eventForm, default_start_gate_count: Math.max(1, Number(event.target.value) || 1) })} />
                      </label>
                      <label className="stack compact">
                        <span>Default gate interval (min)</span>
                        <input type="number" min={0} value={eventForm.default_start_gate_interval_seconds / 60} onChange={(event) => setEventForm({ ...eventForm, default_start_gate_interval_seconds: Math.max(0, Number(event.target.value) || 0) * 60 })} />
                      </label>
                    </div>
                  </div>
                </fieldset>
            </div>
            </form>
          </SectionCard>
        ) : null}
        {eventTab === "scoring" ? (
        <>
        <SectionCard title="Scoring parameters">
          {eventEditorId ? (
            <form className="stack form-block compact-scoring-form compact-clusters" onSubmit={saveEvent}>
              <div className="scoring-import-strip">
                <div className="scoring-import-copy">
                  <strong>Load scoring parameters</strong>
                  <span>Claude-guided placement: import scoring fields and penalty presets from a saved meet without leaving the current event.</span>
                </div>
                <div className="scoring-import-controls">
                  <label className="stack compact scoring-import-field">
                    <span>Saved meet</span>
                    <select value={scoringTemplateEventId} onChange={(event) => setScoringTemplateEventId(event.target.value)}>
                      <option value="">Choose saved scoring parameters</option>
                      {scoringTemplateOptions.map((event) => (
                        <option key={event.id} value={event.id}>
                          {event.location ? `${event.name} - ${event.location}` : event.name} - scoring parameters
                        </option>
                      ))}
                    </select>
                  </label>
                  <button type="button" className="ghost-button scoring-import-button" onClick={() => void loadScoringTemplate()} disabled={!scoringTemplateEventId}>
                    Load scoring parameters
                  </button>
                </div>
              </div>
              {scoringTemplateFeedback ? <div className={`status-chip ${scoringTemplateFeedback.type} scoring-import-feedback`}>{scoringTemplateFeedback.text}</div> : null}
              <div className="fieldset-grid events-scoring-grid">
              <fieldset className="fieldset-cluster scoring-help-open-right">
                <legend>Formula and points</legend>
                <div className="cluster-stack">
              <label className="stack compact">
                <LabelWithHelp label="Scoring formula" helpId="scoring_formula" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                <select value={eventForm.scoring_formula} onChange={(event) => {
                  const newFormula = event.target.value;
                  const preset = formulaPresets[newFormula] ?? customFormulas.find((cf) => cf.value === newFormula)?.preset;
                  setFormulaInfoOpen(false);
                  if (preset) {
                    setEventForm({ ...eventForm, ...preset, scoring_formula: newFormula });
                  } else {
                    setEventForm({ ...eventForm, scoring_formula: newFormula });
                  }
                }}>
                  {scoringFormulaOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              {formulaDescriptions[eventForm.scoring_formula] ? (
                <div className="formula-info-block">
                  <button type="button" className="formula-info-toggle" onClick={() => setFormulaInfoOpen(!formulaInfoOpen)}>
                    {formulaInfoOpen ? "Hide" : "About"} {scoringFormulaOptions.find((o) => o.value === eventForm.scoring_formula)?.label ?? eventForm.scoring_formula}
                  </button>
                  {formulaInfoOpen ? (
                    <div className="formula-info-panel">
                      <strong>{formulaDescriptions[eventForm.scoring_formula].summary}</strong>
                      <p>{formulaDescriptions[eventForm.scoring_formula].details}</p>
                    </div>
                  ) : null}
                </div>
              ) : null}
              <div className="custom-formula-actions">
                {!builtInFormulaValues.has(eventForm.scoring_formula) && customFormulas.some((cf) => cf.value === eventForm.scoring_formula) ? (
                  <button type="button" className="formula-info-toggle danger-text" onClick={() => {
                    const next = customFormulas.filter((cf) => cf.value !== eventForm.scoring_formula);
                    setCustomFormulas(next);
                    saveCustomFormulas(next);
                    setEventForm({ ...eventForm, scoring_formula: "GAP2021", ...formulaPresets.GAP2021 });
                  }}>Delete custom formula</button>
                ) : null}
                {showSaveFormula ? (
                  <span className="custom-formula-save-row">
                    <input type="text" placeholder="Custom formula name" value={savingFormulaName} onChange={(e) => setSavingFormulaName(e.target.value)} className="custom-formula-name-input" />
                    <button type="button" className="formula-info-toggle" onClick={() => {
                      const name = savingFormulaName.trim();
                      if (!name) return;
                      const key = `custom_${name.replace(/\s+/g, "_").toLowerCase()}_${Date.now()}`;
                      const preset: FormulaPreset = {};
                      for (const field of Object.keys(formulaPresetBase) as Array<keyof typeof formulaPresetBase>) {
                        (preset as Record<string, unknown>)[field] = eventForm[field];
                      }
                      const entry: CustomFormula = { value: key, label: name, preset };
                      const next = [...customFormulas, entry];
                      setCustomFormulas(next);
                      saveCustomFormulas(next);
                      setEventForm({ ...eventForm, scoring_formula: key });
                      setSavingFormulaName("");
                      setShowSaveFormula(false);
                    }}>Save</button>
                    <button type="button" className="formula-info-toggle" onClick={() => { setShowSaveFormula(false); setSavingFormulaName(""); }}>Cancel</button>
                  </span>
                ) : (
                  <button type="button" className="formula-info-toggle" onClick={() => setShowSaveFormula(true)}>Save current as custom formula</button>
                )}
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <LabelWithHelp label="Nominal goal (%)" helpId="nominal_goal_percent" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                  <input type="number" step="0.01" value={eventForm.nominal_goal_percent} onChange={(event) => setEventForm({ ...eventForm, nominal_goal_percent: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <LabelWithHelp label="Score-back time (minutes)" helpId="score_back_time_minutes" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                  <input type="number" value={eventForm.score_back_time_minutes} onChange={(event) => setEventForm({ ...eventForm, score_back_time_minutes: Number(event.target.value) })} />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <LabelWithHelp label="Goal / SS penalty" helpId="goal_ss_penalty" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                  <input type="number" step="0.1" value={eventForm.goal_ss_penalty} onChange={(event) => setEventForm({ ...eventForm, goal_ss_penalty: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <LabelWithHelp label="Stopped-task glide bonus" helpId="stopped_glide_bonus" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                  <input type="number" step="0.1" value={eventForm.stopped_glide_bonus} onChange={(event) => setEventForm({ ...eventForm, stopped_glide_bonus: Number(event.target.value) })} />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <LabelWithHelp label="Jump-the-gun factor" helpId="jump_the_gun_factor" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                  <input type="number" step="0.1" value={eventForm.jump_the_gun_factor} onChange={(event) => setEventForm({ ...eventForm, jump_the_gun_factor: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <LabelWithHelp label="Jump-the-gun max (seconds)" helpId="jump_the_gun_max_seconds" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                  <input type="number" value={eventForm.jump_the_gun_max_seconds} onChange={(event) => setEventForm({ ...eventForm, jump_the_gun_max_seconds: Number(event.target.value) })} />
                </label>
              </div>
                    <div className="scoring-checkbox-table" role="table" aria-label="Formula scoring checkboxes">
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Distance points" helpId="use_distance_points" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_distance_points} onChange={(event) => setEventForm({ ...eventForm, use_distance_points: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Time points" helpId="use_time_points" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_time_points} onChange={(event) => setEventForm({ ...eventForm, use_time_points: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Leading points" helpId="use_leading_points" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_leading_points} onChange={(event) => setEventForm({ ...eventForm, use_leading_points: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Arrival position points" helpId="use_arrival_position_points" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_arrival_position_points} onChange={(event) => setEventForm({ ...eventForm, use_arrival_position_points: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Arrival time points" helpId="use_arrival_time_points" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_arrival_time_points} onChange={(event) => setEventForm({ ...eventForm, use_arrival_time_points: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Departure points" helpId="use_departure_points" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_departure_points} onChange={(event) => setEventForm({ ...eventForm, use_departure_points: event.target.checked })} /></span>
                      </label>
                    </div>
                  </div>
                </fieldset>
              <fieldset className="fieldset-cluster">
                <legend>Nominal values and notes</legend>
                <div className="cluster-stack">
                  <div className="inline-grid">
                    <label className="stack compact">
                      <LabelWithHelp label="Nominal distance (km)" helpId="nominal_distance_km" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <input type="number" value={eventForm.nominal_distance_km} onChange={(event) => setEventForm({ ...eventForm, nominal_distance_km: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <LabelWithHelp label="Nominal time (hours)" helpId="nominal_time_hours" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <input type="number" step="0.1" value={eventForm.nominal_time_hours} onChange={(event) => setEventForm({ ...eventForm, nominal_time_hours: Number(event.target.value) })} />
                    </label>
                  </div>
                  <div className="inline-grid">
                    <label className="stack compact">
                      <LabelWithHelp label="Nominal launch" helpId="nominal_launch" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <input type="number" step="0.01" value={eventForm.nominal_launch} onChange={(event) => setEventForm({ ...eventForm, nominal_launch: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <LabelWithHelp label="Minimum distance (km)" helpId="minimum_distance_km" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <input type="number" value={eventForm.minimum_distance_km} onChange={(event) => setEventForm({ ...eventForm, minimum_distance_km: Number(event.target.value) })} />
                    </label>
                  </div>
                </div>
              </fieldset>
              <fieldset className="fieldset-cluster">
                <legend>Advanced scoring</legend>
                <div className="cluster-stack">
                  <div className="inline-grid">
                    <label className="stack compact">
                      <LabelWithHelp label="Day quality override" helpId="day_quality_override" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <input type="number" step="0.01" value={eventForm.day_quality_override} onChange={(event) => setEventForm({ ...eventForm, day_quality_override: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <LabelWithHelp label="Time points if not in goal" helpId="time_points_if_not_in_goal" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <input type="number" step="0.01" value={eventForm.time_points_if_not_in_goal} onChange={(event) => setEventForm({ ...eventForm, time_points_if_not_in_goal: Number(event.target.value) })} />
                    </label>
                  </div>
                  <div className="inline-grid">
                    <label className="stack compact">
                      <LabelWithHelp label="Min time span for valid task (minutes)" helpId="min_time_span_for_valid_task_minutes" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <input type="number" value={eventForm.min_time_span_for_valid_task_minutes} onChange={(event) => setEventForm({ ...eventForm, min_time_span_for_valid_task_minutes: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <LabelWithHelp label="Leading weight factor" helpId="leading_weight_factor" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <input type="number" step="0.01" value={eventForm.leading_weight_factor} onChange={(event) => setEventForm({ ...eventForm, leading_weight_factor: Number(event.target.value) })} />
                    </label>
                  </div>
                  <div className="inline-grid">
                    <label className="stack compact">
                      <LabelWithHelp label="Turnpoint radius tolerance" helpId="turnpoint_radius_tolerance" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <input type="number" step="0.0001" value={eventForm.turnpoint_radius_tolerance} onChange={(event) => setEventForm({ ...eventForm, turnpoint_radius_tolerance: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <LabelWithHelp label="Turnpoint min absolute tolerance (m)" helpId="turnpoint_radius_minimum_absolute_tolerance_m" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <input type="number" step="0.1" value={eventForm.turnpoint_radius_minimum_absolute_tolerance_m} onChange={(event) => setEventForm({ ...eventForm, turnpoint_radius_minimum_absolute_tolerance_m: Number(event.target.value) })} />
                    </label>
                  </div>
                  <div className="inline-grid">
                    <label className="stack compact">
                      <LabelWithHelp label="Task results decimals" helpId="number_of_decimals_task_results" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <input type="number" min={0} max={6} value={eventForm.number_of_decimals_task_results} onChange={(event) => setEventForm({ ...eventForm, number_of_decimals_task_results: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <LabelWithHelp label="Competition results decimals" helpId="number_of_decimals_competition_results" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <input type="number" min={0} max={6} value={eventForm.number_of_decimals_competition_results} onChange={(event) => setEventForm({ ...eventForm, number_of_decimals_competition_results: Number(event.target.value) })} />
                    </label>
                  </div>
                  <div className="inline-grid">
                    <label className="stack compact">
                      <LabelWithHelp label="Scoring altitude" helpId="scoring_altitude" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <select value={eventForm.scoring_altitude} onChange={(event) => setEventForm({ ...eventForm, scoring_altitude: event.target.value })}>
                        {scoringAltitudeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                      </select>
                    </label>
                    <label className="stack compact">
                      <LabelWithHelp label="Final glide decelerator" helpId="final_glide_decelerator" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                      <select value={eventForm.final_glide_decelerator} onChange={(event) => setEventForm({ ...eventForm, final_glide_decelerator: event.target.value })}>
                        {finalGlideDeceleratorOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                      </select>
                    </label>
                  </div>
                  <label className="stack compact">
                    <LabelWithHelp label="No final glide decelerator reason" helpId="no_final_glide_decelerator_reason" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                    <input type="text" value={eventForm.no_final_glide_decelerator_reason} onChange={(event) => setEventForm({ ...eventForm, no_final_glide_decelerator_reason: event.target.value })} placeholder="Optional override note" />
                  </label>
                    <div className="scoring-checkbox-table" role="table" aria-label="Advanced scoring checkboxes">
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Use 1000 points for max day quality" helpId="use_1000_points_for_max_day_quality" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_1000_points_for_max_day_quality} onChange={(event) => setEventForm({ ...eventForm, use_1000_points_for_max_day_quality: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Normalize 1000 before day quality" helpId="normalize_1000_before_day_quality" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.normalize_1000_before_day_quality} onChange={(event) => setEventForm({ ...eventForm, normalize_1000_before_day_quality: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Use difficulty for distance points" helpId="use_difficulty_for_distance_points" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_difficulty_for_distance_points} onChange={(event) => setEventForm({ ...eventForm, use_difficulty_for_distance_points: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Use distance squared for LC" helpId="use_distance_squared_for_lc" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_distance_squared_for_lc} onChange={(event) => setEventForm({ ...eventForm, use_distance_squared_for_lc: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Use semi-circle goal line control zone" helpId="use_semi_circle_control_zone_for_goal_line" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_semi_circle_control_zone_for_goal_line} onChange={(event) => setEventForm({ ...eventForm, use_semi_circle_control_zone_for_goal_line: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Use proportional leading weight if nobody in goal" helpId="use_proportional_leading_weight_if_nobody_in_goal" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_proportional_leading_weight_if_nobody_in_goal} onChange={(event) => setEventForm({ ...eventForm, use_proportional_leading_weight_if_nobody_in_goal: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Redistribute removed time points as distance points" helpId="redistribute_removed_time_points_as_distance_points" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.redistribute_removed_time_points_as_distance_points} onChange={(event) => setEventForm({ ...eventForm, redistribute_removed_time_points_as_distance_points: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Use best score for FTV validity" helpId="use_best_score_for_ftv_validity" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_best_score_for_ftv_validity} onChange={(event) => setEventForm({ ...eventForm, use_best_score_for_ftv_validity: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Use constant leading weight" helpId="use_constant_leading_weight" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_constant_leading_weight} onChange={(event) => setEventForm({ ...eventForm, use_constant_leading_weight: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Use PWCA 2019 for LC" helpId="use_pwca2019_for_lc" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_pwca2019_for_lc} onChange={(event) => setEventForm({ ...eventForm, use_pwca2019_for_lc: event.target.checked })} /></span>
                      </label>
                      <label className="scoring-checkbox-row" role="row">
                        <LabelWithHelp label="Use flat decline of time points" helpId="use_flat_decline_of_timepoints" activeHelpId={activeHelpId} setActiveHelpId={setActiveHelpId} />
                        <span className="scoring-checkbox-control" role="cell"><input type="checkbox" checked={eventForm.use_flat_decline_of_timepoints} onChange={(event) => setEventForm({ ...eventForm, use_flat_decline_of_timepoints: event.target.checked })} /></span>
                      </label>
                    </div>
                </div>
              </fieldset>
              </div>
              {canManagePlatform ? <button type="submit">Save scoring parameters</button> : null}
            </form>
          ) : (
            <p className="hint">Create or select an event to define its scoring defaults.</p>
          )}
        </SectionCard>
        <SectionCard title="Penalty presets">
          {eventEditorId ? (
            <div className="stack form-block">
              {presetFeedback ? <div className={`status-chip ${presetFeedback.type}`}>{presetFeedback.text}</div> : null}
              <div className="scoring-ops-preset-list">
                {scoringPresets.length ? (
                  <>
                    <div className="scoring-ops-preset-table-head">
                      <span>Name</span>
                      <span>Type</span>
                      <span>Amount</span>
                      <span />
                    </div>
                    {scoringPresets.map((preset, index) => (
                      <div key={preset.id} className="scoring-ops-preset-row simple">
                        <input
                          value={preset.label}
                          onChange={(event) =>
                            setScoringPresets((current) =>
                              current.map((item, itemIndex) => (itemIndex === index ? { ...item, label: event.target.value } : item)),
                            )
                          }
                          placeholder="Preset name"
                        />
                        <select
                          value={preset.penalty_type}
                          onChange={(event) =>
                            setScoringPresets((current) =>
                              current.map((item, itemIndex) =>
                                itemIndex === index ? { ...item, penalty_type: event.target.value as "percentage" | "fixed" } : item,
                              ),
                            )
                          }
                        >
                          <option value="percentage">% penalty</option>
                          <option value="fixed">Fixed pts</option>
                        </select>
                        <input
                          type="number"
                          value={preset.value}
                          onChange={(event) =>
                            setScoringPresets((current) =>
                              current.map((item, itemIndex) =>
                                itemIndex === index ? { ...item, value: Number(event.target.value || 0), reason: item.label } : item,
                              ),
                            )
                          }
                        />
                        <button
                          type="button"
                          className="ghost-button danger-button"
                          onClick={() => setScoringPresets((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                  </>
                ) : (
                  <p className="hint">No presets configured yet for this event.</p>
                )}
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => setScoringPresets((current) => [...current, blankPreset(`preset-${Date.now()}-${current.length}`)])}
                >
                  Add preset
                </button>
                <button type="button" className="primary-button" onClick={() => void saveScoringPresets()}>
                  Save penalty presets
                </button>
              </div>
            </div>
          ) : (
            <p className="hint">Create or select an event to manage penalty presets.</p>
          )}
        </SectionCard>
        </>
        ) : null}
        {eventTab === "turnpoints" ? (
        <SectionCard title="Turnpoint files">
          {eventEditorId ? (
            <div className="stack form-block">
              {canManagePlatform ? (
                <div className="participant-intake-row">
                  <div className="stack compact">
                    <span>Upload turnpoint file</span>
                    <p className="hint">CSV, GeoJSON, or GPX. Each upload is stored separately so you can mix multiple waypoint datasets on the same event.</p>
                  </div>
                  <label className="file-input">
                    Upload turnpoints
                    <input
                      type="file"
                      accept=".csv,.geojson,.json,.gpx"
                      onChange={async (event) => {
                        const file = event.target.files?.[0];
                        if (!file || !selectedEventId) return;
                        try {
                          setError("");
                          const response = await uploadFile(`/api/events/${selectedEventId}/turnpoints/upload`, file) as TurnpointUploadResponse;
                          setMessage(`Stored ${response.imported_count} turnpoints from ${file.name}.`);
                          await loadEvent(token, selectedEventId);
                          await refreshEvents(token);
                        } catch (caught) {
                          setError(caught instanceof Error ? caught.message : `Failed to import ${file.name}.`);
                        } finally {
                          event.currentTarget.value = "";
                        }
                      }}
                    />
                  </label>
                </div>
              ) : null}
              <div className="participant-table-wrap">
                <table className="participant-table">
                  <thead>
                    <tr>
                      <th>File name</th>
                      <th>Format</th>
                      <th>Turnpoints</th>
                      <th>Visible</th>
                      <th>Uploaded</th>
                      {canManagePlatform ? <th className="participant-table-actions">Actions</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {turnpointSources.length ? (
                      turnpointSources.map((source) => (
                        <tr key={source.id}>
                          <td><strong>{source.filename}</strong></td>
                          <td>{source.file_format.toUpperCase()}</td>
                          <td>{source.turnpoint_count}</td>
                          <td>
                            <label className="task-advanced-toggle">
                              <input
                                type="checkbox"
                                checked={source.enabled}
                                disabled={!canManagePlatform}
                                onChange={(event) => void toggleTurnpointSource(source, event.target.checked)}
                              />
                              <span>{source.enabled ? "Visible" : "Hidden"}</span>
                            </label>
                          </td>
                          <td>{new Date(source.uploaded_at).toLocaleString()}</td>
                          {canManagePlatform ? (
                            <td className="participant-table-actions">
                              <button type="button" className="ghost-button danger-button" onClick={() => void deleteTurnpointSource(source)}>Delete</button>
                            </td>
                          ) : null}
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={canManagePlatform ? 6 : 5} className="participant-table-empty">No turnpoint files uploaded for this event yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="hint">Create or select an event before uploading turnpoint files.</p>
          )}
        </SectionCard>
        ) : null}
      {eventTab === "airspace" ? (
        <>
          <SectionCard title="Overlay settings">
            {eventEditorId ? (
              <div className="stack form-block">
                <div className="event-airspace-settings-row">
                  <div className="event-airspace-class-row">
                    {airspaceCategoryOptions.map((option) => (
                      <label key={option.value} className="task-advanced-toggle">
                        <input
                          type="checkbox"
                          checked={eventForm.visible_airspace_classes_json.includes(option.value)}
                          onChange={() => {
                            const existing = new Set(eventForm.visible_airspace_classes_json);
                            if (existing.has(option.value)) {
                              existing.delete(option.value);
                            } else {
                              existing.add(option.value);
                            }
                            autoSaveOverlaySettings({ ...eventForm, visible_airspace_classes_json: Array.from(existing) });
                          }}
                        />
                        <span>{option.label}</span>
                      </label>
                    ))}
                    <label className="task-advanced-toggle">
                      <input
                        type="checkbox"
                        checked={eventForm.show_restricted_fields}
                        onChange={(event) => autoSaveOverlaySettings({ ...eventForm, show_restricted_fields: event.target.checked })}
                      />
                      <span>Restricted fields</span>
                    </label>
                  </div>
                  <div className="record-card event-airspace-summary-card">
                    <strong>{visibleAirspaces.length} visible overlays</strong>
                    <span>{selectedEvent?.airspace_count ?? 0} airspace regions and {selectedEvent?.restricted_field_count ?? 0} restricted fields stored for this event.</span>
                  </div>
                </div>
              </div>
            ) : (
              <p className="hint">Create or select an event to configure airspace overlays.</p>
            )}
          </SectionCard>
          <SectionCard title="Overlay files">
            <div className="stack form-block">
              {eventEditorId ? (
                canManagePlatform ? (
                  <div className="event-airspace-upload-row">
                    <div className="stack compact">
                      <span>Upload overlay file</span>
                      <p className="hint">Upload OpenAir or GeoJSON. Hold Ctrl or Shift in the picker to choose multiple files. Files start unlabeled, and you can assign `Airspace` or `Restricted fields` later in the table.</p>
                    </div>
                    <label className="file-input">
                      Upload overlays
                      <input
                        type="file"
                        accept=".txt,.openair,.air,.geojson,.json"
                        multiple
                        onChange={async (event) => {
                          const files = event.target.files;
                          if (!files?.length) return;
                          try {
                            setError("");
                            await uploadAirspaceFile(files);
                          } catch (caught) {
                            setError(caught instanceof Error ? caught.message : "Failed to import the selected overlay files.");
                          } finally {
                            event.currentTarget.value = "";
                          }
                        }}
                      />
                    </label>
                  </div>
                ) : (
                  <p className="hint">Only organizers and admins can upload overlay files. Pilots still see the saved overlays on the task map.</p>
                )
              ) : (
                <p className="hint">Create or select an event before uploading overlay files.</p>
              )}
              <div className="participant-table-wrap">
                <table className="participant-table">
                  <thead>
                    <tr>
                      <th>File name</th>
                      <th>Label</th>
                      <th>Format</th>
                      <th>Visible</th>
                      <th>Uploaded</th>
                      {canManagePlatform ? <th className="participant-table-actions">Actions</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {airspaceSources.length ? (
                      airspaceSources.map((source) => (
                        <tr key={source.id}>
                          <td><strong>{source.filename}</strong></td>
                          <td>
                            {canManagePlatform ? (
                              <select
                                value={source.kind ?? ""}
                                onChange={(event) => void toggleAirspaceSource(source, { kind: event.target.value as AirspaceSourceRecord["kind"] })}
                              >
                                <option value="">Select label</option>
                                <option value="airspace">Airspace</option>
                                <option value="restricted_field">Restricted fields</option>
                              </select>
                            ) : (
                              airspaceSourceLabel(source.kind) || "-"
                            )}
                          </td>
                          <td>{source.file_format.toUpperCase()}</td>
                          <td>
                            <label className="task-advanced-toggle">
                              <input
                                type="checkbox"
                                checked={source.enabled ?? true}
                                disabled={!canManagePlatform}
                                onChange={(event) => void toggleAirspaceSource(source, { enabled: event.target.checked })}
                              />
                              <span>{source.enabled ?? true ? "Visible" : "Hidden"}</span>
                            </label>
                          </td>
                          <td>{new Date(source.uploaded_at).toLocaleString()}</td>
                          {canManagePlatform ? (
                            <td className="participant-table-actions">
                              <button type="button" className="ghost-button danger-button" onClick={() => void deleteAirspaceSource(source)}>Delete</button>
                            </td>
                          ) : null}
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={canManagePlatform ? 6 : 5} className="participant-table-empty">No overlay files uploaded for this event yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </SectionCard>
        </>
      ) : null}
      {eventTab === "participants" ? renderParticipantCards() : null}
      </div>
    </div>
  );
}
