"use client";

import { type FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { SectionCard } from "../SectionCard";
import { TaskMap, type MapTelemetrySmoothing } from "../TaskMap";
import { LabelWithHelp, type ScoringHelpId } from "../../lib/scoringParameters";
import type {
  AirspaceCategoryOption,
  AirspaceSourceRecord,
  AccountSettingsRecord,
  BuddyGroup,
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
  { value: "GAP2025", label: "GAP 2025" },
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
  GAP2025: {
    ...formulaPresetBase,
    nominal_goal_percent: 0.3,
    nominal_distance_km: 50,
    nominal_launch: 0.96,
    goal_ss_penalty: 0,
    time_points_if_not_in_goal: 0.8,
    use_leading_points: true,
    use_arrival_position_points: true,
    use_flat_decline_of_timepoints: true,
    redistribute_removed_time_points_as_distance_points: true,
    use_distance_squared_for_lc: true,
    use_semi_circle_control_zone_for_goal_line: true,
    use_difficulty_for_distance_points: true,
    use_proportional_leading_weight_if_nobody_in_goal: false,
    use_best_score_for_ftv_validity: true,
    stopped_glide_bonus: 5,
    jump_the_gun_factor: 2,
    jump_the_gun_max_seconds: 300,
    min_time_span_for_valid_task_minutes: 45,
    number_of_decimals_task_results: 1,
    number_of_decimals_competition_results: 1,
  },
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
  GAP2025: {
    summary: "Current GAP formula profile",
    details:
      "GAP 2025 keeps the post-2021 GAP model with difficulty-weighted distance, time, leading, and optional arrival position points. " +
      "For hang-gliding Race to Goal tasks, enable leading and arrival position points when matching official AirScore output.",
  },
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
const challengeScoringFields = [
  "scoring_formula",
  "nominal_distance_km",
  "nominal_time_hours",
  "nominal_launch",
  "minimum_distance_km",
  "nominal_goal_percent",
  "score_back_time_minutes",
  "goal_ss_penalty",
  "day_quality_override",
  "time_points_if_not_in_goal",
  "jump_the_gun_factor",
  "jump_the_gun_max_seconds",
  "default_start_gate_count",
  "default_start_gate_interval_seconds",
  "stopped_glide_bonus",
  "use_1000_points_for_max_day_quality",
  "normalize_1000_before_day_quality",
  "use_distance_points",
  "use_time_points",
  "use_leading_points",
  "use_arrival_position_points",
  "use_arrival_time_points",
  "use_departure_points",
  "use_difficulty_for_distance_points",
  "use_distance_squared_for_lc",
  "use_semi_circle_control_zone_for_goal_line",
  "use_proportional_leading_weight_if_nobody_in_goal",
  "redistribute_removed_time_points_as_distance_points",
  "use_best_score_for_ftv_validity",
  "use_constant_leading_weight",
  "use_pwca2019_for_lc",
  "use_flat_decline_of_timepoints",
  "scoring_altitude",
  "final_glide_decelerator",
  "no_final_glide_decelerator_reason",
  "min_time_span_for_valid_task_minutes",
  "leading_weight_factor",
  "turnpoint_radius_tolerance",
  "turnpoint_radius_minimum_absolute_tolerance_m",
  "number_of_decimals_task_results",
  "number_of_decimals_competition_results",
  "visible_airspace_classes_json",
  "show_restricted_fields",
  "penalties_json",
] as const;
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
const fallbackTimeZoneOptions = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Phoenix",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Europe/Vienna",
  "Australia/Sydney",
  "Pacific/Auckland",
] as const;

type PresetFeedback = { type: "success" | "error" | "pending"; text: string } | null;
type TurnpointSymbol = "" | "grass_strip" | "paved_runway" | "dot" | "bar";
type TurnpointSortKey = "name" | "symbol";
type TurnpointSortState = { key: TurnpointSortKey; direction: "asc" | "desc" } | null;
type EditableTurnpoint = {
  id: number | null;
  name: string;
  code: string;
  symbol: TurnpointSymbol;
  latitude: string;
  longitude: string;
  elevation_m: string;
  extra_json: Record<string, string>;
};

const turnpointSymbolOptions = [
  { value: "", label: "Blank" },
  { value: "grass_strip", label: "Grass Strip" },
  { value: "paved_runway", label: "Paved Runway" },
  { value: "dot", label: "Dot" },
  { value: "bar", label: "Bar" },
] satisfies Array<{ value: TurnpointSymbol; label: string }>;

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") return configured || "/backend";
  return configured ?? "/backend";
}

async function apiFetchBlob(path: string, token: string): Promise<{ blob: Blob; filename: string | null }> {
  const response = await fetch(`${resolveApiBase()}${path}`, {
    cache: "no-store",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) {
    throw new Error((await response.text()) || `Request failed (${response.status})`);
  }
  const disposition = response.headers.get("content-disposition");
  const filenameMatch = disposition?.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i);
  const filename = filenameMatch ? decodeURIComponent(filenameMatch[1] ?? filenameMatch[2] ?? "") : null;
  return { blob: await response.blob(), filename };
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

function challengeDefaultsToForm(settings: Record<string, unknown>): EventFormState {
  const form = blankChallengeDefaultsForm();
  for (const field of challengeScoringFields) {
    if (settings[field] !== undefined) {
      (form as Record<string, unknown>)[field] = settings[field];
    }
  }
  return form;
}

function formToChallengeDefaults(form: EventFormState, existing: Record<string, unknown>): Record<string, unknown> {
  const next = { ...existing };
  for (const field of challengeScoringFields) {
    next[field] = (form as unknown as Record<string, unknown>)[field];
  }
  return next;
}

function blankChallengeDefaultsForm(): EventFormState {
  return {
    name: "Challenge Defaults",
    location: "",
    starts_on: new Date().toISOString().slice(0, 10),
    ends_on: new Date().toISOString().slice(0, 10),
    timezone: "UTC",
    scoring_formula: "GAP2021",
    nominal_distance_km: 60,
    nominal_time_hours: 1.5,
    nominal_launch: 0.95,
    minimum_distance_km: 5,
    nominal_goal_percent: 0.3,
    score_back_time_minutes: 15,
    goal_ss_penalty: 0,
    day_quality_override: 0,
    time_points_if_not_in_goal: 1,
    jump_the_gun_factor: 0,
    jump_the_gun_max_seconds: 0,
    default_start_gate_count: 5,
    default_start_gate_interval_seconds: 900,
    stopped_glide_bonus: 0,
    use_1000_points_for_max_day_quality: false,
    normalize_1000_before_day_quality: false,
    use_distance_points: true,
    use_time_points: true,
    use_leading_points: true,
    use_arrival_position_points: false,
    use_arrival_time_points: false,
    use_departure_points: false,
    use_difficulty_for_distance_points: true,
    use_distance_squared_for_lc: false,
    use_semi_circle_control_zone_for_goal_line: true,
    use_proportional_leading_weight_if_nobody_in_goal: true,
    redistribute_removed_time_points_as_distance_points: false,
    use_best_score_for_ftv_validity: true,
    use_constant_leading_weight: false,
    use_pwca2019_for_lc: false,
    use_flat_decline_of_timepoints: false,
    scoring_altitude: "GPS",
    final_glide_decelerator: "none",
    no_final_glide_decelerator_reason: "",
    min_time_span_for_valid_task_minutes: 60,
    leading_weight_factor: 1,
    turnpoint_radius_tolerance: 0.0005,
    turnpoint_radius_minimum_absolute_tolerance_m: 5,
    number_of_decimals_task_results: 2,
    number_of_decimals_competition_results: 1,
    visible_airspace_classes_json: ["B", "C", "D", "P", "Q", "R", "TFR", "OTHER"],
    show_restricted_fields: true,
    penalties_text: "{}",
    is_public_tracking: false,
    visibility: "private",
    event_kind: "challenge",
    owner_user_id: null,
    source_buddy_group_id: null,
    public_slug: null,
    public_listed: false,
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

function browserTimeZone(): string {
  if (typeof Intl === "undefined") return "UTC";
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

function timeZoneOptions(localTimeZone: string, selectedTimeZone: string): string[] {
  const intlWithZones = Intl as typeof Intl & { supportedValuesOf?: (key: "timeZone") => string[] };
  const allZones = (intlWithZones.supportedValuesOf?.("timeZone") ?? [...fallbackTimeZoneOptions]).filter(
    (timezone) => timezone !== "UTC" || timezone === localTimeZone || timezone === selectedTimeZone,
  );
  return Array.from(new Set([localTimeZone, selectedTimeZone, ...allZones].filter(Boolean)));
}

function normalizeEditableSymbol(value: unknown): TurnpointSymbol {
  return value === "grass_strip" || value === "paved_runway" || value === "dot" || value === "bar" ? value : "";
}

function turnpointSymbolLabel(symbol: unknown): string {
  return turnpointSymbolOptions.find((option) => option.value === normalizeEditableSymbol(symbol))?.label ?? "";
}

function turnpointToEditable(turnpoint?: TurnpointRecord | null, fallback?: { latitude: number; longitude: number; elevationM?: number | null }): EditableTurnpoint {
  return {
    id: turnpoint?.id ?? null,
    name: turnpoint?.name ?? "",
    code: turnpoint?.code ?? "",
    symbol: normalizeEditableSymbol(turnpoint?.symbol),
    latitude: String(turnpoint?.latitude ?? fallback?.latitude ?? ""),
    longitude: String(turnpoint?.longitude ?? fallback?.longitude ?? ""),
    elevation_m: turnpoint?.elevation_m == null ? (fallback?.elevationM == null ? "" : String(Math.round(fallback.elevationM))) : String(turnpoint.elevation_m),
    extra_json: Object.fromEntries(Object.entries(turnpoint?.extra_json ?? {}).map(([key, value]) => [key, String(value ?? "")])),
  };
}

function editableToPayload(editable: EditableTurnpoint) {
  const latitude = Number(editable.latitude);
  const longitude = Number(editable.longitude);
  const elevation = editable.elevation_m.trim() ? Number(editable.elevation_m) : null;
  if (!editable.name.trim()) throw new Error("Waypoint name is required.");
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) throw new Error("Latitude must be between -90 and 90.");
  if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) throw new Error("Longitude must be between -180 and 180.");
  if (elevation !== null && !Number.isFinite(elevation)) throw new Error("Altitude must be a number.");
  return {
    name: editable.name.trim(),
    code: editable.code.trim() || null,
    symbol: editable.symbol || null,
    latitude,
    longitude,
    elevation_m: elevation,
    extra_json: editable.extra_json,
  };
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function TurnpointSymbolIcon({ symbol }: { symbol: TurnpointSymbol }) {
  if (symbol === "grass_strip" || symbol === "paved_runway") {
    return <span className={`turnpoint-symbol-icon ${symbol}`} aria-hidden="true">✈</span>;
  }
  if (symbol === "bar") {
    return <span className="turnpoint-symbol-icon bar" aria-hidden="true" />;
  }
  if (symbol === "dot") {
    return <span className="turnpoint-symbol-icon dot" aria-hidden="true" />;
  }
  return <span className="turnpoint-symbol-icon blank" aria-hidden="true" />;
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
  settingsForm: AccountSettingsRecord;
  setSettingsForm: (form: AccountSettingsRecord | ((current: AccountSettingsRecord) => AccountSettingsRecord)) => void;
  saveChallengeSettings: (settings: Record<string, unknown>) => Promise<Record<string, unknown>>;
  canManagePlatform: boolean;
  canManageOfficialEvents: boolean;
  canCreateChallenge: boolean;
  isAdmin: boolean;
  selectEvent: (event: EventRecord) => void;
  createEventDraft: (kind: "competition" | "challenge") => void;
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
  telemetrySmoothing?: MapTelemetrySmoothing;
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
    settingsForm,
    setSettingsForm,
    saveChallengeSettings,
    canManagePlatform,
    canManageOfficialEvents,
    canCreateChallenge,
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
    telemetrySmoothing,
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
  const [buddyGroups, setBuddyGroups] = useState<BuddyGroup[]>([]);
  const [buddyGroupsFeedback, setBuddyGroupsFeedback] = useState("");
  const [challengeDefaultsForm, setChallengeDefaultsForm] = useState<EventFormState>(() => challengeDefaultsToForm(settingsForm.challenge_settings_json ?? {}));
  const [challengeTurnpointSources, setChallengeTurnpointSources] = useState<TurnpointSourceRecord[]>([]);
  const [challengeAirspaceSources, setChallengeAirspaceSources] = useState<AirspaceSourceRecord[]>([]);
  const [challengeSettingsFeedback, setChallengeSettingsFeedback] = useState<PresetFeedback>(null);
  const [startsOnDisplay, setStartsOnDisplay] = useState("");
  const [endsOnDisplay, setEndsOnDisplay] = useState("");
  const [selectedTurnpointSourceId, setSelectedTurnpointSourceId] = useState<number | null>(null);
  const [sourceTurnpoints, setSourceTurnpoints] = useState<TurnpointRecord[]>([]);
  const [sourceTurnpointsLoading, setSourceTurnpointsLoading] = useState(false);
  const [editingTurnpointId, setEditingTurnpointId] = useState<number | null>(null);
  const [turnpointEdit, setTurnpointEdit] = useState<EditableTurnpoint | null>(null);
  const [draftTurnpoint, setDraftTurnpoint] = useState<EditableTurnpoint | null>(null);
  const [turnpointSort, setTurnpointSort] = useState<TurnpointSortState>(null);
  const startsOnPickerRef = useRef<HTMLInputElement | null>(null);
  const endsOnPickerRef = useRef<HTMLInputElement | null>(null);
  const scoringTemplateOptions = events.filter((event) => event.id !== eventEditorId);
  const sortedEvents = [...events].sort((a, b) => {
    const da = a.starts_on ? new Date(a.starts_on).getTime() : -Infinity;
    const db = b.starts_on ? new Date(b.starts_on).getTime() : -Infinity;
    return db - da;
  });
  const canCreateAnyEvent = canManageOfficialEvents || canCreateChallenge;
  const isChallenge = eventForm.event_kind === "challenge";
  const visibleEventTabs = isChallenge ? eventTabItems.filter((tab) => tab.id === "details") : eventTabItems;
  const localTimeZone = useMemo(() => browserTimeZone(), []);
  const timezoneOptions = useMemo(() => timeZoneOptions(localTimeZone, eventForm.timezone), [localTimeZone, eventForm.timezone]);

  const autoSaveOverlaySettings = (nextForm: EventFormState) => {
    setEventForm(nextForm);
    void saveEventForm(nextForm, "Saved overlay settings.");
  };

  useEffect(() => {
    if (!eventForm.timezone) setEventForm({ ...eventForm, timezone: localTimeZone });
  }, [eventForm, localTimeZone, setEventForm]);

  useEffect(() => {
    setStartsOnDisplay(formatLongDate(eventForm.starts_on));
    setEndsOnDisplay(formatLongDate(eventForm.ends_on));
  }, [eventForm.starts_on, eventForm.ends_on]);

  useEffect(() => {
    setChallengeDefaultsForm(challengeDefaultsToForm(settingsForm.challenge_settings_json ?? {}));
  }, [settingsForm.challenge_settings_json]);

  useEffect(() => {
    if (isChallenge && eventTab !== "details" && eventTab !== "challenge_settings") {
      setEventTab("details");
    }
  }, [eventTab, isChallenge, setEventTab]);

  useEffect(() => {
    let cancelled = false;
    async function loadChallengeDefaultSources() {
      const templateEventId = settingsForm.challenge_settings_json?.template_event_id;
      if (!token || typeof templateEventId !== "number") {
        setChallengeTurnpointSources([]);
        setChallengeAirspaceSources([]);
        return;
      }
      try {
        const [loadedTurnpoints, loadedAirspaces] = await Promise.all([
          apiFetch<TurnpointSourceRecord[]>(`/api/events/${templateEventId}/turnpoint-sources`, token),
          apiFetch<AirspaceSourceRecord[]>(`/api/events/${templateEventId}/airspace-sources`, token),
        ]);
        if (!cancelled) {
          setChallengeTurnpointSources(loadedTurnpoints);
          setChallengeAirspaceSources(loadedAirspaces);
        }
      } catch (caught) {
        if (!cancelled) setChallengeSettingsFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not load challenge default files." });
      }
    }
    void loadChallengeDefaultSources();
    return () => {
      cancelled = true;
    };
  }, [settingsForm.challenge_settings_json?.template_event_id, token]);

  useEffect(() => {
    let cancelled = false;
    async function loadBuddyGroups() {
      if (!token) return;
      try {
        const groups = await apiFetch<BuddyGroup[]>("/api/buddies/groups", token);
        if (!cancelled) {
          setBuddyGroups(groups);
          setBuddyGroupsFeedback("");
        }
      } catch (caught) {
        if (!cancelled) setBuddyGroupsFeedback(caught instanceof Error ? `Buddy groups: ${caught.message}` : "Buddy groups could not be loaded.");
      }
    }
    void loadBuddyGroups();
    return () => {
      cancelled = true;
    };
  }, [token]);

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
    setSelectedTurnpointSourceId(null);
    setSourceTurnpoints([]);
    setEditingTurnpointId(null);
    setTurnpointEdit(null);
    setDraftTurnpoint(null);
  }, [eventEditorId]);

  useEffect(() => {
    if (selectedTurnpointSourceId && !turnpointSources.some((source) => source.id === selectedTurnpointSourceId)) {
      setSelectedTurnpointSourceId(null);
      setSourceTurnpoints([]);
    }
  }, [selectedTurnpointSourceId, turnpointSources]);

  const selectedTurnpointSource = turnpointSources.find((source) => source.id === selectedTurnpointSourceId) ?? null;
  const selectedSourceExtraColumns = Array.from(new Set(sourceTurnpoints.flatMap((turnpoint) => Object.keys(turnpoint.extra_json ?? {}))));
  const turnpointTableColSpan = 5 + selectedSourceExtraColumns.length + (canManagePlatform ? 1 : 0);
  const sortedSourceTurnpoints = useMemo(() => {
    if (!turnpointSort) return sourceTurnpoints;
    const direction = turnpointSort.direction === "asc" ? 1 : -1;
    return [...sourceTurnpoints].sort((left, right) => {
      const leftValue = turnpointSort.key === "name" ? left.name : turnpointSymbolLabel(left.symbol);
      const rightValue = turnpointSort.key === "name" ? right.name : turnpointSymbolLabel(right.symbol);
      return leftValue.localeCompare(rightValue, undefined, { sensitivity: "base" }) * direction;
    });
  }, [sourceTurnpoints, turnpointSort]);

  async function loadSourceTurnpoints(sourceId: number) {
    if (!token || !selectedEventId) return;
    setSourceTurnpointsLoading(true);
    try {
      const loaded = await apiFetch<TurnpointRecord[]>(`/api/events/${selectedEventId}/turnpoint-sources/${sourceId}/turnpoints`, token);
      setSelectedTurnpointSourceId(sourceId);
      setSourceTurnpoints(loaded);
      setEditingTurnpointId(null);
      setTurnpointEdit(null);
      setDraftTurnpoint(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load that turnpoint file.");
    } finally {
      setSourceTurnpointsLoading(false);
    }
  }

  async function reloadSelectedSource() {
    if (selectedTurnpointSourceId) {
      await loadSourceTurnpoints(selectedTurnpointSourceId);
    }
  }

  async function saveTurnpointEdit() {
    if (!token || !selectedEventId || !turnpointEdit?.id) return;
    try {
      const saved = await apiFetch<TurnpointRecord>(`/api/events/${selectedEventId}/turnpoints/${turnpointEdit.id}`, token, {
        method: "PUT",
        body: JSON.stringify(editableToPayload(turnpointEdit)),
      });
      setMessage(`Saved waypoint ${saved.name}.`);
      await reloadSelectedSource();
      await loadEvent(token, selectedEventId);
      await refreshEvents(token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save that waypoint.");
    }
  }

  async function saveDraftTurnpoint() {
    if (!token || !selectedEventId || !selectedTurnpointSourceId || !draftTurnpoint) return;
    try {
      const saved = await apiFetch<TurnpointRecord>(`/api/events/${selectedEventId}/turnpoint-sources/${selectedTurnpointSourceId}/turnpoints`, token, {
        method: "POST",
        body: JSON.stringify(editableToPayload(draftTurnpoint)),
      });
      setMessage(`Added waypoint ${saved.name}.`);
      setDraftTurnpoint(null);
      await reloadSelectedSource();
      await loadEvent(token, selectedEventId);
      await refreshEvents(token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not add that waypoint.");
    }
  }

  async function deleteSourceTurnpoint(turnpoint: TurnpointRecord) {
    if (!token || !selectedEventId) return;
    const confirmed = window.confirm(`Delete waypoint "${turnpoint.name}" from ${selectedTurnpointSource?.filename ?? "this file"}?`);
    if (!confirmed) return;
    try {
      await apiFetch<void>(`/api/events/${selectedEventId}/turnpoints/${turnpoint.id}`, token, { method: "DELETE" });
      setMessage(`Deleted waypoint ${turnpoint.name}.`);
      await reloadSelectedSource();
      await loadEvent(token, selectedEventId);
      await refreshEvents(token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete that waypoint.");
    }
  }

  async function downloadTurnpointSource(source: TurnpointSourceRecord) {
    if (!token || !selectedEventId) return;
    try {
      const { blob, filename } = await apiFetchBlob(`/api/events/${selectedEventId}/turnpoint-sources/${source.id}/download`, token);
      downloadBlob(blob, filename ?? source.filename);
      setMessage(`Started downloading ${source.filename}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not download that turnpoint file.");
    }
  }

  async function renameTurnpointSource(source: TurnpointSourceRecord) {
    if (!token || !selectedEventId) return;
    const nextName = window.prompt("Rename turnpoint file", source.filename)?.trim();
    if (!nextName || nextName === source.filename) return;
    try {
      const renamed = await apiFetch<TurnpointSourceRecord>(`/api/events/${selectedEventId}/turnpoint-sources/${source.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({ filename: nextName }),
      });
      setMessage(`Renamed ${source.filename} to ${renamed.filename}.`);
      await loadEvent(token, selectedEventId);
      await refreshEvents(token);
      if (selectedTurnpointSourceId === source.id) {
        await loadSourceTurnpoints(source.id);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not rename that turnpoint file.");
    }
  }

  async function saveTurnpointSourceAs(source: TurnpointSourceRecord) {
    if (!token || !selectedEventId) return;
    const stem = source.filename.replace(/\.[^.]+$/, "");
    const suffix = source.filename.includes(".") ? source.filename.slice(source.filename.lastIndexOf(".")) : "";
    const suggested = `${stem} v2${suffix}`;
    const filename = window.prompt("Save turnpoint file as", suggested)?.trim();
    if (!filename) return;
    try {
      const saved = await apiFetch<TurnpointSourceRecord>(`/api/events/${selectedEventId}/turnpoint-sources/${source.id}/save-as`, token, {
        method: "POST",
        body: JSON.stringify({ filename }),
      });
      setMessage(`Saved ${source.filename} as ${saved.filename}.`);
      await loadEvent(token, selectedEventId);
      await refreshEvents(token);
      await loadSourceTurnpoints(saved.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save that turnpoint file as a new version.");
    }
  }

  function updateEditableExtra(target: "edit" | "draft", key: string, value: string) {
    const setter = target === "edit" ? setTurnpointEdit : setDraftTurnpoint;
    setter((current) => current ? { ...current, extra_json: { ...current.extra_json, [key]: value } } : current);
  }

  function renderSymbolSelect(value: TurnpointSymbol, onChange: (next: TurnpointSymbol) => void) {
    return (
      <select value={value} onChange={(event) => onChange(normalizeEditableSymbol(event.target.value))}>
        {turnpointSymbolOptions.map((option) => (
          <option key={option.value || "blank"} value={option.value}>{option.label}</option>
        ))}
      </select>
    );
  }

  function toggleTurnpointSort(key: TurnpointSortKey) {
    setTurnpointSort((current) => {
      if (!current || current.key !== key) return { key, direction: "asc" };
      return { key, direction: current.direction === "asc" ? "desc" : "asc" };
    });
  }

  function sortLabel(key: TurnpointSortKey) {
    if (turnpointSort?.key !== key) return "Sort";
    return turnpointSort.direction === "asc" ? "A-Z" : "Z-A";
  }

  function closeTurnpointSourceDetail() {
    setSelectedTurnpointSourceId(null);
    setSourceTurnpoints([]);
    setEditingTurnpointId(null);
    setTurnpointEdit(null);
    setDraftTurnpoint(null);
  }

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

  async function saveChallengeDefaults(nextSettings?: Record<string, unknown>) {
    try {
      setChallengeSettingsFeedback({ type: "pending", text: "Saving challenge settings..." });
      const saved = await saveChallengeSettings(nextSettings ?? formToChallengeDefaults(challengeDefaultsForm, settingsForm.challenge_settings_json ?? {}));
      setSettingsForm((current) => ({ ...current, challenge_settings_json: saved }));
      setChallengeSettingsFeedback({ type: "success", text: "Saved challenge settings." });
    } catch (caught) {
      setChallengeSettingsFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not save challenge settings." });
    }
  }

  async function uploadChallengeDefaultFile(path: string, file: File) {
    const response = await uploadFile(path, file) as { settings?: Record<string, unknown> };
    const settings = response.settings ?? {};
    setSettingsForm((current) => ({ ...current, challenge_settings_json: settings }));
    setChallengeSettingsFeedback({ type: "success", text: `Uploaded ${file.name}.` });
  }

  function updateChallengeDefaults(patch: Partial<EventFormState>) {
    setChallengeDefaultsForm((current) => ({ ...current, ...patch }));
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
            {canCreateAnyEvent || canManagePlatform ? (
              <div className="event-selector-actions">
                {canManageOfficialEvents ? <button className="ghost-button" type="button" onClick={() => void createEventDraft("competition")}>Create Official Event</button> : null}
                {canCreateChallenge ? <button className="ghost-button" type="button" onClick={() => void createEventDraft("challenge")}>Create Challenge</button> : null}
                {canManagePlatform ? <button className="primary-button" type="button" onClick={() => void saveEventForm(eventForm, `${eventEditorId ? "Updated" : "Created"} ${eventForm.event_kind === "challenge" ? "challenge" : "event"} ${eventForm.name || "draft"}.`)}>{eventEditorId ? "Save" : "Create"}</button> : null}
                {canManageOfficialEvents && eventEditorId ? <button type="button" className="ghost-button" onClick={() => void duplicateSelectedEvent()}>Duplicate event</button> : null}
                {isAdmin && eventEditorId ? <button type="button" className="ghost-button danger-button" onClick={() => void deleteEvent()}>Delete event</button> : null}
                <button type="button" className="ghost-button" onClick={() => setEventTab("challenge_settings")}>Challenge Settings</button>
              </div>
            ) : null}
          </div>
        </SectionCard>
      <div className="tab-row">
        {visibleEventTabs.map((tab) => (
          <button key={tab.id} type="button" className={eventTab === tab.id ? "tab-button active" : "tab-button"} onClick={() => setEventTab(tab.id)}>
            {tab.label}
          </button>
        ))}
      </div>
      <div className="event-workspace-grid event-workspace-stack">
        {eventTab === "challenge_settings" ? (
          <SectionCard title="Challenge Settings">
            <div className="stack form-block compact-event-form compact-clusters">
              {challengeSettingsFeedback ? <div className={`status-chip ${challengeSettingsFeedback.type}`}>{challengeSettingsFeedback.text}</div> : null}
              <div className="fieldset-grid two-up">
                <fieldset className="fieldset-cluster">
                  <legend>Default files</legend>
                  <div className="cluster-stack">
                    <label className="stack compact">
                      <span>Waypoint file</span>
                      <select
                        value={Number(settingsForm.challenge_settings_json?.turnpoint_source_id ?? "") || ""}
                        onChange={(event) => void saveChallengeDefaults({ ...(settingsForm.challenge_settings_json ?? {}), turnpoint_source_id: Number(event.target.value) || null })}
                      >
                        <option value="">No default waypoint file</option>
                        {challengeTurnpointSources.map((source) => (
                          <option key={source.id} value={source.id}>{source.filename}</option>
                        ))}
                      </select>
                    </label>
                    <label className="file-input">
                      Upload waypoint file
                      <input
                        type="file"
                        accept=".csv,.geojson,.json,.gpx"
                        onChange={async (event) => {
                          const file = event.target.files?.[0];
                          if (!file) return;
                          try {
                            await uploadChallengeDefaultFile("/api/auth/challenge-settings/turnpoints/upload", file);
                          } catch (caught) {
                            setChallengeSettingsFeedback({ type: "error", text: caught instanceof Error ? caught.message : `Failed to upload ${file.name}.` });
                          } finally {
                            event.currentTarget.value = "";
                          }
                        }}
                      />
                    </label>
                    <label className="stack compact">
                      <span>Airspace file</span>
                      <select
                        value={Number(settingsForm.challenge_settings_json?.airspace_source_id ?? "") || ""}
                        onChange={(event) => void saveChallengeDefaults({ ...(settingsForm.challenge_settings_json ?? {}), airspace_source_id: Number(event.target.value) || null })}
                      >
                        <option value="">No default airspace file</option>
                        {challengeAirspaceSources.filter((source) => source.kind !== "restricted_field").map((source) => (
                          <option key={source.id} value={source.id}>{source.filename}</option>
                        ))}
                      </select>
                    </label>
                    <label className="file-input">
                      Upload airspace
                      <input
                        type="file"
                        accept=".txt,.openair,.air,.geojson,.json"
                        onChange={async (event) => {
                          const file = event.target.files?.[0];
                          if (!file) return;
                          try {
                            await uploadChallengeDefaultFile("/api/auth/challenge-settings/airspaces/upload?kind=airspace", file);
                          } catch (caught) {
                            setChallengeSettingsFeedback({ type: "error", text: caught instanceof Error ? caught.message : `Failed to upload ${file.name}.` });
                          } finally {
                            event.currentTarget.value = "";
                          }
                        }}
                      />
                    </label>
                    <label className="stack compact">
                      <span>Restricted-field file</span>
                      <select
                        value={Number(settingsForm.challenge_settings_json?.restricted_field_source_id ?? "") || ""}
                        onChange={(event) => void saveChallengeDefaults({ ...(settingsForm.challenge_settings_json ?? {}), restricted_field_source_id: Number(event.target.value) || null })}
                      >
                        <option value="">No default restricted fields</option>
                        {challengeAirspaceSources.filter((source) => source.kind === "restricted_field").map((source) => (
                          <option key={source.id} value={source.id}>{source.filename}</option>
                        ))}
                      </select>
                    </label>
                    <label className="file-input">
                      Upload restricted fields
                      <input
                        type="file"
                        accept=".txt,.openair,.air,.geojson,.json"
                        onChange={async (event) => {
                          const file = event.target.files?.[0];
                          if (!file) return;
                          try {
                            await uploadChallengeDefaultFile("/api/auth/challenge-settings/airspaces/upload?kind=restricted_field", file);
                          } catch (caught) {
                            setChallengeSettingsFeedback({ type: "error", text: caught instanceof Error ? caught.message : `Failed to upload ${file.name}.` });
                          } finally {
                            event.currentTarget.value = "";
                          }
                        }}
                      />
                    </label>
                  </div>
                </fieldset>
                <fieldset className="fieldset-cluster">
                  <legend>Default scoring</legend>
                  <div className="cluster-stack">
                    <label className="stack compact">
                      <span>Scoring formula</span>
                      <select value={challengeDefaultsForm.scoring_formula} onChange={(event) => updateChallengeDefaults({ scoring_formula: event.target.value })}>
                        {scoringFormulaOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                      </select>
                    </label>
                    <div className="inline-grid">
                      <label className="stack compact">
                        <span>Minimum distance (km)</span>
                        <input type="number" min={0} step="0.1" value={challengeDefaultsForm.minimum_distance_km} onChange={(event) => updateChallengeDefaults({ minimum_distance_km: Number(event.target.value) || 0 })} />
                      </label>
                      <label className="stack compact">
                        <span>Nominal distance (km)</span>
                        <input type="number" min={0} step="1" value={challengeDefaultsForm.nominal_distance_km} onChange={(event) => updateChallengeDefaults({ nominal_distance_km: Number(event.target.value) || 0 })} />
                      </label>
                    </div>
                    <div className="inline-grid">
                      <label className="stack compact">
                        <span>Nominal time (hours)</span>
                        <input type="number" min={0} step="0.1" value={challengeDefaultsForm.nominal_time_hours} onChange={(event) => updateChallengeDefaults({ nominal_time_hours: Number(event.target.value) || 0 })} />
                      </label>
                      <label className="stack compact">
                        <span>Nominal launch</span>
                        <input type="number" min={0} max={1} step="0.01" value={challengeDefaultsForm.nominal_launch} onChange={(event) => updateChallengeDefaults({ nominal_launch: Number(event.target.value) || 0 })} />
                      </label>
                    </div>
                    <div className="inline-grid">
                      <label className="stack compact">
                        <span>Default start gates</span>
                        <input type="number" min={1} step="1" value={challengeDefaultsForm.default_start_gate_count} onChange={(event) => updateChallengeDefaults({ default_start_gate_count: Math.max(1, Number(event.target.value) || 1) })} />
                      </label>
                      <label className="stack compact">
                        <span>Gate interval (minutes)</span>
                        <input type="number" min={0} step="1" value={Math.round(challengeDefaultsForm.default_start_gate_interval_seconds / 60)} onChange={(event) => updateChallengeDefaults({ default_start_gate_interval_seconds: Math.max(0, Number(event.target.value) || 0) * 60 })} />
                      </label>
                    </div>
                    <div className="event-airspace-class-row">
                      {airspaceCategoryOptions.map((option) => (
                        <label key={option.value} className="task-advanced-toggle">
                          <input
                            type="checkbox"
                            checked={challengeDefaultsForm.visible_airspace_classes_json.includes(option.value)}
                            onChange={() => {
                              const existing = new Set(challengeDefaultsForm.visible_airspace_classes_json);
                              if (existing.has(option.value)) existing.delete(option.value);
                              else existing.add(option.value);
                              updateChallengeDefaults({ visible_airspace_classes_json: Array.from(existing) });
                            }}
                          />
                          <span>{option.label}</span>
                        </label>
                      ))}
                    </div>
                    <label className="task-advanced-toggle">
                      <input type="checkbox" checked={challengeDefaultsForm.show_restricted_fields} onChange={(event) => updateChallengeDefaults({ show_restricted_fields: event.target.checked })} />
                      <span>Show restricted fields</span>
                    </label>
                    <div className="button-row">
                      <button type="button" className="primary-button" onClick={() => void saveChallengeDefaults()}>Save challenge settings</button>
                      {selectedEvent ? <button type="button" className="ghost-button" onClick={() => setChallengeDefaultsForm(scoringFormFromEvent(selectedEvent, challengeDefaultsForm))}>Copy scoring from selected event</button> : null}
                    </div>
                  </div>
                </fieldset>
              </div>
            </div>
          </SectionCard>
        ) : null}
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
                  <label className="stack compact">
                    <span>Competition type</span>
                    <select
                      value={eventForm.event_kind}
                      onChange={(event) => {
                        const nextKind = event.target.value as "competition" | "challenge";
                        setEventForm({
                          ...eventForm,
                          event_kind: nextKind,
                          source_buddy_group_id: nextKind === "challenge" ? eventForm.source_buddy_group_id : null,
                          public_listed: nextKind === "challenge" ? eventForm.public_listed : true,
                        });
                      }}
                    >
                      <option value="competition" disabled={!canManageOfficialEvents}>Official event</option>
                      <option value="challenge">Buddy challenge</option>
                    </select>
                  </label>
                  {eventForm.event_kind === "challenge" ? (
                    <>
                      <label className="stack compact">
                        <span>Buddy group</span>
                        <select
                          value={eventForm.source_buddy_group_id ?? ""}
                          onChange={(event) => setEventForm({ ...eventForm, source_buddy_group_id: Number(event.target.value) || null })}
                        >
                          <option value="">No buddy group</option>
                          {buddyGroups.map((group) => (
                            <option key={group.id} value={group.id}>{group.name}</option>
                          ))}
                        </select>
                      </label>
                      {buddyGroupsFeedback ? <p className="muted">{buddyGroupsFeedback}</p> : null}
                      <label className="task-advanced-toggle">
                        <input type="checkbox" checked={eventForm.public_listed} onChange={(event) => setEventForm({ ...eventForm, public_listed: event.target.checked })} />
                        <span>List under public buddy challenges</span>
                      </label>
                    </>
                  ) : null}
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
                      <select value={eventForm.timezone || localTimeZone} onChange={(event) => setEventForm({ ...eventForm, timezone: event.target.value })}>
                        {timezoneOptions.map((timezone) => (
                          <option key={timezone} value={timezone}>{timezone === localTimeZone ? `Current location - ${timezone}` : timezone}</option>
                        ))}
                      </select>
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
                          <td className="turnpoint-file-name-cell">
                            <button type="button" className="link-button" onClick={() => void loadSourceTurnpoints(source.id)}>
                              <strong>{source.filename}</strong>
                            </button>
                          </td>
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
                              <button type="button" className="ghost-button" onClick={() => void downloadTurnpointSource(source)}>Download</button>
                              <button type="button" className="ghost-button" onClick={() => void renameTurnpointSource(source)}>Rename</button>
                              <button type="button" className="ghost-button" onClick={() => void saveTurnpointSourceAs(source)}>Save as</button>
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
              {selectedTurnpointSource ? (
                <div className="turnpoint-file-detail">
                  <div className="results-sheet-header">
                    <div>
                      <h3>{selectedTurnpointSource.filename}</h3>
                      <p className="hint">{sourceTurnpoints.length} waypoint{sourceTurnpoints.length === 1 ? "" : "s"} in this file. Click the map to draft a new waypoint.</p>
                    </div>
                    <div className="button-row">
                      {canManagePlatform ? (
                        <>
                          <button type="button" className="ghost-button" onClick={() => void downloadTurnpointSource(selectedTurnpointSource)}>Download</button>
                          <button type="button" className="ghost-button" onClick={() => void renameTurnpointSource(selectedTurnpointSource)}>Rename</button>
                          <button type="button" className="ghost-button" onClick={() => void saveTurnpointSourceAs(selectedTurnpointSource)}>Save as</button>
                        </>
                      ) : null}
                      <button type="button" className="ghost-button" onClick={() => void reloadSelectedSource()}>Refresh</button>
                      <button type="button" className="turnpoint-detail-close" onClick={closeTurnpointSourceDetail} aria-label="Close turnpoint file detail">x</button>
                    </div>
                  </div>
                  <div className="turnpoint-file-layout">
                    <div className="turnpoint-editor-map">
                      <TaskMap
                        turnpoints={sourceTurnpoints}
                        airspaces={[]}
                        taskPoints={[]}
                        track={null}
                        editable={canManagePlatform}
                        onSelectTurnpoint={(turnpoint) => {
                          if (!canManagePlatform) return;
                          const sourceTurnpoint = sourceTurnpoints.find((candidate) => candidate.id === turnpoint.id);
                          if (!sourceTurnpoint) return;
                          setDraftTurnpoint(null);
                          setEditingTurnpointId(sourceTurnpoint.id);
                          setTurnpointEdit(turnpointToEditable(sourceTurnpoint));
                        }}
                        onMapClick={(position) => {
                          if (!canManagePlatform) return;
                          setEditingTurnpointId(null);
                          setTurnpointEdit(null);
                          setDraftTurnpoint(turnpointToEditable(null, position));
                        }}
                        fitKey={`${selectedTurnpointSource.id}-${sourceTurnpoints.length}`}
                        viewStateKey={`turnpoint-source-${selectedTurnpointSource.id}`}
                        fitMaxZoom={12}
                        telemetrySmoothing={telemetrySmoothing}
                        overlayConfig={{ click_to_add_turnpoint: true }}
                      />
                    </div>
                    <div className="stack compact turnpoint-draft-panel">
                      {draftTurnpoint ? (
                        <>
                          <strong>New waypoint</strong>
                          <div className="turnpoint-edit-grid">
                            <label><span>Name</span><input value={draftTurnpoint.name} onChange={(event) => setDraftTurnpoint({ ...draftTurnpoint, name: event.target.value })} /></label>
                            <label><span>Latitude</span><input value={draftTurnpoint.latitude} inputMode="decimal" onChange={(event) => setDraftTurnpoint({ ...draftTurnpoint, latitude: event.target.value })} /></label>
                            <label><span>Longitude</span><input value={draftTurnpoint.longitude} inputMode="decimal" onChange={(event) => setDraftTurnpoint({ ...draftTurnpoint, longitude: event.target.value })} /></label>
                            <label><span>Altitude</span><input value={draftTurnpoint.elevation_m} inputMode="decimal" onChange={(event) => setDraftTurnpoint({ ...draftTurnpoint, elevation_m: event.target.value })} /></label>
                            <label><span>Symbol</span>{renderSymbolSelect(draftTurnpoint.symbol, (symbol) => setDraftTurnpoint({ ...draftTurnpoint, symbol }))}</label>
                          </div>
                          {selectedSourceExtraColumns.length ? (
                            <div className="turnpoint-extra-grid">
                              {selectedSourceExtraColumns.map((key) => (
                                <label key={key}><span>{key}</span><input value={draftTurnpoint.extra_json[key] ?? ""} onChange={(event) => updateEditableExtra("draft", key, event.target.value)} /></label>
                              ))}
                            </div>
                          ) : null}
                          <div className="button-row">
                            <button type="button" className="primary-button" onClick={() => void saveDraftTurnpoint()}>Save waypoint</button>
                            <button type="button" className="ghost-button" onClick={() => setDraftTurnpoint(null)}>Cancel</button>
                          </div>
                        </>
                      ) : turnpointEdit && editingTurnpointId ? (
                        <>
                          <strong>Edit waypoint</strong>
                          <div className="turnpoint-edit-grid">
                            <label><span>Name</span><input value={turnpointEdit.name} onChange={(event) => setTurnpointEdit({ ...turnpointEdit, name: event.target.value })} /></label>
                            <label><span>Latitude</span><input value={turnpointEdit.latitude} inputMode="decimal" onChange={(event) => setTurnpointEdit({ ...turnpointEdit, latitude: event.target.value })} /></label>
                            <label><span>Longitude</span><input value={turnpointEdit.longitude} inputMode="decimal" onChange={(event) => setTurnpointEdit({ ...turnpointEdit, longitude: event.target.value })} /></label>
                            <label><span>Altitude</span><input value={turnpointEdit.elevation_m} inputMode="decimal" onChange={(event) => setTurnpointEdit({ ...turnpointEdit, elevation_m: event.target.value })} /></label>
                            <label><span>Symbol</span>{renderSymbolSelect(turnpointEdit.symbol, (symbol) => setTurnpointEdit({ ...turnpointEdit, symbol }))}</label>
                          </div>
                          {selectedSourceExtraColumns.length ? (
                            <div className="turnpoint-extra-grid">
                              {selectedSourceExtraColumns.map((key) => (
                                <label key={key}><span>{key}</span><input value={turnpointEdit.extra_json[key] ?? ""} onChange={(event) => updateEditableExtra("edit", key, event.target.value)} /></label>
                              ))}
                            </div>
                          ) : null}
                          <div className="button-row">
                            <button type="button" className="primary-button" onClick={() => void saveTurnpointEdit()}>Save waypoint</button>
                            <button type="button" className="ghost-button" onClick={() => { setEditingTurnpointId(null); setTurnpointEdit(null); }}>Cancel</button>
                          </div>
                        </>
                      ) : (
                        <p className="hint">Click a waypoint to edit it, or click open map space to place a new waypoint draft.</p>
                      )}
                    </div>
                  </div>
                  <div className="participant-table-wrap turnpoint-table-scroll">
                    <table className="participant-table turnpoint-edit-table">
                      <thead>
                        <tr>
                          <th>
                            <button type="button" className="turnpoint-sort-button" onClick={() => toggleTurnpointSort("name")} aria-label={`Sort waypoints by name ${turnpointSort?.key === "name" && turnpointSort.direction === "asc" ? "descending" : "ascending"}`}>
                              <span>Name</span>
                              <span>{sortLabel("name")}</span>
                            </button>
                          </th>
                          <th>Lat</th>
                          <th>Long</th>
                          <th>Alt</th>
                          <th>
                            <button type="button" className="turnpoint-sort-button" onClick={() => toggleTurnpointSort("symbol")} aria-label={`Sort waypoints by symbol ${turnpointSort?.key === "symbol" && turnpointSort.direction === "asc" ? "descending" : "ascending"}`}>
                              <span>Symbol</span>
                              <span>{sortLabel("symbol")}</span>
                            </button>
                          </th>
                          {selectedSourceExtraColumns.map((key) => <th key={key}>{key}</th>)}
                          {canManagePlatform ? <th className="participant-table-actions">Actions</th> : null}
                        </tr>
                      </thead>
                      <tbody>
                        {sourceTurnpointsLoading ? (
                          <tr><td colSpan={turnpointTableColSpan} className="participant-table-empty">Loading waypoints...</td></tr>
                        ) : sortedSourceTurnpoints.length ? (
                          sortedSourceTurnpoints.map((turnpoint) => {
                            const isEditing = editingTurnpointId === turnpoint.id && turnpointEdit;
                            return (
                              <tr key={turnpoint.id}>
                                {isEditing ? (
                                  <>
                                    <td><input value={turnpointEdit.name} onChange={(event) => setTurnpointEdit({ ...turnpointEdit, name: event.target.value })} /></td>
                                    <td><input value={turnpointEdit.latitude} inputMode="decimal" onChange={(event) => setTurnpointEdit({ ...turnpointEdit, latitude: event.target.value })} /></td>
                                    <td><input value={turnpointEdit.longitude} inputMode="decimal" onChange={(event) => setTurnpointEdit({ ...turnpointEdit, longitude: event.target.value })} /></td>
                                    <td><input value={turnpointEdit.elevation_m} inputMode="decimal" onChange={(event) => setTurnpointEdit({ ...turnpointEdit, elevation_m: event.target.value })} /></td>
                                    <td>{renderSymbolSelect(turnpointEdit.symbol, (symbol) => setTurnpointEdit({ ...turnpointEdit, symbol }))}</td>
                                    {selectedSourceExtraColumns.map((key) => (
                                      <td key={key}><input value={turnpointEdit.extra_json[key] ?? ""} onChange={(event) => updateEditableExtra("edit", key, event.target.value)} /></td>
                                    ))}
                                    <td className="participant-table-actions">
                                      <button type="button" className="primary-button" onClick={() => void saveTurnpointEdit()}>Save</button>
                                      <button type="button" className="ghost-button" onClick={() => { setEditingTurnpointId(null); setTurnpointEdit(null); }}>Cancel</button>
                                    </td>
                                  </>
                                ) : (
                                  <>
                                    <td><strong>{turnpoint.name}</strong></td>
                                    <td>{turnpoint.latitude.toFixed(6)}</td>
                                    <td>{turnpoint.longitude.toFixed(6)}</td>
                                    <td>{turnpoint.elevation_m == null ? "" : Math.round(turnpoint.elevation_m)}</td>
                                    <td className="turnpoint-symbol-cell"><TurnpointSymbolIcon symbol={normalizeEditableSymbol(turnpoint.symbol)} /> {turnpointSymbolLabel(turnpoint.symbol)}</td>
                                    {selectedSourceExtraColumns.map((key) => <td key={key}>{String(turnpoint.extra_json?.[key] ?? "")}</td>)}
                                    {canManagePlatform ? (
                                      <td className="participant-table-actions">
                                        <button type="button" className="ghost-button" onClick={() => { setEditingTurnpointId(turnpoint.id); setTurnpointEdit(turnpointToEditable(turnpoint)); }}>Edit</button>
                                        <button type="button" className="ghost-button danger-button" onClick={() => void deleteSourceTurnpoint(turnpoint)}>Delete</button>
                                      </td>
                                    ) : null}
                                  </>
                                )}
                              </tr>
                            );
                          })
                        ) : (
                          <tr><td colSpan={turnpointTableColSpan} className="participant-table-empty">No waypoints in this file.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
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
