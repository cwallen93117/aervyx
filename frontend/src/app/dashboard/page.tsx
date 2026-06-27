"use client";

import { type FormEvent, type KeyboardEvent, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AppSidebar } from "../../components/AppSidebar";
import { SectionCard } from "../../components/SectionCard";
import { type MapAirspaceRegion, type MapTurnpoint, type TrackCollection } from "../../components/TaskMap";
import { computeTaskOptimization } from "../../lib/taskOptimization";

import EventsSection from "../../components/dashboard/EventsSection";
import TasksSection from "../../components/dashboard/TasksSection";
import ScoringSection from "../../components/dashboard/ScoringSection";
import LiveTrackingSection from "../../components/dashboard/LiveTrackingSection";
import LiveTrackingBacktestSection from "../../components/dashboard/LiveTrackingBacktestSection";
import LogbookSection from "../../components/dashboard/LogbookSection";
import SettingsSection from "../../components/dashboard/SettingsSection";
import AdminSection from "../../components/dashboard/AdminSection";
import SosSection from "../../components/dashboard/SosSection";
import { WeatherSection } from "../../components/dashboard/WeatherSection";
import { AirspaceSection } from "../../components/dashboard/AirspaceSection";
import ParticipantCards from "../../components/dashboard/ParticipantCards";
import DriverDashboard from "../../components/dashboard/DriverDashboard";
import { ThemeToggle } from "../../components/ThemeToggle";
import { sortTasksByDateAsc } from "../../components/dashboard/taskSorting";
import {
  type SidebarSection,
  type EventTab,
  type User,
  type AccountSettingsRecord,
  type AdminSiteRecord,
  type AdminSiteRescanResultRecord,
  type AdminSiteScanIgcResultRecord,
  type AdminUserRecord,
  type SiteSettingsRecord,
  type MapOverlayConfigRecord,
  type LogbookFlightSummaryRecord,
  type LogbookFlightDetailRecord,
  type LogbookFolderImportResultRecord,
  type LogbookBulkDeleteResponseRecord,
  type LogbookFlightFormRecord,
  type EventRecord,
  type EventFormState,
  type PilotRecord,
  type TurnpointRecord,
  type TurnpointSourceRecord,
  type TaskPointRecord,
  type TaskRecord,
  type ResultRecord,
  type PilotSummaryRecord,
  type TaskResultSummaryRecord,
  type UploadRecord,
  type TurnpointUploadResponse,
  type BulkUploadItemRecord,
  type AirspaceSourceRecord,
  type AirspaceUploadResponse,
  type TaskDraftState,
  type ScoresPortalTab,
  type ScoringTab,
  type AirspaceCategoryOption,
  type TaskPointMode,
  type DebugStatusResponse,
  blankEventForm,
} from "../../components/dashboard/types";

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) {
    return configured;
  }
  if (typeof window !== "undefined") {
    if (configured) {
      try {
        const parsed = new URL(configured);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
          return `${window.location.protocol}//${window.location.hostname}:${parsed.port || "8000"}`;
        }
      } catch {
        return configured;
      }
      return configured;
    }
    return "/backend";
  }
  return configured ?? "/backend";
}
// ---------------------------------------------------------------------------
// Airspace freshness indicator (shown in hero bar)
// ---------------------------------------------------------------------------

type AirspaceSourceStatus = {
  last_fetched_at?: string | null;
  last_checked_at?: string | null;
};

type AirspaceRefreshResult = {
  status?: string;
  error?: string;
};

type AirspaceStatusResponse = {
  sources?: {
    class?: AirspaceSourceStatus;
    sua?: AirspaceSourceStatus;
    tfr?: AirspaceSourceStatus;
  };
  manual_refresh?: {
    in_progress?: boolean;
    sources?: string[];
    results?: Record<string, AirspaceRefreshResult>;
  };
  refreshed?: Record<string, AirspaceRefreshResult>;
};

const AIRSPACE_REFRESH_POLL_MS = 3000;
const AIRSPACE_REFRESH_MAX_POLLS = 60;
const TFR_TIME_STEP_HOURS = 1;
const TFR_TIME_WINDOW_HOURS = 24;

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function failedAirspaceSources(payload: AirspaceStatusResponse) {
  const results = payload.manual_refresh?.results ?? payload.refreshed ?? {};
  return Object.entries(results)
    .filter(([, result]) => result.status === "error")
    .map(([source]) => source);
}

function latestIso(...values: Array<string | null | undefined>) {
  let latest: string | null = null;
  let latestTime = 0;
  for (const value of values) {
    if (!value) continue;
    const time = Date.parse(value);
    if (Number.isNaN(time)) continue;
    if (time > latestTime) {
      latest = value;
      latestTime = time;
    }
  }
  return latest;
}

function buildTfrTimeSteps() {
  const start = new Date();
  start.setMinutes(0, 0, 0);
  const steps: string[] = [];
  for (let hour = 0; hour <= TFR_TIME_WINDOW_HOURS; hour += TFR_TIME_STEP_HOURS) {
    steps.push(new Date(start.getTime() + hour * 60 * 60 * 1000).toISOString());
  }
  return steps;
}

function formatAirspaceTimestamp(iso: string | null | undefined) {
  if (!iso) return "--";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "--";
  return dt.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function formatTfrSliderLabel(iso: string | null | undefined) {
  if (!iso) return "";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "";
  return dt.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric" });
}

function getLocalHour(iso: string) {
  return new Date(iso).getHours();
}

function getLocalMinute(iso: string) {
  return new Date(iso).getMinutes();
}

function AirspaceTfrTimeSlider({ selectedTime, onTimeChange }: { selectedTime: string; onTimeChange: (time: string) => void }) {
  const validTimes = useMemo(() => buildTfrTimeSteps(), []);
  const selectedIdx = Math.max(0, validTimes.findIndex((time) => time === selectedTime));
  const safeIdx = selectedIdx === -1 ? 0 : selectedIdx;
  const scrubberPct = validTimes.length > 1 ? (safeIdx / (validTimes.length - 1)) * 100 : 0;
  const dayGroups = useMemo(() => {
    const groups: Array<{ label: string; startPct: number; widthPct: number }> = [];
    let currentLabel = "";
    let startIndex = 0;
    validTimes.forEach((iso, index) => {
      const label = new Date(iso).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
      if (index === 0) {
        currentLabel = label;
        startIndex = 0;
        return;
      }
      if (label !== currentLabel) {
        groups.push({
          label: currentLabel,
          startPct: (startIndex / (validTimes.length - 1)) * 100,
          widthPct: ((index - startIndex) / (validTimes.length - 1)) * 100,
        });
        currentLabel = label;
        startIndex = index;
      }
    });
    if (validTimes.length > 0) {
      groups.push({
        label: currentLabel,
        startPct: (startIndex / (validTimes.length - 1)) * 100,
        widthPct: ((validTimes.length - startIndex - 1) / (validTimes.length - 1)) * 100,
      });
    }
    return groups;
  }, [validTimes]);

  return (
    <div className="airspace-tfr-timeline" title="TFR display time">
      <div className="airspace-tfr-timeline-track-area">
        <div className="airspace-tfr-timeline-days">
          {dayGroups.map((group) => (
            <div key={group.label} className="airspace-tfr-timeline-day" style={{ left: `${group.startPct}%`, width: `${group.widthPct}%` }}>
              {group.label}
            </div>
          ))}
        </div>
        <div className="airspace-tfr-timeline-hours">
          <input
            type="range"
            className="airspace-tfr-timeline-input"
            min={0}
            max={validTimes.length - 1}
            step={1}
            value={safeIdx}
            aria-label="TFR display time"
            onChange={(event) => onTimeChange(validTimes[Number(event.target.value)])}
          />
          {validTimes.map((iso, index) => {
            const hour = getLocalHour(iso);
            const minute = getLocalMinute(iso);
            if (minute !== 0 || hour % 3 !== 0) return null;
            const pct = validTimes.length > 1 ? (index / (validTimes.length - 1)) * 100 : 0;
            const hour12 = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
            const label = `${hour12}${hour < 12 ? "a" : "p"}`;
            return (
              <div key={iso} className="airspace-tfr-timeline-tick" style={{ left: `${pct}%` }}>
                <div className={hour === 0 ? "airspace-tfr-timeline-tick-mark midnight" : "airspace-tfr-timeline-tick-mark"} />
                <span>{label}</span>
              </div>
            );
          })}
          <div className="airspace-tfr-timeline-scrubber" style={{ left: `${scrubberPct}%` }} />
        </div>
        <div className="airspace-tfr-timeline-current">{formatTfrSliderLabel(validTimes[safeIdx])}</div>
      </div>
    </div>
  );
}

function AirspaceFreshnessStatus({
  selectedTfrTime,
  onTfrTimeChange,
  onAirspaceRefreshComplete,
  onTfrRefreshComplete,
}: {
  selectedTfrTime: string;
  onTfrTimeChange: (time: string) => void;
  onAirspaceRefreshComplete?: () => void;
  onTfrRefreshComplete?: () => void;
}) {
  const [status, setStatus] = useState<{ airspace?: string; airspaceChecked?: string; tfr?: string } | null>(null);
  const [refreshing, setRefreshing] = useState<"airspace" | "tfr" | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  const applyStatus = useCallback((d: AirspaceStatusResponse) => {
    const airspaceTs = latestIso(d.sources?.class?.last_fetched_at, d.sources?.sua?.last_fetched_at);
    const airspaceCheckedTs = latestIso(d.sources?.class?.last_checked_at, d.sources?.sua?.last_checked_at);
    const tfrTs = d.sources?.tfr?.last_fetched_at;
    setStatus({
      airspace: formatAirspaceTimestamp(airspaceTs),
      airspaceChecked: formatAirspaceTimestamp(airspaceCheckedTs),
      tfr: formatAirspaceTimestamp(tfrTs),
    });
  }, []);

  const loadStatus = useCallback(async () => {
    const api = resolveApiBase();
    const response = await fetch(`${api}/api/faa-airspace/status`);
    if (!response.ok) throw new Error(`Airspace status failed: ${response.status}`);
    const payload = await response.json() as AirspaceStatusResponse;
    applyStatus(payload);
    return payload;
  }, [applyStatus]);

  useEffect(() => {
    void loadStatus().catch(() => {});
  }, [loadStatus]);

  async function handleRefresh(target: "airspace" | "tfr", sources: string, force: boolean) {
    const api = resolveApiBase();
    setRefreshing(target);
    setRefreshError(null);
    try {
      const params = new URLSearchParams({ sources, force: String(force) });
      const response = await fetch(`${api}/api/faa-airspace/refresh?${params}`, { method: "POST" });
      if (!response.ok) {
        throw new Error(`Airspace refresh failed: ${response.status}`);
      }
      let payload = await response.json() as AirspaceStatusResponse;

      applyStatus(payload);

      for (let attempt = 0; payload.manual_refresh?.in_progress && attempt < AIRSPACE_REFRESH_MAX_POLLS; attempt += 1) {
        await sleep(AIRSPACE_REFRESH_POLL_MS);
        payload = await loadStatus();
      }

      if (payload.manual_refresh?.in_progress) {
        setRefreshError("Refresh is still running. Check again shortly.");
        return;
      }

      const failedSources = failedAirspaceSources(payload);
      if (target === "airspace") {
        onAirspaceRefreshComplete?.();
      } else {
        onTfrRefreshComplete?.();
      }

      if (failedSources.length > 0) {
        setRefreshError(`Refresh failed for ${failedSources.join(", ")}`);
      }
    } catch (caught) {
      setRefreshError(caught instanceof Error ? caught.message : "Refresh failed");
      void loadStatus().catch(() => {});
    } finally {
      setRefreshing(null);
    }
  }

  if (!status) return null;
  return (
    <span className="airspace-freshness">
      <span className="airspace-status-stack">
        <span>Airspace: {status.airspace}</span>
        <span className="airspace-checked-label">Last checked: {status.airspaceChecked}</span>
      </span>
      <button
        type="button"
        className="airspace-refresh-button"
        onClick={() => void handleRefresh("airspace", "class,sua,tfr", false)}
        disabled={refreshing !== null}
        title="Check FAA airspace and TFR data, then update stale sources"
        aria-label="Check FAA airspace and TFR data"
      >
        <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M13 3v4H9" />
          <path d="M12.1 7A4.7 4.7 0 1 0 10 12.4" />
        </svg>
        {refreshing === "airspace" ? "Checking" : "Check"}
      </button>
      <span className="airspace-status-separator" aria-hidden="true">|</span>
      <span>TFRs: {status.tfr}</span>
      <button
        type="button"
        className="airspace-refresh-button"
        onClick={() => void handleRefresh("tfr", "tfr", true)}
        disabled={refreshing !== null}
        title="Refresh TFR data"
        aria-label="Refresh TFR data"
      >
        <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M13 3v4H9" />
          <path d="M12.1 7A4.7 4.7 0 1 0 10 12.4" />
        </svg>
        {refreshing === "tfr" ? "Refreshing" : "Refresh"}
      </button>
      <AirspaceTfrTimeSlider selectedTime={selectedTfrTime} onTimeChange={onTfrTimeChange} />
      {refreshError ? <span className="airspace-refresh-error">{refreshError}</span> : null}
    </span>
  );
}

const TOKEN_KEY = "flightcomp-platform-token";
const REFRESH_TOKEN_KEY = "flightcomp-platform-refresh-token";
const SIDEBAR_COMPACT_KEY = "flightcomp-platform-sidebar-compact";
const LAST_EVENT_KEY = "flightcomp-platform-last-event-id";
const ACTIVE_SECTION_KEY = "flightcomp-platform-active-section";
const SESSION_COOKIE = "flightcomp_session";
const DEFAULT_MESSAGE = "Use admin / admin1234 or pilot-demo / pilot1234 after the backend seed runs.";
type SidebarItem = { id: SidebarSection; label: string; description?: string };

const adminSidebarItems = [
  { id: "events", label: "Events / Challenges" },
  { id: "tasks", label: "Tasks" },
  { id: "scoring", label: "Scores" },
  { id: "live_tracking", label: "Live Tracking" },
  { id: "drivers", label: "Drivers" },
  { id: "logbook", label: "Logbook" },
  { id: "weather", label: "Weather" },
  { id: "airspace", label: "Airspace" },
  { id: "sos", label: "SOS Alerts" },
  { id: "settings", label: "Settings" },
  { id: "admin", label: "Admin" },
  { id: "live_backtest", label: "Live Backtest" },
] satisfies SidebarItem[];
const organizerSidebarItems = [
  { id: "events", label: "Events / Challenges" },
  { id: "tasks", label: "Tasks" },
  { id: "scoring", label: "Scores" },
  { id: "live_tracking", label: "Live Tracking" },
  { id: "logbook", label: "Logbook" },
  { id: "sos", label: "SOS Alerts" },
  { id: "settings", label: "Settings" },
] satisfies SidebarItem[];
const pilotSidebarItems = [
  { id: "events", label: "Events / Challenges" },
  { id: "tasks", label: "Tasks" },
  { id: "scoring", label: "Scores" },
  { id: "live_tracking", label: "Live Tracking" },
  { id: "logbook", label: "Logbook" },
  { id: "settings", label: "Settings" },
] satisfies SidebarItem[];
const guestSidebarItems = [
  { id: "scoring", label: "Scores" },
  { id: "live_tracking", label: "Live Tracking" },
] satisfies SidebarItem[];

const adminSidebarItemIds = new Set<SidebarSection>(adminSidebarItems.map((item) => item.id));
const organizerSidebarItemIds = new Set<SidebarSection>(organizerSidebarItems.map((item) => item.id));
const pilotSidebarItemIds = new Set<SidebarSection>(pilotSidebarItems.map((item) => item.id));
const guestSidebarItemIds = new Set<SidebarSection>(guestSidebarItems.map((item) => item.id));

function sidebarItemsForRole(role: User["role"] | null): SidebarItem[] {
  if (role === "admin") return adminSidebarItems;
  if (role === "organizer") return organizerSidebarItems;
  if (role === "pilot") return pilotSidebarItems;
  return guestSidebarItems;
}

function normalizeSectionForRole(section: string | null, role: User["role"] | null): SidebarSection {
  const allowedSections =
    role === "admin"
      ? adminSidebarItemIds
      : role === "organizer"
        ? organizerSidebarItemIds
        : role === "pilot"
          ? pilotSidebarItemIds
          : guestSidebarItemIds;
  if (section && allowedSections.has(section as SidebarSection)) {
    return section as SidebarSection;
  }
  if (role === "pilot") return "events";
  if (role === null) return "scoring";
  return "events";
}

const taskTypeOptions = [
  { value: "race_to_goal_with_gates", label: "Race to Goal" },
  { value: "elapsed_time", label: "Elapsed Time" },
  { value: "open_distance", label: "Open Distance" },
] as const;
const meterFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

function nextDraftEventName(events: EventRecord[]) {
  const existingNames = new Set(events.map((event) => event.name.trim().toLowerCase()));
  if (!existingNames.has("new event")) {
    return "New event";
  }
  let suffix = 2;
  while (existingNames.has(`new event ${suffix}`)) {
    suffix += 1;
  }
  return `New event ${suffix}`;
}

function blankTaskDraft(overrides: Partial<TaskDraftState> = {}): TaskDraftState {
  return {
    id: null,
    name: "New Task",
    task_date: "",
    is_practice: false,
    task_type: "race_to_goal_with_gates",
    task_start_time: "",
    task_finish_time: "",
    start_open_time: "",
    start_close_time: "",
    start_gate_count: 5,
    start_gate_interval_minutes: 15,
    nominal_distance_km: 60,
    nominal_time_hours: 1.5,
    nominal_launch: 0.95,
    minimum_distance_km: 5,
    penalties_text: "{}",
    points: [],
    ...overrides,
  };
}

function blankSettingsForm(): AccountSettingsRecord {
  return {
    username: "",
    full_name: "",
    role: "pilot",
    profile_type: "pilot",
    profile_type_updated_at: new Date(0).toISOString(),
    altitude_unit: "ft",
    speed_unit: "kph",
    distance_unit: "km",
    vario_unit: "fpm",
    aircraft_icon: "hang_glider",
    email: "",
    first_name: "",
    last_name: "",
    nation: "",
    competition_number: "",
    civl_id: "",
    pilot_id: null,
    has_password: false,
    challenge_settings_json: {},
  };
}

function blankSiteSettingsForm(): SiteSettingsRecord {
  return {
    telemetry_vario_smoothing_seconds: 5,
    telemetry_altitude_smoothing_seconds: 3,
    telemetry_speed_smoothing_seconds: 3,
    telemetry_glide_ratio_smoothing_seconds: 5,
    max_map_pitch_degrees: 75,
    site_match_radius_m: 1000,
    live_position_pruning_enabled: true,
    mqtt_enabled: false,
    mqtt_broker_mode: "local_mosquitto",
    mqtt_host: null,
    mqtt_port: 1883,
    mqtt_tls_enabled: false,
    mqtt_username: null,
    mqtt_password: null,
    mqtt_topic_prefix: "msh",
    mqtt_channel_psk: null,
    cloudflare_ddns_enabled: false,
    cloudflare_ddns_zone_id: null,
    cloudflare_ddns_api_token_configured: false,
    cloudflare_ddns_api_token: null,
    cloudflare_ddns_clear_api_token: false,
    cloudflare_ddns_record_names: ["mqtt.aervyx.net", "mqtt-staging.aervyx.net"],
    cloudflare_ddns_check_interval_hours: 12,
    cloudflare_ddns_last_checked_at: null,
    cloudflare_ddns_last_public_ip: null,
    cloudflare_ddns_last_update_result: null,
    cloudflare_ddns_last_error: null,
    mesh_profiles: null,
    updated_at: null,
  };
}

function normalizeIdentityEmail(value: string): string {
  return value.trim().toLowerCase();
}

function normalizeTaskType(value: string | null | undefined): string {
  switch (value) {
    case undefined:
    case null:
    case "race":
    case "race_to_goal":
      return "race_to_goal_with_gates";
    case "speedrun":
      return "elapsed_time";
    case "speedrun_interval":
      return "race_to_goal_with_gates";
    default:
      return value;
  }
}

function defaultTaskPointDirection(pointType: string): "enter" | "exit" {
  return pointType.toLowerCase() === "start" ? "exit" : "enter";
}

function defaultTaskPointRadius(pointType: string): number | null {
  switch (pointType.toLowerCase()) {
    case "start":
      return 5000;
    case "turnpoint":
      return 1000;
    case "goal":
      return 400;
    default:
      return null;
  }
}

function normalizeTaskPoint(point: TaskPointRecord): TaskPointRecord {
  return {
    ...point,
    direction: point.direction === "exit" || point.direction === "enter" ? point.direction : defaultTaskPointDirection(point.point_type),
  };
}

function normalizeTaskPointsForMode(points: TaskPointRecord[], advanced: boolean): TaskPointRecord[] {
  const lastPointIndex = points.length - 1;
  return points.map((point, pointIndex) => {
    const pointType = advanced ? point.point_type : toSimplePointType(point.point_type);
    let nextPointType = pointType;
    if (!advanced && pointIndex === 0) {
      nextPointType = "start";
    } else if (!advanced && pointIndex === lastPointIndex && points.length > 1) {
      nextPointType = "goal";
    } else if (!advanced && (pointType === "goal" || pointType === "start")) {
      nextPointType = "turnpoint";
    }
    const pointTypeChanged = nextPointType !== point.point_type;
    return normalizeTaskPoint({
      ...point,
      position: pointIndex + 1,
      point_type: nextPointType,
      direction: pointTypeChanged ? defaultTaskPointDirection(nextPointType) : point.direction,
      radius_m: pointTypeChanged ? defaultTaskPointRadius(nextPointType) ?? point.radius_m : point.radius_m,
    });
  });
}

function taskDraftFromEvent(event: EventRecord | null | undefined): TaskDraftState {
  return blankTaskDraft({
    start_gate_count: event?.default_start_gate_count ?? 5,
    start_gate_interval_minutes: event?.default_start_gate_interval_seconds == null ? 15 : event.default_start_gate_interval_seconds / 60,
    nominal_distance_km: event?.nominal_distance_km ?? 60,
    nominal_time_hours: event?.nominal_time_hours ?? 1.5,
    nominal_launch: event?.nominal_launch ?? 0.95,
    minimum_distance_km: event?.minimum_distance_km ?? 5,
    penalties_text: JSON.stringify(event?.penalties_json ?? {}, null, 2),
  });
}

function formatMeters(value: number): string {
  return meterFormatter.format(Math.max(0, Math.round(value || 0)));
}

function formatTaskClockLabel(value: string | null | undefined): string {
  if (!value) return "-";
  const trimmed = value.trim();
  const match = trimmed.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (!match) return value;
  const hours24 = Number(match[1]);
  const minutes = match[2];
  const suffix = hours24 >= 12 ? "PM" : "AM";
  const hours12 = hours24 % 12 || 12;
  return `${hours12}:${minutes} ${suffix}`;
}

function isAdvancedPointType(pointType: string): boolean {
  return pointType === "launch" || pointType === "ESS";
}

function toSimplePointType(pointType: string): string {
  if (pointType === "launch") return "start";
  if (pointType === "ESS") return "goal";
  return pointType;
}

function pointTypeOptionsForMode(mode: TaskPointMode): Array<{ value: string; label: string }> {
  return mode === "advanced"
    ? [
        { value: "launch", label: "Launch" },
        { value: "start", label: "Start" },
        { value: "turnpoint", label: "Turnpoint" },
        { value: "ESS", label: "ESS" },
        { value: "goal", label: "Goal" },
      ]
    : [
        { value: "start", label: "Start" },
        { value: "turnpoint", label: "Turnpoint" },
        { value: "goal", label: "Goal" },
      ];
}

function sanitizeMeterInput(rawValue: string): string {
  return rawValue.replace(/[^\d]/g, "").replace(/^0+(?=\d)/, "");
}

function taskPointInputKey(point: TaskPointRecord, index: number): string {
  return `${point.id ?? point.turnpoint_id ?? point.name}-${index}`;
}

function normalizeTimeValue(value: string | null | undefined): string {
  if (!value) return "";
  const trimmed = value.trim();
  if (/^\d{2}:\d{2}:\d{2}$/.test(trimmed)) {
    return trimmed.slice(0, 5);
  }
  return trimmed;
}

function timeOrNull(value: string): string | null {
  return value.trim() ? value : null;
}

function taskTypeBehavior(taskType: string) {
  switch (taskType) {
    case "race":
    case "race_to_goal":
    case "race_to_goal_with_gates":
      return { usesStartWindow: true, usesMultipleGates: true };
    case "elapsed_time":
    case "open_distance":
    default:
      return { usesStartWindow: false, usesMultipleGates: false };
  }
}

function eventToForm(event: EventRecord | null | undefined): EventFormState {
  return event
    ? {
        name: event.name,
        location: event.location,
        starts_on: event.starts_on,
        ends_on: event.ends_on,
        timezone: event.timezone,
        scoring_formula: event.scoring_formula,
        nominal_distance_km: event.nominal_distance_km,
        nominal_time_hours: event.nominal_time_hours,
        nominal_launch: event.nominal_launch,
        minimum_distance_km: event.minimum_distance_km,
        nominal_goal_percent: event.nominal_goal_percent,
        score_back_time_minutes: event.score_back_time_minutes,
        goal_ss_penalty: event.goal_ss_penalty,
        day_quality_override: event.day_quality_override,
        time_points_if_not_in_goal: event.time_points_if_not_in_goal,
        jump_the_gun_factor: event.jump_the_gun_factor,
        jump_the_gun_max_seconds: event.jump_the_gun_max_seconds,
        default_start_gate_count: event.default_start_gate_count ?? 5,
        default_start_gate_interval_seconds: event.default_start_gate_interval_seconds ?? 900,
        stopped_glide_bonus: event.stopped_glide_bonus,
        use_1000_points_for_max_day_quality: event.use_1000_points_for_max_day_quality,
        normalize_1000_before_day_quality: event.normalize_1000_before_day_quality,
        use_distance_points: event.use_distance_points,
        use_time_points: event.use_time_points,
        use_leading_points: event.use_leading_points,
        use_arrival_position_points: event.use_arrival_position_points,
        use_arrival_time_points: event.use_arrival_time_points,
        use_departure_points: event.use_departure_points,
        use_difficulty_for_distance_points: event.use_difficulty_for_distance_points,
        use_distance_squared_for_lc: event.use_distance_squared_for_lc,
        use_semi_circle_control_zone_for_goal_line: event.use_semi_circle_control_zone_for_goal_line,
        use_proportional_leading_weight_if_nobody_in_goal: event.use_proportional_leading_weight_if_nobody_in_goal,
        redistribute_removed_time_points_as_distance_points: event.redistribute_removed_time_points_as_distance_points,
        use_best_score_for_ftv_validity: event.use_best_score_for_ftv_validity,
        use_constant_leading_weight: event.use_constant_leading_weight,
        use_pwca2019_for_lc: event.use_pwca2019_for_lc,
        use_flat_decline_of_timepoints: event.use_flat_decline_of_timepoints,
        scoring_altitude: event.scoring_altitude,
        final_glide_decelerator: event.final_glide_decelerator,
        no_final_glide_decelerator_reason: event.no_final_glide_decelerator_reason,
        min_time_span_for_valid_task_minutes: event.min_time_span_for_valid_task_minutes,
        leading_weight_factor: event.leading_weight_factor,
        turnpoint_radius_tolerance: event.turnpoint_radius_tolerance,
        turnpoint_radius_minimum_absolute_tolerance_m: event.turnpoint_radius_minimum_absolute_tolerance_m,
        number_of_decimals_task_results: event.number_of_decimals_task_results,
        number_of_decimals_competition_results: event.number_of_decimals_competition_results,
        visible_airspace_classes_json: event.visible_airspace_classes_json,
        show_restricted_fields: event.show_restricted_fields,
        penalties_text: JSON.stringify(event.penalties_json ?? {}, null, 2),
        is_public_tracking: event.is_public_tracking ?? false,
        visibility: event.visibility ?? "private",
        event_kind: event.event_kind ?? "competition",
        owner_user_id: event.owner_user_id ?? null,
        source_buddy_group_id: event.source_buddy_group_id ?? null,
        public_slug: event.public_slug ?? null,
        public_listed: event.public_listed ?? true,
      }
    : blankEventForm();
}

function sortEventsByUpdatedAt(eventList: EventRecord[]): EventRecord[] {
  return [...eventList].sort((left, right) => {
    const leftTime = Date.parse(left.updated_at || "") || 0;
    const rightTime = Date.parse(right.updated_at || "") || 0;
    if (leftTime !== rightTime) return rightTime - leftTime;
    return left.name.localeCompare(right.name);
  });
}

let _refreshPromise: Promise<string> | null = null;

async function tryRefreshToken(): Promise<string | null> {
  const refreshToken = window.localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) return null;
  try {
    const response = await fetch(`${resolveApiBase()}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    });
    if (!response.ok) return null;
    const data = (await response.json()) as { access_token: string; refresh_token?: string };
    window.localStorage.setItem(TOKEN_KEY, data.access_token);
    if (data.refresh_token) window.localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
    return data.access_token;
  } catch {
    return null;
  }
}

async function apiFetch<T>(
  path: string,
  token: string,
  init: RequestInit = {},
  onResponse?: (response: Response) => void,
): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (response.status === 401) {
    // Try to refresh the access token once
    if (!_refreshPromise) _refreshPromise = tryRefreshToken().then((t) => { _refreshPromise = null; return t ?? ""; });
    const newToken = await _refreshPromise;
    if (newToken) {
      const retryHeaders = new Headers(init.headers ?? {});
      retryHeaders.set("Authorization", `Bearer ${newToken}`);
      if (!(init.body instanceof FormData) && !retryHeaders.has("Content-Type")) retryHeaders.set("Content-Type", "application/json");
      const retryResponse = await fetch(`${resolveApiBase()}${path}`, { ...init, headers: retryHeaders, cache: "no-store" });
      if (!retryResponse.ok) throw new Error((await retryResponse.text()) || `Request failed: ${retryResponse.status}`);
      onResponse?.(retryResponse);
      if (retryResponse.status === 204) return undefined as T;
      const text = await retryResponse.text();
      return (text ? JSON.parse(text) : undefined) as T;
    }
  }
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`);
  onResponse?.(response);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

function parseContentDispositionFilename(disposition: string | null): string | null {
  if (!disposition) return null;
  // Prefer RFC 5987 encoded filename* (supports non-ASCII + reserved chars like "#")
  // e.g. `attachment; filename*=UTF-8''Charles-2026-04-05-%231.igc`
  const extMatch = disposition.match(/filename\*=(?:([\w-]+)'[^']*')?([^;]+)/i);
  if (extMatch && extMatch[2]) {
    const raw = extMatch[2].trim().replace(/^"|"$/g, "");
    try {
      return decodeURIComponent(raw);
    } catch {
      return raw;
    }
  }
  // Fallback to plain `filename="..."` / `filename=...`
  const plain = disposition.match(/filename=("([^"\\]*(?:\\.[^"\\]*)*)"|([^;]+))/i);
  if (plain) {
    return (plain[2] ?? plain[3] ?? "").trim();
  }
  return null;
}

async function apiFetchBlob(path: string, token: string, init: RequestInit = {}): Promise<{ blob: Blob; filename: string | null }> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`);
  const filename = parseContentDispositionFilename(response.headers.get("content-disposition"));
  return { blob: await response.blob(), filename };
}

function logbookImportFileKey(file: File) {
  const relativePath = "webkitRelativePath" in file && typeof file.webkitRelativePath === "string" && file.webkitRelativePath.trim()
    ? file.webkitRelativePath.trim()
    : file.name;
  return `${relativePath}::${file.size}::${file.lastModified}`;
}

async function apiFetchPublic<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export default function HomePage() {
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [activeSection, setActiveSection] = useState<SidebarSection>("events");
  const [airspaceRefreshToken, setAirspaceRefreshToken] = useState(0);
  const [tfrRefreshToken, setTfrRefreshToken] = useState(0);
  const [selectedTfrTime, setSelectedTfrTime] = useState(() => buildTfrTimeSteps()[0]);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [eventEditorId, setEventEditorId] = useState<number | null>(null);
  const [eventTab, setEventTabRaw] = useState<EventTab>(() => {
    if (typeof window !== "undefined") {
      const saved = window.localStorage.getItem("aervyx-event-tab");
      if (saved && ["details", "turnpoints", "airspace", "participants", "scoring"].includes(saved)) {
        return saved as EventTab;
      }
    }
    return "details";
  });
  const setEventTab = (tab: EventTab) => {
    setEventTabRaw(tab);
    window.localStorage.setItem("aervyx-event-tab", tab);
    setMessage("");
    setError("");
  };
  const [pilots, setPilots] = useState<PilotRecord[]>([]);
  const [pilotDirectory, setPilotDirectory] = useState<PilotRecord[]>([]);
  const [turnpoints, setTurnpoints] = useState<TurnpointRecord[]>([]);
  const [turnpointSources, setTurnpointSources] = useState<TurnpointSourceRecord[]>([]);
  const [airspaces, setAirspaces] = useState<MapAirspaceRegion[]>([]);
  const [airspaceSources, setAirspaceSources] = useState<AirspaceSourceRecord[]>([]);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [results, setResults] = useState<ResultRecord[]>([]);
  const [pilotSummary, setPilotSummary] = useState<PilotSummaryRecord[]>([]);
  const [taskResultSummary, setTaskResultSummary] = useState<TaskResultSummaryRecord[]>([]);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [track, setTrack] = useState<TrackCollection | null>(null);
  const [selectedResultUploadIds, setSelectedResultUploadIds] = useState<number[]>([]);
  const [resultTracksByUploadId, setResultTracksByUploadId] = useState<Record<number, TrackCollection>>({});
  const [highlightedResultUploadId, setHighlightedResultUploadId] = useState<number | null>(null);
  const [pilotSummaryEventId, setPilotSummaryEventId] = useState<number | null>(null);
  const [scoringDataTaskId, setScoringDataTaskId] = useState<number | null>(null);
  const [message, setMessageRaw] = useState(DEFAULT_MESSAGE);
  const [error, setErrorRaw] = useState("");
  const messageTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const errorTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const setMessage = useCallback((text: string) => {
    if (messageTimer.current) clearTimeout(messageTimer.current);
    setMessageRaw(text);
    if (text && text !== DEFAULT_MESSAGE) {
      messageTimer.current = setTimeout(() => setMessageRaw(""), 4000);
    }
  }, []);
  const setError = useCallback((text: string) => {
    if (errorTimer.current) clearTimeout(errorTimer.current);
    setErrorRaw(text);
    if (text) {
      errorTimer.current = setTimeout(() => setErrorRaw(""), 6000);
    }
  }, []);
  const [authChecking, setAuthChecking] = useState(true);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [eventForm, setEventForm] = useState(blankEventForm());
    const [pilotForm, setPilotForm] = useState({ first_name: "", last_name: "", email: "", nation: "", competition_number: "", civl_id: "" });
    const [taskDraft, setTaskDraft] = useState<TaskDraftState>(blankTaskDraft());
  const [radiusDrafts, setRadiusDrafts] = useState<Record<string, string>>({});
  const [turnpointSearch, setTurnpointSearch] = useState("");
  const [taskPointAdvanced, setTaskPointAdvanced] = useState(false);
  const [scoringFeedback, setScoringFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [eventFormFeedback, setEventFormFeedback] = useState<Record<"details" | "scoring" | "airspace", { type: "success" | "error"; text: string } | null>>({
    details: null,
    scoring: null,
    airspace: null,
  });
  const [taskFeedback, setTaskFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [uploadFeedback, setUploadFeedback] = useState<{ type: "success" | "error" | "pending"; text: string } | null>(null);
  const [resultsDownloadFeedback, setResultsDownloadFeedback] = useState<{
    type: "success" | "error" | "pending";
    text: string;
    uploadId: number | null;
    all: boolean;
  } | null>(null);
  const [sidebarCompact, setSidebarCompact] = useState(false);
  const [authPanelOpen, setAuthPanelOpen] = useState(false);
  const [scoresPortalTab, setScoresPortalTab] = useState<ScoresPortalTab>("results");
  const [scoringTab, setScoringTab] = useState<ScoringTab>("task");
  const [adminUploadPilotId, setAdminUploadPilotId] = useState<number | null>(null);
  const [settingsForm, setSettingsForm] = useState<AccountSettingsRecord>(blankSettingsForm());
  const [settingsPasswordForm, setSettingsPasswordForm] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [settingsFeedback, setSettingsFeedback] = useState<{
    profile: { type: "success" | "error"; text: string } | null;
    password: { type: "success" | "error"; text: string } | null;
  }>({ profile: null, password: null });
  const [adminUsers, setAdminUsers] = useState<AdminUserRecord[]>([]);
  const [adminFeedback, setAdminFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [adminSites, setAdminSites] = useState<AdminSiteRecord[]>([]);
  const [adminSitesFeedback, setAdminSitesFeedback] = useState<{ type: "success" | "error" | "pending"; text: string } | null>(null);
  const [siteSettings, setSiteSettings] = useState<SiteSettingsRecord>(blankSiteSettingsForm());
  const [siteSettingsFeedback, setSiteSettingsFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [mapOverlayConfig, setMapOverlayConfig] = useState<MapOverlayConfigRecord>({ config: {} });
  const [mapOverlayConfigFeedback, setMapOverlayConfigFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [debugStatus, setDebugStatus] = useState<DebugStatusResponse | null>(null);
  const [logbookFlights, setLogbookFlights] = useState<LogbookFlightSummaryRecord[]>([]);
  const [logbookLoading, setLogbookLoading] = useState(false);
  const [logbookFeedback, setLogbookFeedback] = useState<{ type: "success" | "error" | "pending"; text: string } | null>(null);
  const [logbookDetailFlight, setLogbookDetailFlight] = useState<LogbookFlightDetailRecord | null>(null);
  const [logbookDetailLoading, setLogbookDetailLoading] = useState(false);
  const [logbookReplayFlight, setLogbookReplayFlight] = useState<LogbookFlightSummaryRecord | null>(null);
  const [logbookReplayTrack, setLogbookReplayTrack] = useState<TrackCollection | null>(null);
  const [logbookReplayLoading, setLogbookReplayLoading] = useState(false);
  const resultTrackPalette = useMemo(() => ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#d97706", "#0891b2", "#db2777", "#65a30d"], []);
  const taskFeedbackTimeoutRef = useRef<number | null>(null);

  const selectedEvent = useMemo(() => events.find((event) => event.id === selectedEventId) ?? null, [events, selectedEventId]);
    const selectedTask = useMemo(() => tasks.find((task) => task.id === selectedTaskId) ?? null, [tasks, selectedTaskId]);
    const taskDistanceMetrics = useMemo(() => computeTaskOptimization(taskDraft.points), [taskDraft.points]);
    const currentTaskTypeBehavior = useMemo(() => taskTypeBehavior(taskDraft.task_type), [taskDraft.task_type]);
    const taskPointMode: TaskPointMode = taskPointAdvanced ? "advanced" : "simple";
    const taskPointTypeOptions = useMemo(() => pointTypeOptionsForMode(taskPointMode), [taskPointMode]);
    const availableDirectoryPilots = useMemo(
      () => pilotDirectory.filter((candidate) => !pilots.some((pilot) => pilot.id === candidate.id)),
      [pilotDirectory, pilots],
    );
  const pilotById = useMemo(() => new Map(pilots.map((pilot) => [pilot.id, pilot])), [pilots]);
  const pilotNameById = useMemo(() => new Map(pilots.map((pilot) => [pilot.id, `${pilot.first_name} ${pilot.last_name}`.trim()])), [pilots]);
  const uploadById = useMemo(() => new Map(uploads.map((upload) => [upload.id, upload])), [uploads]);
  const trackableResults = useMemo(
    () => results.filter((result): result is ResultRecord & { upload_id: number } => result.upload_id != null),
    [results],
  );
  const resultByUploadId = useMemo(
    () => new Map(trackableResults.map((result) => [result.upload_id, result])),
    [trackableResults],
  );
  const resultTrackColorsByUploadId = useMemo(() => {
    const colorMap = new Map<number, string>();
    trackableResults.forEach((result, index) => {
      colorMap.set(result.upload_id, resultTrackPalette[index % resultTrackPalette.length]);
    });
    return colorMap;
  }, [resultTrackPalette, trackableResults]);
  const filteredTurnpoints = useMemo(() => {
      const query = turnpointSearch.trim().toLowerCase();
      if (!query) return [];
      if (query.includes("*")) return turnpoints;
      return turnpoints
        .filter((turnpoint) => {
          const haystack = `${turnpoint.name} ${turnpoint.code ?? ""}`.toLowerCase();
          return haystack.includes(query);
        })
        .slice(0, 12);
  }, [turnpointSearch, turnpoints]);
  const resultsTrackOverlay = useMemo<TrackCollection | null>(() => {
    if (!selectedResultUploadIds.length) {
      return null;
    }
    const features = selectedResultUploadIds.flatMap((uploadId) => {
      const collection = resultTracksByUploadId[uploadId];
      if (!collection) {
        return [];
      }
      const upload = uploadById.get(uploadId);
      const result = resultByUploadId.get(uploadId);
      const color = resultTrackColorsByUploadId.get(uploadId) ?? resultTrackPalette[0];
      return collection.features.map((feature) => {
        const featurePilotName = typeof feature.properties?.pilot_name === "string" ? feature.properties.pilot_name.trim() : "";
        const uploadPilotName = upload ? (pilotNameById.get(upload.pilot_id) ?? "").trim() : "";
        const pilotName = result?.pilot_name.trim()
          || featurePilotName
          || uploadPilotName
          || (upload ? `Pilot ${upload.pilot_id}` : `Pilot ${uploadId}`);
        return {
          ...feature,
            properties: {
              ...feature.properties,
              color,
              pilot_name: pilotName,
              upload_id: uploadId,
              line_style: "solid",
              track_kind: "igc",
            },
          };
      });
    });
    return { type: "FeatureCollection", features };
  }, [pilotNameById, resultByUploadId, resultTrackColorsByUploadId, resultTrackPalette, resultTracksByUploadId, selectedResultUploadIds, uploadById]);
  const allResultTrackIds = useMemo(() => trackableResults.map((result) => result.upload_id), [trackableResults]);
  const allResultTracksChecked = useMemo(
    () => allResultTrackIds.length > 0 && allResultTrackIds.every((uploadId) => selectedResultUploadIds.includes(uploadId)),
    [allResultTrackIds, selectedResultUploadIds],
  );
  const taskDefinitionRows = useMemo(() => {
    let cumulativeDistance = 0;
    return taskDraft.points.map((point, index) => {
      if (index > 0) {
        cumulativeDistance += taskDistanceMetrics.legMetrics[index - 1]?.optimizedDistanceKm ?? 0;
      }
      const sourceTurnpoint = turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id);
      const pointType = point.point_type.toLowerCase();
      const suffix = pointType === "launch" || pointType === "start"
        ? "SS"
        : pointType === "ess" || pointType === "goal"
          ? "ES"
          : "";
      return {
        label: `${index + 1}${suffix ? ` ${suffix}` : ""}`,
        legDistanceKm: cumulativeDistance,
        identifier: sourceTurnpoint?.code || point.name,
        radiusLabel: `${formatMeters(point.radius_m)} m`,
        openLabel: formatTaskClockLabel((currentTaskTypeBehavior.usesStartWindow ? taskDraft.start_open_time : taskDraft.task_start_time) || taskDraft.task_start_time || "-"),
        closeLabel: formatTaskClockLabel(taskDraft.start_close_time || taskDraft.task_finish_time || "-"),
      };
    });
  }, [currentTaskTypeBehavior.usesStartWindow, taskDistanceMetrics.legMetrics, taskDraft.points, taskDraft.start_open_time, taskDraft.start_close_time, taskDraft.task_finish_time, taskDraft.task_start_time, turnpoints]);
  const startGateLabels = useMemo(() => {
    if (!currentTaskTypeBehavior.usesMultipleGates || !taskDraft.start_open_time || !taskDraft.start_gate_count || taskDraft.start_gate_interval_minutes === "") {
      return [];
    }
    const [hoursText, minutesText] = taskDraft.start_open_time.split(":");
    const baseMinutes = Number(hoursText) * 60 + Number(minutesText);
    return Array.from({ length: taskDraft.start_gate_count }, (_, index) => {
      const totalMinutes = baseMinutes + index * Number(taskDraft.start_gate_interval_minutes || 0);
      const hours = Math.floor(totalMinutes / 60) % 24;
      const minutes = totalMinutes % 60;
      return formatTaskClockLabel(`${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`);
    });
  }, [currentTaskTypeBehavior.usesMultipleGates, taskDraft.start_gate_count, taskDraft.start_gate_interval_minutes, taskDraft.start_open_time]);
  const visibleAirspaces = useMemo(() => {
    const enabled = new Set<string>(eventForm.visible_airspace_classes_json ?? []);
    const enabledSourceIds = new Set(airspaceSources.filter((source) => source.enabled ?? true).map((source) => source.id));
    return airspaces.filter((region) => {
      if (!enabledSourceIds.has(region.source_id)) {
        return false;
      }
      if (region.is_restricted_field) {
        return eventForm.show_restricted_fields;
      }
      return enabled.has(region.display_category);
    });
  }, [airspaces, airspaceSources, eventForm.show_restricted_fields, eventForm.visible_airspace_classes_json]);
  const taskResultsColumns = useMemo(() => {
    const columns: Array<{ key: "distance" | "speed" | "arrival" | "departure" | "leading"; label: string }> = [];
    if (eventForm.use_distance_points) columns.push({ key: "distance", label: "Dist. Points" });
    if (eventForm.use_leading_points) columns.push({ key: "leading", label: "Leading Points" });
    if (eventForm.use_time_points) columns.push({ key: "speed", label: "Time Points" });
    if (eventForm.use_arrival_position_points || eventForm.use_arrival_time_points) columns.push({ key: "arrival", label: "Arrival Points" });
    if (eventForm.use_departure_points) columns.push({ key: "departure", label: "Departure Points" });
    return columns;
  }, [
    eventForm.use_arrival_position_points,
    eventForm.use_arrival_time_points,
    eventForm.use_departure_points,
    eventForm.use_distance_points,
    eventForm.use_leading_points,
    eventForm.use_time_points,
  ]);
  const scoredTasks = useMemo(
    () => sortTasksByDateAsc(tasks.filter((task) => pilotSummary.some((summary) => summary.task_scores[String(task.id)] != null))),
    [tasks, pilotSummary],
  );
  const taskMetricsById = useMemo(() => new Map(tasks.map((task) => [task.id, computeTaskOptimization(task.points)])), [tasks]);
  const isAdmin = user?.role === "admin";
  const canManagePlatform = user?.role === "admin" || user?.role === "organizer";
  const canManageCurrentEvent = Boolean(
    canManagePlatform ||
    (user && selectedEvent?.event_kind === "challenge" && selectedEvent.owner_user_id === user.id),
  );

  function showTaskFeedback(feedback: { type: "success" | "error"; text: string }) {
    setTaskFeedback(feedback);
    if (taskFeedbackTimeoutRef.current !== null) {
      window.clearTimeout(taskFeedbackTimeoutRef.current);
    }
    taskFeedbackTimeoutRef.current = window.setTimeout(() => {
      setTaskFeedback((current) => (current?.type === feedback.type && current?.text === feedback.text ? null : current));
      taskFeedbackTimeoutRef.current = null;
    }, 2000);
  }

  useEffect(() => {
    return () => {
      if (taskFeedbackTimeoutRef.current !== null) {
        window.clearTimeout(taskFeedbackTimeoutRef.current);
      }
    };
  }, []);
  const resultsTaskMapTurnpoints = useMemo<MapTurnpoint[]>(
    () =>
      taskDraft.points.map((point, index) => ({
        id: point.turnpoint_id ?? -(index + 1),
        name: point.name,
        code: turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code ?? null,
        latitude: point.latitude,
        longitude: point.longitude,
      })),
    [taskDraft.points, turnpoints],
  );
  const taskSectionMapTurnpoints = useMemo<MapTurnpoint[]>(
    () => (
      canManagePlatform
        ? turnpoints
        : taskDraft.points.map((point, index) => ({
            id: point.turnpoint_id ?? -(index + 1),
            name: point.name,
            code: turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code ?? null,
            latitude: point.latitude,
            longitude: point.longitude,
          }))
    ),
    [canManagePlatform, taskDraft.points, turnpoints],
  );
  const sidebarItems = sidebarItemsForRole(user?.role ?? null);

  useEffect(() => {
    const savedToken = window.localStorage.getItem(TOKEN_KEY);
    setSidebarCompact(window.localStorage.getItem(SIDEBAR_COMPACT_KEY) === "true");
    if (!savedToken) {
      setAuthChecking(false);
      window.location.replace("/login?next=/dashboard");
      return;
    }

    void bootstrap(savedToken)
      .catch(async () => {
        // Try refreshing before redirecting to login
        const newToken = await tryRefreshToken();
        if (newToken) {
          try {
            await bootstrap(newToken);
            setToken(newToken);
            return;
          } catch { /* fall through to logout */ }
        }
        window.localStorage.removeItem(TOKEN_KEY);
        window.localStorage.removeItem(REFRESH_TOKEN_KEY);
        document.cookie = `${SESSION_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
        setToken("");
        setUser(null);
        setError("");
        window.location.replace("/login?next=/dashboard");
      })
      .finally(() => setAuthChecking(false));
  }, []);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COMPACT_KEY, String(sidebarCompact));
  }, [sidebarCompact]);

  useEffect(() => {
    if (!user) return;
    window.localStorage.setItem(ACTIVE_SECTION_KEY, activeSection);
  }, [activeSection, user]);

  useEffect(() => {
    if (!user) return;
    const normalizedSection = normalizeSectionForRole(activeSection, user.role);
    if (normalizedSection !== activeSection) {
      setActiveSection(normalizedSection);
    }
  }, [activeSection, user]);

  useEffect(() => {
    if (!canManagePlatform) {
      setAdminUploadPilotId(null);
      return;
    }
    if (!pilots.length) {
      setAdminUploadPilotId(null);
      return;
    }
    if (adminUploadPilotId && pilots.some((pilot) => pilot.id === adminUploadPilotId)) {
      return;
    }
    setAdminUploadPilotId(pilots[0].id);
  }, [adminUploadPilotId, canManagePlatform, pilots]);

  useEffect(() => {
    if (!token || activeSection !== "scoring" || !selectedTaskId || scoringDataTaskId === selectedTaskId) {
      return;
    }
    const selectedTask = tasks.find((task) => task.id === selectedTaskId);
    void loadTask(token, selectedTaskId, selectedTask, true).catch((caught) => {
      setScoringFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not load task scoring data." });
    });
  }, [activeSection, scoringDataTaskId, selectedTaskId, tasks, token]);

  useEffect(() => {
    if (!token || activeSection !== "scoring" || !selectedEventId || pilotSummaryEventId === selectedEventId) {
      return;
    }
    void refreshPilotSummary(token, selectedEventId).catch((caught) => {
      setScoringFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not load overall results." });
    });
  }, [activeSection, pilotSummaryEventId, selectedEventId, token]);

  useEffect(() => {
    if (!token || activeSection !== "logbook") {
      return;
    }
    void refreshLogbookFlights(token).catch((caught) => {
      setLogbookFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not load the logbook." });
    });
  }, [activeSection, token]);

  async function bootstrap(activeToken: string) {
    document.cookie = `${SESSION_COOKIE}=1; Path=/; Max-Age=2592000; SameSite=Lax`;
    setToken(activeToken);
    setError("");
    const [me, rawEvents, settings, loadedSiteSettings, loadedLogbookFlights, loadedMapOverlayConfig] = await Promise.all([
      apiFetch<User>("/api/auth/me", activeToken),
      apiFetch<EventRecord[]>("/api/events", activeToken),
      apiFetch<AccountSettingsRecord>("/api/auth/settings", activeToken),
      apiFetch<SiteSettingsRecord>("/api/site-settings", activeToken),
      apiFetch<LogbookFlightSummaryRecord[]>("/api/logbook/flights", activeToken),
      apiFetch<MapOverlayConfigRecord>("/api/map-overlay-config", activeToken).catch(() => ({ config: {} }) as MapOverlayConfigRecord),
    ]);
    const loadedEvents = sortEventsByUpdatedAt(rawEvents);
    const storedEventId = Number(window.localStorage.getItem(LAST_EVENT_KEY) ?? "");
    const storedSection = window.localStorage.getItem(ACTIVE_SECTION_KEY);
    const normalizedSection = normalizeSectionForRole(storedSection, me.role);
    const preferredEvent = loadedEvents.find((event) => event.id === storedEventId) ?? loadedEvents[0] ?? null;
    setUser(me);
    setSettingsForm(settings);
    setSiteSettings(loadedSiteSettings);
    setMapOverlayConfig(loadedMapOverlayConfig);
    setLogbookFlights(loadedLogbookFlights);
    setActiveSection(normalizedSection);
    setEvents(loadedEvents);
    void refreshPilotDirectory(activeToken, me);
    void refreshAdminUsers(activeToken, me);
    void refreshAdminSites(activeToken, me);
    if (preferredEvent) {
      window.localStorage.setItem(LAST_EVENT_KEY, String(preferredEvent.id));
      setSelectedEventId(preferredEvent.id);
      setEventEditorId(preferredEvent.id);
      setEventForm(eventToForm(preferredEvent));
      void loadEvent(activeToken, preferredEvent.id, preferredEvent, me, undefined, normalizedSection).catch((caught) => {
        setError(caught instanceof Error ? caught.message : "Could not load the selected event.");
      });
    } else {
      setSelectedEventId(null);
      setEventEditorId(null);
      setEventForm(blankEventForm());
      setPilots([]);
      setTurnpoints([]);
      setTurnpointSources([]);
      setAirspaces([]);
      setAirspaceSources([]);
      setTasks([]);
      setPilotSummary([]);
      setTaskResultSummary([]);
      setResults([]);
      setUploads([]);
      setTrack(null);
      setSelectedResultUploadIds([]);
      setResultTracksByUploadId({});
      setRadiusDrafts({});
      setTaskDraft(taskDraftFromEvent(null));
    }
  }

  async function refreshEvents(activeToken: string) {
    const loadedEvents = sortEventsByUpdatedAt(await apiFetch<EventRecord[]>("/api/events", activeToken));
    setEvents(loadedEvents);
    return loadedEvents;
  }

  async function refreshPilotSummary(activeToken: string, eventId: number) {
    const [loadedSummary, loadedTaskSummary] = await Promise.all([
      apiFetch<PilotSummaryRecord[]>(`/api/events/${eventId}/pilot-summary`, activeToken),
      apiFetch<TaskResultSummaryRecord[]>(`/api/events/${eventId}/task-result-summary`, activeToken),
    ]);
    setPilotSummary(loadedSummary);
    setTaskResultSummary(loadedTaskSummary);
    setPilotSummaryEventId(eventId);
    return loadedSummary;
  }

  async function refreshPilotDirectory(activeToken: string, activeUser?: User | null) {
    if (!["admin", "organizer"].includes((activeUser ?? user)?.role ?? "")) {
      setPilotDirectory([]);
      return [];
    }
    const loadedPilots = await apiFetch<PilotRecord[]>("/api/pilots", activeToken);
    setPilotDirectory(loadedPilots);
    return loadedPilots;
  }

  async function refreshAdminUsers(activeToken: string, activeUser?: User | null) {
    if ((activeUser ?? user)?.role !== "admin") {
      setAdminUsers([]);
      return [];
    }
    const loadedUsers = await apiFetch<AdminUserRecord[]>("/api/auth/users", activeToken);
    setAdminUsers(loadedUsers);
    return loadedUsers;
  }

  async function refreshAdminSites(activeToken: string, activeUser?: User | null) {
    if ((activeUser ?? user)?.role !== "admin") {
      setAdminSites([]);
      return [];
    }
    const loadedSites = await apiFetch<AdminSiteRecord[]>("/api/admin/sites", activeToken);
    setAdminSites(loadedSites);
    return loadedSites;
  }

  async function refreshSiteSettings(activeToken: string) {
    const loadedSettings = await apiFetch<SiteSettingsRecord>("/api/site-settings", activeToken);
    setSiteSettings(loadedSettings);
    return loadedSettings;
  }

  async function refreshLogbookFlights(activeToken: string) {
    setLogbookLoading(true);
    try {
      const loadedFlights = await apiFetch<LogbookFlightSummaryRecord[]>("/api/logbook/flights", activeToken);
      setLogbookFlights(loadedFlights);
      return loadedFlights;
    } finally {
      setLogbookLoading(false);
    }
  }

  async function createManualLogbookFlight(form: LogbookFlightFormRecord) {
    if (!token) return;
    setLogbookFeedback({ type: "pending", text: "Saving manual flight..." });
    try {
      await apiFetch<LogbookFlightDetailRecord>("/api/logbook/flights", token, {
        method: "POST",
        body: JSON.stringify({
          flight_date: form.flight_date,
          site_name: form.site_name,
          duration_seconds: form.duration_seconds.trim() ? Number(form.duration_seconds) : null,
          highest_altitude_m: form.highest_altitude_m.trim() ? Number(form.highest_altitude_m) : null,
          best_climb_mps: form.best_climb_mps.trim() ? Number(form.best_climb_mps) : null,
          notes: form.notes.trim() || null,
        }),
      });
      await refreshLogbookFlights(token);
      setLogbookFeedback({ type: "success", text: `Saved manual flight for ${form.site_name || "the logbook"}.` });
    } catch (caught) {
      setLogbookFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not save that flight." });
      throw caught;
    }
  }

  async function uploadLogbookFlight(file: File) {
    if (!token) return;
    setLogbookFeedback({ type: "pending", text: `Uploading ${file.name} into the logbook...` });
    try {
      const formData = new FormData();
      formData.append("file", file);
      await apiFetch<LogbookFlightDetailRecord>("/api/logbook/flights/upload", token, {
        method: "POST",
        body: formData,
      });
      await refreshLogbookFlights(token);
      setLogbookFeedback({ type: "success", text: `Uploaded ${file.name} into your logbook.` });
    } catch (caught) {
      setLogbookFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not upload that IGC file." });
    }
  }

  async function scanLogbookFolderFlights(files: File[], confirmedFileKeys: string[] = []) {
    if (!token) {
      return { imported: [], skipped: [], review_needed: [] } satisfies LogbookFolderImportResultRecord;
    }
    const igcFiles = files.filter((file) => file.name.toLowerCase().endsWith(".igc"));
    if (!igcFiles.length) {
      const emptyResult = { imported: [], skipped: [], review_needed: [] } satisfies LogbookFolderImportResultRecord;
      setLogbookFeedback({ type: "error", text: "No IGC files were found in that folder selection." });
      return emptyResult;
    }
    setLogbookFeedback({ type: "pending", text: `Scanning ${igcFiles.length} IGC file${igcFiles.length === 1 ? "" : "s"} from the selected folder...` });
    try {
      const formData = new FormData();
      const relativePaths = igcFiles.map((file) => ("webkitRelativePath" in file && file.webkitRelativePath ? file.webkitRelativePath : file.name));
      const fileKeys = igcFiles.map((file) => logbookImportFileKey(file));
      igcFiles.forEach((file) => formData.append("files", file, file.name));
      formData.append("relative_paths_json", JSON.stringify(relativePaths));
      formData.append("file_keys_json", JSON.stringify(fileKeys));
      if (confirmedFileKeys.length) {
        formData.append("confirmed_file_keys_json", JSON.stringify(confirmedFileKeys));
      }
      const result = await apiFetch<LogbookFolderImportResultRecord>("/api/logbook/flights/import-folder", token, {
        method: "POST",
        body: formData,
      });
      await refreshLogbookFlights(token);
      const summaryText = [
        result.imported.length ? `${result.imported.length} imported` : null,
        result.review_needed.length ? `${result.review_needed.length} need review` : null,
        result.skipped.length ? `${result.skipped.length} skipped` : null,
      ].filter(Boolean).join(" - ");
      setLogbookFeedback({
        type: result.review_needed.length ? "pending" : "success",
        text: summaryText ? `Folder scan complete: ${summaryText}.` : "Folder scan complete.",
      });
      return result;
    } catch (caught) {
      setLogbookFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not scan that folder." });
      throw caught;
    }
  }

  async function attachLogbookFlightFile(flight: LogbookFlightSummaryRecord, file: File) {
    if (!token) return;
    const flightLabel = flight.site_name || flight.filename || "that flight";
    setLogbookFeedback({ type: "pending", text: `Attaching ${file.name} to ${flightLabel}...` });
    try {
      const formData = new FormData();
      formData.append("file", file);
      const updated = await apiFetch<LogbookFlightDetailRecord>(`/api/logbook/flights/${flight.id}/upload`, token, {
        method: "POST",
        body: formData,
      });
      if (logbookDetailFlight?.id === flight.id) {
        setLogbookDetailFlight(updated);
      }
      if (logbookReplayFlight?.id === flight.id) {
        setLogbookReplayFlight(updated);
      }
      await refreshLogbookFlights(token);
      setLogbookFeedback({ type: "success", text: `Attached ${file.name} to ${flightLabel}.` });
    } catch (caught) {
      setLogbookFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not attach that IGC file." });
      throw caught;
    }
  }

  async function openLogbookFlightDetail(flightId: number) {
    if (!token) return;
    setLogbookDetailLoading(true);
    setLogbookDetailFlight(null);
    try {
      const detail = await apiFetch<LogbookFlightDetailRecord>(`/api/logbook/flights/${flightId}`, token);
      setLogbookDetailFlight(detail);
    } catch (caught) {
      setLogbookFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not load that flight." });
    } finally {
      setLogbookDetailLoading(false);
    }
  }

  function closeLogbookFlightDetail() {
    setLogbookDetailLoading(false);
    setLogbookDetailFlight(null);
  }

  async function openLogbookFlightReplay(flight: LogbookFlightSummaryRecord) {
    if (!token) return;
    setLogbookReplayFlight(flight);
    setLogbookReplayTrack(null);
    setLogbookReplayLoading(true);
    try {
      const trackCollection = await apiFetch<TrackCollection>(`/api/logbook/flights/${flight.id}/track`, token);
      setLogbookReplayTrack(trackCollection);
    } catch (caught) {
      setLogbookFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not load that flight replay." });
      setLogbookReplayFlight(null);
    } finally {
      setLogbookReplayLoading(false);
    }
  }

  function closeLogbookFlightReplay() {
    setLogbookReplayLoading(false);
    setLogbookReplayFlight(null);
    setLogbookReplayTrack(null);
  }

  async function downloadLogbookFlight(flightId: number) {
    if (!token) return;
    try {
      const { blob, filename } = await apiFetchBlob(`/api/logbook/flights/${flightId}/download`, token);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename ?? `flight-${flightId}.igc`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setLogbookFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not download that IGC file." });
    }
  }

  async function deleteLogbookFlight(flight: LogbookFlightSummaryRecord) {
    if (!token) return;
    const flightLabel = flight.filename ?? flight.site_name ?? "that flight";
    setLogbookFeedback({ type: "pending", text: `Deleting ${flightLabel}...` });
    try {
      await apiFetch<void>(`/api/logbook/flights/${flight.id}`, token, { method: "DELETE" });
      if (logbookDetailFlight?.id === flight.id) {
        setLogbookDetailFlight(null);
        setLogbookDetailLoading(false);
      }
      if (logbookReplayFlight?.id === flight.id) {
        setLogbookReplayFlight(null);
        setLogbookReplayTrack(null);
        setLogbookReplayLoading(false);
      }
      await refreshLogbookFlights(token);
      setLogbookFeedback({ type: "success", text: `Deleted ${flight.filename ?? "that flight"} from the logbook.` });
    } catch (caught) {
      setLogbookFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not delete that flight." });
    }
  }

  async function bulkDeleteLogbookFlights(flightsToDelete: LogbookFlightSummaryRecord[]) {
    if (!token || !flightsToDelete.length) return;
    const selectedIds = flightsToDelete.map((flight) => flight.id);
    setLogbookFeedback({
      type: "pending",
      text: `Deleting ${selectedIds.length} selected flight${selectedIds.length === 1 ? "" : "s"}...`,
    });
    try {
      const result = await apiFetch<LogbookBulkDeleteResponseRecord>("/api/logbook/flights", token, {
        method: "DELETE",
        body: JSON.stringify({ flight_ids: selectedIds }),
      });
      const deletedIdSet = new Set(result.deleted_ids);
      if (logbookDetailFlight && deletedIdSet.has(logbookDetailFlight.id)) {
        setLogbookDetailFlight(null);
        setLogbookDetailLoading(false);
      }
      if (logbookReplayFlight && deletedIdSet.has(logbookReplayFlight.id)) {
        setLogbookReplayFlight(null);
        setLogbookReplayTrack(null);
        setLogbookReplayLoading(false);
      }
      await refreshLogbookFlights(token);
      setLogbookFeedback({
        type: "success",
        text: `Deleted ${result.deleted_count} selected flight${result.deleted_count === 1 ? "" : "s"} from the logbook.`,
      });
    } catch (caught) {
      setLogbookFeedback({
        type: "error",
        text: caught instanceof Error ? caught.message : "Could not delete the selected flights.",
      });
      throw caught;
    }
  }

  async function saveLogbookFlightNotes(flightId: number, notes: string) {
    if (!token) return;
    setLogbookFeedback({ type: "pending", text: "Saving flight notes..." });
    try {
      const updated = await apiFetch<LogbookFlightDetailRecord>(`/api/logbook/flights/${flightId}`, token, {
        method: "PATCH",
        body: JSON.stringify({ notes }),
      });
      setLogbookDetailFlight(updated);
      await refreshLogbookFlights(token);
      setLogbookFeedback({ type: "success", text: "Saved flight notes." });
    } catch (caught) {
      setLogbookFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not save flight notes." });
      throw caught;
    }
  }

  async function updateLogbookFlightSite(flightId: number, siteName: string) {
    if (!token) return;
    setLogbookFeedback({ type: "pending", text: "Saving site..." });
    try {
      const updated = await apiFetch<LogbookFlightDetailRecord>(`/api/logbook/flights/${flightId}`, token, {
        method: "PATCH",
        body: JSON.stringify({ site_name: siteName }),
      });
      setLogbookDetailFlight(updated);
      await refreshLogbookFlights(token);
      setLogbookFeedback({ type: "success", text: `Site updated to "${updated.site_name}".` });
    } catch (caught) {
      setLogbookFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not update the site." });
      throw caught;
    }
  }

  async function setLogbookFlightStar(flight: LogbookFlightSummaryRecord, starred: boolean) {
    if (!token) return;
    const flightLabel = flight.site_name || flight.filename || "that flight";
    setLogbookFlights((current) =>
      current.map((entry) => (entry.id === flight.id ? { ...entry, starred } : entry)),
    );
    if (logbookReplayFlight?.id === flight.id) {
      setLogbookReplayFlight({ ...logbookReplayFlight, starred });
    }
    if (logbookDetailFlight?.id === flight.id) {
      setLogbookDetailFlight({ ...logbookDetailFlight, starred });
    }
    try {
      const updated = await apiFetch<LogbookFlightDetailRecord>(`/api/logbook/flights/${flight.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({ starred }),
      });
      setLogbookFlights((current) =>
        current.map((entry) => (entry.id === flight.id ? { ...entry, ...updated } : entry)),
      );
      if (logbookDetailFlight?.id === flight.id) {
        setLogbookDetailFlight(updated);
      }
      if (logbookReplayFlight?.id === flight.id) {
        setLogbookReplayFlight(updated);
      }
      setLogbookFeedback({ type: "success", text: `${starred ? "Starred" : "Unstarred"} ${flightLabel}.` });
    } catch (caught) {
      setLogbookFlights((current) =>
        current.map((entry) => (entry.id === flight.id ? { ...entry, starred: flight.starred } : entry)),
      );
      if (logbookReplayFlight?.id === flight.id) {
        setLogbookReplayFlight({ ...flight, starred: flight.starred });
      }
      if (logbookDetailFlight?.id === flight.id) {
        setLogbookDetailFlight({ ...logbookDetailFlight, starred: flight.starred });
      }
      setLogbookFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not update that flight." });
      throw caught;
    }
  }

  async function loadEvent(
    activeToken: string,
    eventId: number,
    currentEvent?: EventRecord | null,
    activeUser?: User | null,
    preferredTaskId?: number | null,
    preferredSection?: SidebarSection,
  ) {
    setWorkspaceLoading(true);
    try {
      setSelectedEventId(eventId);
      window.localStorage.setItem(LAST_EVENT_KEY, String(eventId));
      const activeEvent = currentEvent ?? events.find((event) => event.id === eventId) ?? null;
      const targetSection = preferredSection ?? activeSection;
      setEventEditorId(eventId);
      setEventForm(eventToForm(activeEvent));
      const [loadedPilots, loadedTurnpoints, loadedTurnpointSources, loadedAirspaces, loadedAirspaceSources, loadedTasks] = await Promise.all([
        apiFetch<PilotRecord[]>(`/api/events/${eventId}/pilots`, activeToken),
        apiFetch<TurnpointRecord[]>(`/api/events/${eventId}/turnpoints`, activeToken),
        apiFetch<TurnpointSourceRecord[]>(`/api/events/${eventId}/turnpoint-sources`, activeToken),
        apiFetch<MapAirspaceRegion[]>(`/api/events/${eventId}/airspaces`, activeToken),
        apiFetch<AirspaceSourceRecord[]>(`/api/events/${eventId}/airspace-sources`, activeToken),
        apiFetch<TaskRecord[]>(`/api/events/${eventId}/tasks`, activeToken),
      ]);
      const viewer = activeUser ?? user;
      const viewerCanManageLoadedEvent = Boolean(
        viewer?.role === "admin" ||
        viewer?.role === "organizer" ||
        (viewer && activeEvent?.event_kind === "challenge" && activeEvent.owner_user_id === viewer.id),
      );
      const visibleTasks = sortTasksByDateAsc(viewer?.role === "pilot" && !viewerCanManageLoadedEvent ? loadedTasks.filter((task) => task.status === "published") : loadedTasks);
      setPilots(loadedPilots);
      setTurnpoints(loadedTurnpoints);
      setTurnpointSources(loadedTurnpointSources);
      setAirspaces(loadedAirspaces);
      setAirspaceSources(loadedAirspaceSources);
      setTasks(visibleTasks);
      setPilotSummary([]);
      setTaskResultSummary([]);
      setPilotSummaryEventId(null);
      setTrack(null);
      setSelectedResultUploadIds([]);
      setResultTracksByUploadId({});
      setHighlightedResultUploadId(null);
      setScoringDataTaskId(null);
      setRadiusDrafts({});
      const nextTask = visibleTasks.find((task) => task.id === preferredTaskId)
        ?? visibleTasks.find((task) => task.id === selectedTaskId)
        ?? visibleTasks[0];
      if (nextTask) {
        await loadTask(activeToken, nextTask.id, nextTask, targetSection === "scoring");
      } else {
        setSelectedTaskId(null);
        setResults([]);
        setUploads([]);
        setTaskPointAdvanced(false);
        setScoringFeedback(null);
        setTaskFeedback(null);
        setEventFormFeedback({ details: null, scoring: null, airspace: null });
        setTaskDraft(taskDraftFromEvent(activeEvent));
      }
    } finally {
      setWorkspaceLoading(false);
    }
  }

  async function selectEvent(event: EventRecord) {
    if (!token) return;
    setEventEditorId(event.id);
    setEventForm(eventToForm(event));
    await loadEvent(token, event.id, event);
  }

  async function loadTask(activeToken: string, taskId: number, loadedTask?: TaskRecord, includeScoringData = true) {
    const task = loadedTask ?? (await apiFetch<TaskRecord>(`/api/tasks/${taskId}`, activeToken));
    const hasAdvancedTaskPoints = task.points.some((point) => isAdvancedPointType(point.point_type));
    setSelectedTaskId(taskId);
    setTrack(null);
    setSelectedResultUploadIds([]);
    setResultTracksByUploadId({});
    setHighlightedResultUploadId(null);
    setResultsDownloadFeedback(null);
    setRadiusDrafts({});
    setTaskPointAdvanced(hasAdvancedTaskPoints);
    setScoringFeedback(null);
    setTaskFeedback(null);
    setTaskDraft({
      id: task.id,
      name: task.name,
      task_date: task.task_date ?? "",
      is_practice: Boolean(task.is_practice),
      task_type: normalizeTaskType(task.task_type),
      task_start_time: normalizeTimeValue(task.task_start_time),
      task_finish_time: normalizeTimeValue(task.task_finish_time),
      start_open_time: normalizeTimeValue(task.start_open_time),
      start_close_time: normalizeTimeValue(task.start_close_time),
      start_gate_count: task.start_gate_count || 1,
      start_gate_interval_minutes: task.start_gate_interval_seconds == null ? "" : task.start_gate_interval_seconds / 60,
      nominal_distance_km: task.nominal_distance_km,
      nominal_time_hours: task.nominal_time_hours,
      nominal_launch: task.nominal_launch,
      minimum_distance_km: task.minimum_distance_km,
      penalties_text: JSON.stringify(task.penalties_json, null, 2),
      points: normalizeTaskPointsForMode(task.points, hasAdvancedTaskPoints),
    });
    if (!includeScoringData) {
      setResults([]);
      setUploads([]);
      setScoringDataTaskId(null);
      return;
    }
    const [loadedResults, loadedUploads] = await Promise.all([
      apiFetch<ResultRecord[]>(`/api/tasks/${taskId}/results`, activeToken),
      apiFetch<UploadRecord[]>(`/api/tasks/${taskId}/uploads`, activeToken),
    ]);
    setResults(loadedResults);
    setUploads(loadedUploads);
    setScoringDataTaskId(taskId);
  }

  function signOut() {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
    document.cookie = `${SESSION_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
    window.location.replace("/login");
  }

  async function saveAccountSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setSettingsFeedback((current) => ({ ...current, profile: null }));
    try {
      const payload = await apiFetch<AccountSettingsRecord>("/api/auth/settings", token, {
        method: "PATCH",
        body: JSON.stringify({
          username: normalizeIdentityEmail(settingsForm.username),
          full_name: settingsForm.full_name,
          profile_type: settingsForm.profile_type,
          altitude_unit: settingsForm.altitude_unit,
          speed_unit: settingsForm.speed_unit,
          distance_unit: settingsForm.distance_unit,
          vario_unit: settingsForm.vario_unit,
          aircraft_icon: settingsForm.aircraft_icon,
          email: normalizeIdentityEmail(settingsForm.username) || null,
          first_name: settingsForm.first_name || null,
          last_name: settingsForm.last_name || null,
          nation: settingsForm.nation || null,
          competition_number: settingsForm.competition_number || null,
          civl_id: settingsForm.civl_id || null,
          challenge_settings_json: settingsForm.challenge_settings_json,
        }),
      });
      setSettingsForm({
        username: payload.username,
        full_name: payload.full_name,
        role: payload.role,
        profile_type: payload.profile_type,
        profile_type_updated_at: payload.profile_type_updated_at,
        altitude_unit: payload.altitude_unit,
        speed_unit: payload.speed_unit,
        distance_unit: payload.distance_unit,
        vario_unit: payload.vario_unit,
        aircraft_icon: payload.aircraft_icon,
        email: payload.email,
        first_name: payload.first_name,
        last_name: payload.last_name,
        nation: payload.nation,
        competition_number: payload.competition_number,
        civl_id: payload.civl_id,
        pilot_id: payload.pilot_id ?? null,
        has_password: payload.has_password,
        access_token: payload.access_token,
        challenge_settings_json: payload.challenge_settings_json ?? {},
      });
      if (payload.access_token) {
        window.localStorage.setItem(TOKEN_KEY, payload.access_token);
        document.cookie = `${SESSION_COOKIE}=1; Path=/; Max-Age=2592000; SameSite=Lax`;
        setToken(payload.access_token);
      }
      setUser((current) => (current ? { ...current, username: payload.username, full_name: payload.full_name, role: payload.role, profile_type: payload.profile_type, profile_type_updated_at: payload.profile_type_updated_at } : current));
      setSettingsFeedback((current) => ({ ...current, profile: { type: "success", text: "Account settings saved." } }));
    } catch (caught) {
      setSettingsFeedback((current) => ({
        ...current,
        profile: { type: "error", text: caught instanceof Error ? caught.message : "Could not save account settings." },
      }));
    }
  }

  async function saveChallengeSettings(settings: Record<string, unknown>) {
    if (!token) return settings;
    const payload = await apiFetch<{ settings: Record<string, unknown> }>("/api/auth/challenge-settings", token, {
      method: "PATCH",
      body: JSON.stringify({ settings }),
    });
    setSettingsForm((current) => ({ ...current, challenge_settings_json: payload.settings ?? {} }));
    return payload.settings ?? {};
  }

  async function savePasswordSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setSettingsFeedback((current) => ({ ...current, password: null }));
    if (settingsPasswordForm.new_password.length < 8) {
      setSettingsFeedback((current) => ({ ...current, password: { type: "error", text: "New password must be at least 8 characters." } }));
      return;
    }
    if (settingsPasswordForm.new_password !== settingsPasswordForm.confirm_password) {
      setSettingsFeedback((current) => ({ ...current, password: { type: "error", text: "New password and confirmation do not match." } }));
      return;
    }
    try {
      await apiFetch<{ status: string }>("/api/auth/change-password", token, {
        method: "POST",
        body: JSON.stringify({
          current_password: settingsPasswordForm.current_password,
          new_password: settingsPasswordForm.new_password,
        }),
      });
      const wasFirstPassword = !settingsForm.has_password;
      setSettingsPasswordForm({ current_password: "", new_password: "", confirm_password: "" });
      if (wasFirstPassword) setSettingsForm((current) => ({ ...current, has_password: true }));
      setSettingsFeedback((current) => ({ ...current, password: { type: "success", text: wasFirstPassword ? "Password set successfully. You can now log in from the mobile app." : "Password updated successfully." } }));
    } catch (caught) {
      setSettingsFeedback((current) => ({
        ...current,
        password: { type: "error", text: caught instanceof Error ? caught.message : "Could not update password." },
      }));
    }
  }

  async function handlePilotClaimed() {
    if (!token) return;
    try {
      const settings = await apiFetch<AccountSettingsRecord>("/api/auth/settings", token);
      setSettingsForm(settings);
    } catch { /* ignore */ }
  }

  async function handleMeshDevicesChanged() {
    if (!token) return;
    await refreshAdminUsers(token);
  }

  async function saveAdminUser(userRecord: AdminUserRecord) {
    if (!token) return;
    setAdminFeedback(null);
    try {
      const payload = await apiFetch<AdminUserRecord>(`/api/auth/users/${userRecord.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({
          role: userRecord.role,
          profile_type: userRecord.profile_type,
          is_active: userRecord.is_active,
        }),
      });
      setAdminUsers((current) => current.map((entry) => (entry.id === payload.id ? payload : entry)));
      setAdminFeedback({ type: "success", text: `Updated ${payload.full_name}.` });
    } catch (caught) {
      setAdminFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not update that user." });
    }
  }

  async function clearAdminUserDevice(userId: number) {
    if (!token) return;
    setAdminFeedback(null);
    try {
      await apiFetch(`/api/auth/users/${userId}/mesh-device`, token, { method: "DELETE" });
      setAdminUsers((current) =>
        current.map((u) => (u.id === userId ? { ...u, mesh_device_id: null } : u))
      );
      setAdminFeedback({ type: "success", text: "Device pairing cleared." });
    } catch (caught) {
      setAdminFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not clear device." });
    }
  }

  async function updateUserCredentials(userId: number, payload: { username?: string; password?: string }) {
    if (!token) return;
    const updated = await apiFetch<AdminUserRecord>(`/api/auth/users/${userId}/credentials`, token, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    setAdminUsers((current) => current.map((entry) => (entry.id === updated.id ? updated : entry)));
    setAdminFeedback({ type: "success", text: `Updated credentials for ${updated.full_name || updated.username}.` });
  }

  async function saveSiteSettings() {
    if (!token) return;
    setSiteSettingsFeedback(null);
    try {
      const payload = await apiFetch<SiteSettingsRecord>("/api/site-settings", token, {
        method: "PATCH",
        body: JSON.stringify({
          telemetry_vario_smoothing_seconds: siteSettings.telemetry_vario_smoothing_seconds,
          telemetry_altitude_smoothing_seconds: siteSettings.telemetry_altitude_smoothing_seconds,
          telemetry_speed_smoothing_seconds: siteSettings.telemetry_speed_smoothing_seconds,
          telemetry_glide_ratio_smoothing_seconds: siteSettings.telemetry_glide_ratio_smoothing_seconds,
          max_map_pitch_degrees: siteSettings.max_map_pitch_degrees,
          site_match_radius_m: siteSettings.site_match_radius_m,
          live_position_pruning_enabled: siteSettings.live_position_pruning_enabled,
          mqtt_enabled: siteSettings.mqtt_enabled,
          mqtt_broker_mode: siteSettings.mqtt_broker_mode,
          mqtt_host: siteSettings.mqtt_host,
          mqtt_port: siteSettings.mqtt_port,
          mqtt_tls_enabled: siteSettings.mqtt_tls_enabled,
          mqtt_username: siteSettings.mqtt_username,
          mqtt_password: siteSettings.mqtt_password,
          mqtt_topic_prefix: siteSettings.mqtt_topic_prefix,
          mqtt_channel_psk: siteSettings.mqtt_channel_psk,
          cloudflare_ddns_enabled: siteSettings.cloudflare_ddns_enabled,
          cloudflare_ddns_zone_id: siteSettings.cloudflare_ddns_zone_id,
          cloudflare_ddns_api_token: siteSettings.cloudflare_ddns_api_token,
          cloudflare_ddns_clear_api_token: siteSettings.cloudflare_ddns_clear_api_token,
          cloudflare_ddns_record_names: siteSettings.cloudflare_ddns_record_names,
          cloudflare_ddns_check_interval_hours: siteSettings.cloudflare_ddns_check_interval_hours,
          mesh_profiles: siteSettings.mesh_profiles,
        }),
      });
      setSiteSettings(payload);
      setSiteSettingsFeedback({ type: "success", text: "Site settings saved." });
    } catch (caught) {
      setSiteSettingsFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not save site settings." });
    }
  }

  async function saveMapOverlayConfig() {
    if (!token) return;
    setMapOverlayConfigFeedback(null);
    try {
      const payload = await apiFetch<MapOverlayConfigRecord>("/api/map-overlay-config", token, {
        method: "PATCH",
        body: JSON.stringify({ config: mapOverlayConfig.config }),
      });
      setMapOverlayConfig(payload);
      setMapOverlayConfigFeedback({ type: "success", text: "Map overlay config saved." });
    } catch (caught) {
      setMapOverlayConfigFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not save map overlay config." });
    }
  }

  async function saveAdminSite(siteRecord: AdminSiteRecord) {
    if (!token) return;
    setAdminSitesFeedback({ type: "pending", text: `Saving ${siteRecord.name || "site"}...` });
    try {
      const payload = {
        name: siteRecord.name,
        city_state: siteRecord.city_state,
        latitude: siteRecord.latitude,
        longitude: siteRecord.longitude,
        is_active: siteRecord.is_active,
      };
      const saved = siteRecord.id < 0
        ? await apiFetch<AdminSiteRecord>("/api/admin/sites", token, {
            method: "POST",
            body: JSON.stringify(payload),
          })
        : await apiFetch<AdminSiteRecord>(`/api/admin/sites/${siteRecord.id}`, token, {
            method: "PATCH",
            body: JSON.stringify(payload),
          });
      setAdminSites((current) =>
        siteRecord.id < 0
          ? [...current.filter((entry) => entry.id !== siteRecord.id), saved].sort((a, b) => a.name.localeCompare(b.name))
          : current.map((entry) => (entry.id === saved.id ? saved : entry)),
      );
      setAdminSitesFeedback({ type: "success", text: `Saved ${saved.name}.` });
    } catch (caught) {
      setAdminSitesFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not save that site." });
    }
  }

  async function deleteAdminSite(siteRecord: AdminSiteRecord) {
    if (!token) return;
    setAdminSitesFeedback(null);
    try {
      await apiFetch<void>(`/api/admin/sites/${siteRecord.id}`, token, { method: "DELETE" });
      setAdminSites((current) => current.filter((entry) => entry.id !== siteRecord.id));
      setAdminSitesFeedback({ type: "success", text: `Deleted ${siteRecord.name}.` });
    } catch (caught) {
      setAdminSitesFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not delete that site." });
    }
  }

  async function rescanAdminFlightSites() {
    if (!token) return;
    setAdminSitesFeedback({ type: "pending", text: "Rescanning unmatched flights for site matches..." });
    try {
      const result = await apiFetch<AdminSiteRescanResultRecord>("/api/admin/sites/rescan-flights", token, {
        method: "POST",
      });
      await refreshLogbookFlights(token);
      setAdminSitesFeedback({
        type: "success",
        text: `Scanned ${result.scanned_count} flights, matched ${result.matched_count}, ${result.unmatched_count} still unmatched.`,
      });
    } catch (caught) {
      setAdminSitesFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not rescan flights for site matches." });
    }
  }

  async function scanIgcForNewSites() {
    if (!token) return;
    setAdminSitesFeedback({ type: "pending", text: "Scanning all IGC files for new takeoff sites..." });
    try {
      const result = await apiFetch<AdminSiteScanIgcResultRecord>("/api/admin/sites/scan-igc", token, {
        method: "POST",
      });
      if (result.sites.length) {
        setAdminSites((current) => [...current, ...result.sites]);
      }
      // Refresh existing sites to get updated flight counts
      const refreshed = await apiFetch<AdminSiteRecord[]>("/api/admin/sites", token);
      setAdminSites(refreshed);
      setAdminSitesFeedback({
        type: "success",
        text: `Scanned ${result.total_igc_scanned} IGC files. Created ${result.new_sites_created} new site${result.new_sites_created === 1 ? "" : "s"}, matched ${result.flights_matched} flights.`,
      });
    } catch (caught) {
      setAdminSitesFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not scan IGC files for new sites." });
    }
  }

  const refreshDebugStatus = useCallback(async (onResponse?: (response: Response) => void) => {
    if (!token) return;
    try {
      const data = await apiFetch<DebugStatusResponse>("/api/admin/debug/status", token, {}, onResponse);
      setDebugStatus(data);
    } catch {
      // silently ignore - the tab will show stale data or loading state
    }
  }, [token]);

  async function deleteAdminUser(userRecord: AdminUserRecord) {
    if (!token) return;
    setAdminFeedback(null);
    try {
      await apiFetch<void>(`/api/auth/users/${userRecord.id}`, token, { method: "DELETE" });
      setAdminUsers((current) => current.filter((entry) => entry.id !== userRecord.id));
      setAdminFeedback({ type: "success", text: `Deleted ${userRecord.full_name}.` });
    } catch (caught) {
      setAdminFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not delete that user." });
    }
  }

  async function persistEventForm(nextForm: EventFormState, successMessage?: string) {
    if (!token) return;
    let penaltiesJson: Record<string, unknown>;
    try {
      penaltiesJson = JSON.parse(nextForm.penalties_text || "{}") as Record<string, unknown>;
    } catch {
      setError("Scoring penalties must be valid JSON before saving the event.");
      return;
    }
    const payload = {
      name: nextForm.name,
      location: nextForm.location,
      starts_on: nextForm.starts_on,
      ends_on: nextForm.ends_on,
      timezone: nextForm.timezone,
      scoring_formula: nextForm.scoring_formula,
      nominal_distance_km: nextForm.nominal_distance_km,
      nominal_time_hours: nextForm.nominal_time_hours,
      nominal_launch: nextForm.nominal_launch,
      minimum_distance_km: nextForm.minimum_distance_km,
      nominal_goal_percent: nextForm.nominal_goal_percent,
      score_back_time_minutes: nextForm.score_back_time_minutes,
      goal_ss_penalty: nextForm.goal_ss_penalty,
      day_quality_override: nextForm.day_quality_override,
      time_points_if_not_in_goal: nextForm.time_points_if_not_in_goal,
      jump_the_gun_factor: nextForm.jump_the_gun_factor,
      jump_the_gun_max_seconds: nextForm.jump_the_gun_max_seconds,
      default_start_gate_count: nextForm.default_start_gate_count,
      default_start_gate_interval_seconds: nextForm.default_start_gate_interval_seconds,
      stopped_glide_bonus: nextForm.stopped_glide_bonus,
      use_1000_points_for_max_day_quality: nextForm.use_1000_points_for_max_day_quality,
      normalize_1000_before_day_quality: nextForm.normalize_1000_before_day_quality,
      use_distance_points: nextForm.use_distance_points,
      use_time_points: nextForm.use_time_points,
      use_leading_points: nextForm.use_leading_points,
      use_arrival_position_points: nextForm.use_arrival_position_points,
      use_arrival_time_points: nextForm.use_arrival_time_points,
      use_departure_points: nextForm.use_departure_points,
      use_difficulty_for_distance_points: nextForm.use_difficulty_for_distance_points,
      use_distance_squared_for_lc: nextForm.use_distance_squared_for_lc,
      use_semi_circle_control_zone_for_goal_line: nextForm.use_semi_circle_control_zone_for_goal_line,
      use_proportional_leading_weight_if_nobody_in_goal: nextForm.use_proportional_leading_weight_if_nobody_in_goal,
      redistribute_removed_time_points_as_distance_points: nextForm.redistribute_removed_time_points_as_distance_points,
      use_best_score_for_ftv_validity: nextForm.use_best_score_for_ftv_validity,
      use_constant_leading_weight: nextForm.use_constant_leading_weight,
      use_pwca2019_for_lc: nextForm.use_pwca2019_for_lc,
      use_flat_decline_of_timepoints: nextForm.use_flat_decline_of_timepoints,
      scoring_altitude: nextForm.scoring_altitude,
      final_glide_decelerator: nextForm.final_glide_decelerator,
      no_final_glide_decelerator_reason: nextForm.no_final_glide_decelerator_reason,
      min_time_span_for_valid_task_minutes: nextForm.min_time_span_for_valid_task_minutes,
      leading_weight_factor: nextForm.leading_weight_factor,
      turnpoint_radius_tolerance: nextForm.turnpoint_radius_tolerance,
      turnpoint_radius_minimum_absolute_tolerance_m: nextForm.turnpoint_radius_minimum_absolute_tolerance_m,
      number_of_decimals_task_results: nextForm.number_of_decimals_task_results,
      number_of_decimals_competition_results: nextForm.number_of_decimals_competition_results,
      visible_airspace_classes_json: nextForm.visible_airspace_classes_json,
      show_restricted_fields: nextForm.show_restricted_fields,
      penalties_json: penaltiesJson,
      is_public_tracking: nextForm.is_public_tracking,
      visibility: nextForm.visibility,
      event_kind: nextForm.event_kind,
      owner_user_id: nextForm.owner_user_id,
      source_buddy_group_id: nextForm.event_kind === "challenge" ? nextForm.source_buddy_group_id : null,
      public_slug: nextForm.public_slug,
      public_listed: nextForm.event_kind === "challenge" ? nextForm.public_listed : true,
    };
    const savedEvent = await apiFetch<EventRecord>(eventEditorId ? `/api/events/${eventEditorId}` : "/api/events", token, { method: eventEditorId ? "PUT" : "POST", body: JSON.stringify(payload) });
    const loadedEvents = await refreshEvents(token);
    const nextEvent = loadedEvents.find((candidate) => candidate.id === savedEvent.id) ?? savedEvent;
    setEventEditorId(nextEvent.id);
    setEventForm(eventToForm(nextEvent));
    window.localStorage.setItem(LAST_EVENT_KEY, String(nextEvent.id));
    setMessage(successMessage ?? `${eventEditorId ? "Updated" : "Created"} event ${savedEvent.name}.`);
    await loadEvent(token, nextEvent.id, nextEvent);
    if (!selectedTaskId) {
      setTaskDraft(taskDraftFromEvent(nextEvent));
    }
  }

  async function saveEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await persistEventForm(eventForm);
  }

  async function createEventDraft(kind: "competition" | "challenge") {
    if (!token) return;
    const isChallenge = kind === "challenge";
    const template = { ...blankEventForm(), event_kind: kind };
    const savedEvent = await apiFetch<EventRecord>("/api/events", token, {
      method: "POST",
      body: JSON.stringify({
        ...template,
        name: isChallenge ? "New challenge" : nextDraftEventName(events),
        penalties_json: {},
        public_listed: isChallenge,
      }),
    });
    const loadedEvents = await refreshEvents(token);
    const nextEvent = loadedEvents.find((candidate) => candidate.id === savedEvent.id) ?? savedEvent;
    setEventTab("details");
    setEventEditorId(nextEvent.id);
    setEventForm(eventToForm(nextEvent));
    window.localStorage.setItem(LAST_EVENT_KEY, String(nextEvent.id));
    setMessage(`Created ${isChallenge ? "challenge" : "event"} ${nextEvent.name}.`);
    await loadEvent(token, nextEvent.id, nextEvent);
  }

  async function duplicateSelectedEvent() {
    if (!token || !eventEditorId) return;
    const duplicatedEvent = await apiFetch<EventRecord>(`/api/events/${eventEditorId}/duplicate`, token, {
      method: "POST",
    });
    const loadedEvents = await refreshEvents(token);
    const nextEvent = loadedEvents.find((candidate) => candidate.id === duplicatedEvent.id) ?? duplicatedEvent;
    setEventTab("details");
    setEventEditorId(nextEvent.id);
    setEventForm(eventToForm(nextEvent));
    window.localStorage.setItem(LAST_EVENT_KEY, String(nextEvent.id));
    setMessage(`Duplicated event ${selectedEvent?.name ?? duplicatedEvent.name} into ${duplicatedEvent.name}.`);
    await loadEvent(token, nextEvent.id, nextEvent);
  }

  async function deleteEvent() {
    if (!token || !eventEditorId) return;
    const eventToDelete = events.find((event) => event.id === eventEditorId);
    const confirmed = window.confirm(`Delete event "${eventToDelete?.name ?? "this event"}"? This will remove its tasks, turnpoints, uploads, and scoring records.`);
    if (!confirmed) return;
    await apiFetch<void>(`/api/events/${eventEditorId}`, token, { method: "DELETE" });
    const loadedEvents = await refreshEvents(token);
    if (loadedEvents[0]) {
      const nextEvent = loadedEvents[0];
      setMessage(`Deleted event ${eventToDelete?.name ?? ""}.`);
      setEventEditorId(nextEvent.id);
      setEventForm(eventToForm(nextEvent));
      window.localStorage.setItem(LAST_EVENT_KEY, String(nextEvent.id));
      await loadEvent(token, nextEvent.id, nextEvent);
    } else {
      setMessage(`Deleted event ${eventToDelete?.name ?? ""}.`);
      setSelectedEventId(null);
      setEventEditorId(null);
      window.localStorage.removeItem(LAST_EVENT_KEY);
      setEventForm(blankEventForm());
      setPilots([]);
      setTurnpoints([]);
      setTurnpointSources([]);
      setAirspaces([]);
      setAirspaceSources([]);
      setTasks([]);
      setResults([]);
      setPilotSummary([]);
      setTaskResultSummary([]);
      setUploads([]);
      setTrack(null);
      setTaskPointAdvanced(false);
      setTaskDraft(taskDraftFromEvent(null));
    }
  }

  async function createPilot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedEventId) return;
    const payload = await apiFetch<PilotRecord>(`/api/events/${selectedEventId}/pilots`, token, { method: "POST", body: JSON.stringify(pilotForm) });
    setPilotForm({ first_name: "", last_name: "", email: "", nation: "", competition_number: "", civl_id: "" });
    setMessage(`Created pilot ${payload.first_name} ${payload.last_name}${payload.temp_password ? ` with temp password ${payload.temp_password}` : ""}.`);
    await loadEvent(token, selectedEventId);
    await refreshPilotDirectory(token);
    await refreshEvents(token);
  }

  async function assignExistingPilot(pilotId: number | null) {
    if (!token || !selectedEventId || !pilotId) return;
    const payload = await apiFetch<PilotRecord>(`/api/events/${selectedEventId}/pilots/${pilotId}/assign`, token, { method: "POST" });
    setMessage(`Added ${payload.first_name} ${payload.last_name} to ${selectedEvent?.name ?? "the event"}.`);
    await loadEvent(token, selectedEventId);
    await refreshPilotDirectory(token);
    await refreshEvents(token);
  }

  async function removePilot(pilot: PilotRecord) {
    if (!token || !selectedEventId) return;
    await apiFetch<void>(`/api/events/${selectedEventId}/pilots/${pilot.id}`, token, { method: "DELETE" });
    setMessage(`Removed ${pilot.first_name} ${pilot.last_name} from ${selectedEvent?.name ?? "the event"}.`);
    await loadEvent(token, selectedEventId);
    await refreshPilotDirectory(token);
    await refreshEvents(token);
  }

  async function updatePilot(pilotId: number, payload: { first_name: string; last_name: string; email: string; nation: string; competition_number: string; civl_id: string }) {
    if (!token) return;
    const body = {
      first_name: payload.first_name,
      last_name: payload.last_name,
      email: payload.email || null,
      nation: payload.nation || null,
      competition_number: payload.competition_number || null,
      civl_id: payload.civl_id || null,
    };
    const updated = await apiFetch<PilotRecord>(`/api/pilots/${pilotId}`, token, { method: "PUT", body: JSON.stringify(body) });
    setMessage(`Updated ${updated.first_name} ${updated.last_name}.`);
    if (selectedEventId) await loadEvent(token, selectedEventId);
    await refreshPilotDirectory(token);
  }

  async function uploadFile<T>(path: string, file: File): Promise<T> {
    if (!token) throw new Error("You must be signed in to upload files.");
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<T>(path, token, { method: "POST", body: formData });
  }

  async function toggleTurnpointSource(source: TurnpointSourceRecord, enabled: boolean) {
    if (!token || !selectedEventId) return;
    await apiFetch<TurnpointSourceRecord>(`/api/events/${selectedEventId}/turnpoint-sources/${source.id}`, token, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
    setMessage(`${enabled ? "Enabled" : "Hidden"} ${source.filename} on the event map.`);
    await loadEvent(token, selectedEventId, selectedEvent);
  }

  async function deleteTurnpointSource(source: TurnpointSourceRecord) {
    if (!token || !selectedEventId) return;
    const confirmed = window.confirm(`Delete ${source.filename}? This removes its imported waypoints from the database.`);
    if (!confirmed) return;
    await apiFetch<void>(`/api/events/${selectedEventId}/turnpoint-sources/${source.id}`, token, { method: "DELETE" });
    setMessage(`Deleted ${source.filename}.`);
    await loadEvent(token, selectedEventId, selectedEvent);
    await refreshEvents(token);
  }

  async function uploadAirspaceFile(files: FileList | File[]) {
    if (!selectedEventId) return;
    const uploadQueue = Array.from(files);
    if (!uploadQueue.length) return;

    let importedCount = 0;
    for (const file of uploadQueue) {
      const response = await uploadFile<AirspaceUploadResponse>(`/api/events/${selectedEventId}/airspaces/upload?kind=`, file);
      importedCount += response.imported_count;
    }

    const fileLabel = uploadQueue.length === 1 ? ` from ${uploadQueue[0].name}` : ` across ${uploadQueue.length} files`;
    setMessage(`Stored ${importedCount} overlays${fileLabel}. Choose labels in the table when you're ready.`);
    await loadEvent(token, selectedEventId, selectedEvent);
    await refreshEvents(token);
  }

  async function deleteAirspaceSource(source: AirspaceSourceRecord) {
    if (!token || !selectedEventId) return;
    const sourceLabel = source.kind === "restricted_field" ? "restricted fields" : source.kind === "airspace" ? "airspace overlays" : "overlays";
    const confirmed = window.confirm(`Delete ${source.filename}? This removes its ${sourceLabel} from the database.`);
    if (!confirmed) return;
    await apiFetch<void>(`/api/events/${selectedEventId}/airspace-sources/${source.id}`, token, { method: "DELETE" });
    setMessage(`Deleted ${source.filename}.`);
    await loadEvent(token, selectedEventId, selectedEvent);
    await refreshEvents(token);
  }

  async function updateAirspaceSource(source: AirspaceSourceRecord, updates: { enabled?: boolean; kind?: AirspaceSourceRecord["kind"] }) {
    if (!token || !selectedEventId) return;
    await apiFetch<AirspaceSourceRecord>(`/api/events/${selectedEventId}/airspace-sources/${source.id}`, token, {
      method: "PATCH",
      body: JSON.stringify(updates),
    });
    if (typeof updates.enabled === "boolean") {
      setMessage(`${updates.enabled ? "Enabled" : "Hidden"} ${source.filename} on the event map.`);
    } else if (updates.kind !== undefined) {
      const label = updates.kind === "restricted_field" ? "Restricted fields" : updates.kind === "airspace" ? "Airspace" : "No label";
      setMessage(`Updated ${source.filename} to ${label}.`);
    }
    await loadEvent(token, selectedEventId, selectedEvent);
  }

  function toggleVisibleAirspaceClass(category: AirspaceCategoryOption) {
    const existing = new Set(eventForm.visible_airspace_classes_json);
    if (existing.has(category)) {
      existing.delete(category);
    } else {
      existing.add(category);
    }
    setEventForm({ ...eventForm, visible_airspace_classes_json: Array.from(existing) });
  }

  function startNewTask() {
    const nextTaskNumber = tasks.length + 1;
    setSelectedTaskId(null);
    setTrack(null);
    setResults([]);
    setUploads([]);
    setTaskPointAdvanced(false);
    setScoringFeedback(null);
    setTaskFeedback(null);
    setRadiusDrafts({});
    setTaskDraft({
      ...taskDraftFromEvent(selectedEvent),
      name: `Task ${nextTaskNumber}`,
    });
    setMessage(`Started a new draft for ${selectedEvent?.name ?? "this event"}.`);
  }

  function duplicateTask() {
    if (!taskDraft.id) return;
    setSelectedTaskId(null);
    setTrack(null);
    setResults([]);
    setUploads([]);
    setScoringFeedback(null);
    setTaskFeedback(null);
    setRadiusDrafts({});
    setTaskDraft({
      ...taskDraft,
      id: null,
      name: `${taskDraft.name} (copy)`,
    });
    setMessage(`Created a copy of ${taskDraft.name}. Save to persist.`);
  }

  function addTurnpoint(turnpoint: MapTurnpoint) {
    setRadiusDrafts({});
    setTaskDraft((current) => {
      const pointType = current.points.length === 0 ? (taskPointAdvanced ? "launch" : "start") : "turnpoint";
      const mappedRadius = defaultTaskPointRadius(pointType);
      const points = [
        ...current.points,
        {
          position: current.points.length + 1,
          point_type: pointType,
          direction: defaultTaskPointDirection(pointType),
          radius_m: mappedRadius ?? (current.points.length === 0 ? 300 : 400),
          turnpoint_id: turnpoint.id,
          name: turnpoint.name,
          latitude: turnpoint.latitude,
          longitude: turnpoint.longitude,
        },
      ];
      return {
        ...current,
        points: normalizeTaskPointsForMode(points, taskPointAdvanced),
      };
    });
  }

  function updatePoint(index: number, patch: Partial<TaskPointRecord>) {
    setTaskDraft((current) => ({
      ...current,
      points: normalizeTaskPointsForMode(
        current.points.map((point, pointIndex) => {
          if (pointIndex !== index) return point;
          const nextPoint = { ...point, ...patch };
          if (patch.point_type && patch.point_type !== point.point_type) {
            nextPoint.direction = defaultTaskPointDirection(patch.point_type);
            nextPoint.radius_m = defaultTaskPointRadius(patch.point_type) ?? nextPoint.radius_m;
          }
          return normalizeTaskPoint(nextPoint);
        }),
        taskPointAdvanced,
      ),
    }));
  }

  function handleRadiusInputChange(index: number, point: TaskPointRecord, rawValue: string) {
    const key = taskPointInputKey(point, index);
    const sanitized = sanitizeMeterInput(rawValue);
    if (!sanitized) {
      setRadiusDrafts((current) => ({ ...current, [key]: "" }));
      return;
    }
    const nextRadius = Number(sanitized);
    updatePoint(index, { radius_m: nextRadius });
    setRadiusDrafts((current) => ({ ...current, [key]: formatMeters(nextRadius) }));
  }

  function handleRadiusInputBlur(index: number, point: TaskPointRecord) {
    const key = taskPointInputKey(point, index);
    const sanitized = sanitizeMeterInput(radiusDrafts[key] ?? "");
    if (!sanitized) {
      setRadiusDrafts((current) => {
        const next = { ...current };
        delete next[key];
        return next;
      });
      return;
    }
    const nextRadius = Number(sanitized);
    updatePoint(index, { radius_m: nextRadius });
    setRadiusDrafts((current) => ({ ...current, [key]: formatMeters(nextRadius) }));
  }

  function handleRadiusInputKeyDown(event: KeyboardEvent<HTMLInputElement>, index: number, point: TaskPointRecord) {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    const key = taskPointInputKey(point, index);
    const draftValue = sanitizeMeterInput(radiusDrafts[key] ?? "");
    const baseRadius = draftValue ? Number(draftValue) : Math.max(0, Math.round(point.radius_m || 0));
    const nextRadius = Math.max(0, baseRadius + (event.key === "ArrowUp" ? 100 : -100));
    updatePoint(index, { radius_m: nextRadius });
    setRadiusDrafts((current) => ({ ...current, [key]: formatMeters(nextRadius) }));
  }

  function radiusInputValue(index: number, point: TaskPointRecord) {
    return radiusDrafts[taskPointInputKey(point, index)] ?? formatMeters(point.radius_m);
  }

  function removePoint(index: number) {
    setRadiusDrafts({});
    setTaskDraft((current) => ({
      ...current,
      points: normalizeTaskPointsForMode(current.points.filter((_, pointIndex) => pointIndex !== index), taskPointAdvanced),
    }));
  }

  function movePoint(fromIndex: number, toIndex: number) {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) {
      return;
    }
    setRadiusDrafts({});
    setTaskDraft((current) => {
      const points = [...current.points];
      const [movedPoint] = points.splice(fromIndex, 1);
      points.splice(toIndex, 0, movedPoint);
      return { ...current, points: normalizeTaskPointsForMode(points, taskPointAdvanced) };
    });
  }

  async function saveTask() {
    if (!token || !selectedEventId) return;
    try {
      setTaskFeedback(null);
      const currentTaskStatus = taskDraft.id
        ? selectedTask?.status ?? tasks.find((task) => task.id === taskDraft.id)?.status ?? "draft"
        : "draft";
      const payload = {
        name: taskDraft.name,
        task_date: taskDraft.task_date || null,
        is_practice: taskDraft.is_practice,
        status: currentTaskStatus,
        task_type: taskDraft.task_type,
        task_start_time: timeOrNull(taskDraft.task_start_time),
        task_finish_time: timeOrNull(taskDraft.task_finish_time),
        start_open_time: currentTaskTypeBehavior.usesStartWindow ? timeOrNull(taskDraft.start_open_time) : null,
        start_close_time: timeOrNull(taskDraft.start_close_time),
        start_gate_count: taskDraft.start_gate_count,
        start_gate_interval_seconds: taskDraft.start_gate_interval_minutes === "" ? null : taskDraft.start_gate_interval_minutes * 60,
        nominal_distance_km: taskDraft.nominal_distance_km,
        nominal_time_hours: taskDraft.nominal_time_hours,
        nominal_launch: taskDraft.nominal_launch,
        minimum_distance_km: taskDraft.minimum_distance_km,
        penalties_json: JSON.parse(taskDraft.penalties_text || "{}"),
        points: normalizeTaskPointsForMode(taskDraft.points, taskPointAdvanced),
      };
      let savedTask: TaskRecord;
      if (taskDraft.id) {
        savedTask = await apiFetch<TaskRecord>(`/api/tasks/${taskDraft.id}`, token, { method: "PUT", body: JSON.stringify(payload) });
      } else {
        savedTask = await apiFetch<TaskRecord>(`/api/events/${selectedEventId}/tasks`, token, { method: "POST", body: JSON.stringify(payload) });
      }
      await loadEvent(token, selectedEventId, undefined, undefined, savedTask.id);
      await refreshEvents(token);
      setActiveSection("tasks");
      showTaskFeedback({ type: "success", text: `${taskDraft.id ? "Updated" : "Created"} task ${taskDraft.name}.` });
    } catch (caught) {
      showTaskFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Task save failed." });
    }
  }

  async function publishTask() {
    if (!token || !taskDraft.id) return;
    try {
      setTaskFeedback(null);
      const publishedTask = await apiFetch<TaskRecord>(`/api/tasks/${taskDraft.id}/publish`, token, { method: "POST" });
      setTaskFeedback({ type: "success", text: `Published task ${taskDraft.name}.` });
      if (selectedEventId) await loadEvent(token, selectedEventId, undefined, undefined, publishedTask.id);
    } catch (caught) {
      setTaskFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Task publish failed." });
    }
  }

  async function unpublishTask() {
    if (!token || !taskDraft.id) return;
    try {
      setTaskFeedback(null);
      const unpublishedTask = await apiFetch<TaskRecord>(`/api/tasks/${taskDraft.id}/unpublish`, token, { method: "POST" });
      setTaskFeedback({ type: "success", text: `Unpublished task ${taskDraft.name} and cleared its scoring.` });
      if (selectedEventId) await loadEvent(token, selectedEventId, undefined, undefined, unpublishedTask.id);
    } catch (caught) {
      setTaskFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Task unpublish failed." });
    }
  }

  async function deleteTask() {
    if (!token || !taskDraft.id || !selectedEventId) return;
    const confirmed = window.confirm(`Delete task "${taskDraft.name}"? This will remove its uploaded tracks and score results for this task.`);
    if (!confirmed) return;
    try {
      setTaskFeedback(null);
      const remainingTasks = tasks.filter((task) => task.id !== taskDraft.id);
      const fallbackTaskId = remainingTasks[0]?.id ?? null;
      await apiFetch<void>(`/api/tasks/${taskDraft.id}`, token, { method: "DELETE" });
      setTaskFeedback({ type: "success", text: `Deleted task ${taskDraft.name}.` });
      await loadEvent(token, selectedEventId, undefined, undefined, fallbackTaskId);
      await refreshEvents(token);
      setActiveSection("tasks");
    } catch (caught) {
      setTaskFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Task delete failed." });
    }
  }

  async function uploadIgc(file: File, pilotId?: number | null) {
    if (!token || !selectedTaskId) return;
    setUploadFeedback({ type: "pending", text: `Uploading ${file.name}...` });
    const formData = new FormData();
    formData.append("file", file);
    if (pilotId) {
      formData.append("pilot_id", String(pilotId));
    }
    await apiFetch(`/api/tasks/${selectedTaskId}/uploads`, token, { method: "POST", body: formData });
    const pilotLabel = pilotId ? pilotNameById.get(pilotId) ?? `pilot ${pilotId}` : "pilot";
    setUploadFeedback({ type: "success", text: `Uploaded ${file.name} for ${pilotLabel}.` });
    await loadTask(token, selectedTaskId);
  }

  async function uploadIgcBatch(files: FileList | File[]) {
    if (!token || !selectedTaskId) return;
    try {
      setUploadFeedback({ type: "pending", text: `Uploading ${Array.from(files).length} IGC files...` });
      const formData = new FormData();
      Array.from(files).forEach((file) => formData.append("files", file));
      const batchResults = await apiFetch<BulkUploadItemRecord[]>(`/api/tasks/${selectedTaskId}/uploads/bulk`, token, {
        method: "POST",
        body: formData,
      });
      const matchedCount = batchResults.filter((item) => item.matched).length;
      const unmatched = batchResults.filter((item) => !item.matched);
      const unmatchedSummary = unmatched.length
        ? ` Unmatched: ${unmatched.map((item) => `${item.filename} (${item.message})`).join("; ")}`
        : "";
      setUploadFeedback({ type: "success", text: `Uploaded ${matchedCount} of ${batchResults.length} IGC files in bulk.${unmatchedSummary}` });
      await loadTask(token, selectedTaskId);
      if (selectedEventId) {
        await refreshPilotSummary(token, selectedEventId);
      }
    } catch (caught) {
      setUploadFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Bulk upload failed." });
    }
  }

  async function deleteUpload(upload: UploadRecord) {
    if (!token || !selectedTaskId) return;
    await apiFetch(`/api/uploads/${upload.id}`, token, { method: "DELETE" });
    setMessage(`Deleted ${upload.filename}.`);
    await loadTask(token, selectedTaskId);
    if (selectedEventId) {
      await refreshPilotSummary(token, selectedEventId);
    }
    setTrack(null);
  }

  function downloadBlobFile(blob: Blob, filename: string) {
    const objectUrl = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 0);
  }

  async function downloadUploadFile(uploadId: number, filename: string) {
    if (!token) return;
    try {
      setResultsDownloadFeedback({ type: "pending", text: `Preparing ${filename}...`, uploadId, all: false });
      const { blob, filename: responseFilename } = await apiFetchBlob(`/api/uploads/${uploadId}/download`, token);
      downloadBlobFile(blob, responseFilename ?? filename);
      setResultsDownloadFeedback({ type: "success", text: `Download started for ${responseFilename ?? filename}.`, uploadId, all: false });
    } catch (caught) {
      setResultsDownloadFeedback({
        type: "error",
        text: caught instanceof Error ? caught.message : "Could not download the IGC file.",
        uploadId,
        all: false,
      });
    }
  }

  async function downloadAllIgcFiles() {
    if (!token || !selectedTaskId) return;
    try {
      const taskName = (selectedTask?.name ?? "task").replace(/[^a-z0-9._-]+/gi, "-");
      setResultsDownloadFeedback({ type: "pending", text: "Preparing all IGC files...", uploadId: null, all: true });
      const { blob, filename } = await apiFetchBlob(`/api/tasks/${selectedTaskId}/uploads/download-all`, token);
      downloadBlobFile(blob, filename ?? `${taskName}-igc-files.zip`);
      setResultsDownloadFeedback({ type: "success", text: "Started downloading all IGC files.", uploadId: null, all: true });
    } catch (caught) {
      setResultsDownloadFeedback({
        type: "error",
        text: caught instanceof Error ? caught.message : "Could not download all IGC files.",
        uploadId: null,
        all: true,
      });
    }
  }

  async function toggleResultTrack(uploadId: number, checked: boolean) {
    if (!token) return;
    if (!checked) {
      setSelectedResultUploadIds((current) => current.filter((id) => id !== uploadId));
      setHighlightedResultUploadId((current) => (current === uploadId ? null : current));
      return;
    }
    setSelectedResultUploadIds((current) => (current.includes(uploadId) ? current : [...current, uploadId]));
    setHighlightedResultUploadId(uploadId);
    if (!resultTracksByUploadId[uploadId]) {
      try {
        const collection = await apiFetch<TrackCollection>(`/api/uploads/${uploadId}/track`, token);
        setResultTracksByUploadId((current) => ({ ...current, [uploadId]: collection }));
      } catch (caught) {
        setSelectedResultUploadIds((current) => current.filter((id) => id !== uploadId));
        setScoringFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not load the selected pilot track." });
        return;
      }
    }
  }

  async function toggleAllResultTracks() {
    if (!token) return;
    if (!allResultTrackIds.length) return;
    if (allResultTracksChecked) {
      setSelectedResultUploadIds([]);
      setHighlightedResultUploadId(null);
      return;
    }
    const missingUploadIds = allResultTrackIds.filter((uploadId) => !resultTracksByUploadId[uploadId]);
    if (missingUploadIds.length) {
      try {
        const loadedCollections = await Promise.all(
          missingUploadIds.map(async (uploadId) => [uploadId, await apiFetch<TrackCollection>(`/api/uploads/${uploadId}/track`, token)] as const),
        );
        setResultTracksByUploadId((current) => {
          const next = { ...current };
          loadedCollections.forEach(([uploadId, collection]) => {
            next[uploadId] = collection;
          });
          return next;
        });
      } catch (caught) {
        setScoringFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not load all pilot tracks." });
        return;
      }
    }
    setSelectedResultUploadIds(allResultTrackIds);
  }

  function toggleTaskPointAdvanced(checked: boolean) {
    setTaskPointAdvanced(checked);
    if (!checked) {
      setTaskDraft((current) => ({
        ...current,
        points: normalizeTaskPointsForMode(current.points, false),
      }));
    }
  }

  async function rescoreSelectedTask() {
    if (!token) return;
    if (!selectedTaskId) {
      setScoringFeedback({ type: "error", text: "Select a task before running scoring." });
      return;
    }
    try {
      setScoringFeedback(null);
      await apiFetch(`/api/tasks/${selectedTaskId}/rescore`, token, { method: "POST" });
      await loadTask(token, selectedTaskId);
      if (selectedEventId) {
        await refreshPilotSummary(token, selectedEventId);
      }
      setScoringFeedback({ type: "success", text: "Scoring completed for the selected task." });
    } catch (caught) {
      setScoringFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Scoring failed." });
    }
  }

  async function deleteScoredTask() {
    if (!token) return;
    if (!selectedTaskId) {
      setScoringFeedback({ type: "error", text: "Select a task before deleting scored results." });
      return;
    }
    const taskName = selectedTask?.name ?? taskDraft.name ?? "this task";
    const confirmed = window.confirm(`Delete all scored results for "${taskName}"? This keeps the task and uploaded IGC files, but removes the scoring output.`);
    if (!confirmed) return;
    try {
      setScoringFeedback(null);
      await apiFetch<{ status: string; deleted_count: number }>(`/api/tasks/${selectedTaskId}/results`, token, { method: "DELETE" });
      await loadTask(token, selectedTaskId);
      if (selectedEventId) {
        await refreshPilotSummary(token, selectedEventId);
      }
      setScoringFeedback({ type: "success", text: `Deleted scored results for ${taskName}.` });
    } catch (caught) {
      setScoringFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not delete scored results." });
    }
  }

  async function promoteResult(resultId: number) {
    if (!token || !selectedTaskId) return;
    try {
      await apiFetch(`/api/results/${resultId}/promote`, token, { method: "POST" });
      await loadTask(token, selectedTaskId);
    } catch (caught) {
      setScoringFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Promote failed." });
    }
  }

  function renderParticipantCardsNode() {
    return (
      <ParticipantCards
        selectedEventId={selectedEventId}
        selectedEvent={selectedEvent}
        pilots={pilots}
        sitePilots={pilotDirectory}
        availableDirectoryPilots={availableDirectoryPilots}
        pilotForm={pilotForm}
        setPilotForm={setPilotForm}
        canManagePlatform={canManageCurrentEvent}
        isAdmin={isAdmin}
        assignExistingPilot={assignExistingPilot}
        createPilot={createPilot}
        removePilot={removePilot}
        updatePilot={updatePilot}
        uploadFile={uploadFile}
        loadEvent={(t, id) => loadEvent(t, id)}
        refreshPilotDirectory={(t) => refreshPilotDirectory(t)}
        refreshEvents={refreshEvents}
        token={token}
        setMessage={setMessage}
      />
    );
  }

  function renderActiveSection() {
      if (user?.role === "pilot" && activeSection === "events") {
        return (
          <TasksSection
            selectedEventId={selectedEventId}
            selectedEvent={selectedEvent}
            tasks={tasks}
            selectedTaskId={selectedTaskId}
            selectedTask={selectedTask}
            taskDraft={taskDraft}
            setTaskDraft={setTaskDraft}
            taskPointAdvanced={taskPointAdvanced}
            toggleTaskPointAdvanced={toggleTaskPointAdvanced}
            taskPointTypeOptions={taskPointTypeOptions}
            turnpoints={turnpoints}
            turnpointSearch={turnpointSearch}
            setTurnpointSearch={setTurnpointSearch}
            filteredTurnpoints={filteredTurnpoints}
            startGateLabels={startGateLabels}
            taskDistanceMetrics={taskDistanceMetrics}
            currentTaskTypeBehavior={currentTaskTypeBehavior}
            radiusDrafts={radiusDrafts}
            setRadiusDrafts={setRadiusDrafts}
            track={track}
            visibleAirspaces={visibleAirspaces}
            taskSectionMapTurnpoints={taskSectionMapTurnpoints}
            settingsForm={settingsForm}
            telemetrySmoothing={siteSettings}
            canManagePlatform={canManageCurrentEvent}
            taskFeedback={taskFeedback}
            token={token}
            activeSection={activeSection}
            loadTask={loadTask}
            addTurnpoint={addTurnpoint}
            updatePoint={updatePoint}
            removePoint={removePoint}
            movePoint={movePoint}
            saveTask={saveTask}
            publishTask={publishTask}
            unpublishTask={unpublishTask}
            deleteTask={deleteTask}
            startNewTask={startNewTask}
            duplicateTask={duplicateTask}
            handleRadiusInputChange={handleRadiusInputChange}
            handleRadiusInputBlur={handleRadiusInputBlur}
            handleRadiusInputKeyDown={handleRadiusInputKeyDown}
            radiusInputValue={radiusInputValue}
            overlayConfig={mapOverlayConfig.config?.task_builder}
          />
        );
      }
      switch (activeSection) {
        case "events":
          return (
            <EventsSection
              events={events}
              selectedEventId={selectedEventId}
              selectedEvent={selectedEvent}
              eventEditorId={eventEditorId}
              eventTab={eventTab}
              setEventTab={setEventTab}
              eventForm={eventForm}
              setEventForm={setEventForm}
              turnpoints={turnpoints}
              turnpointSources={turnpointSources}
              airspaces={airspaces}
              airspaceSources={airspaceSources}
              visibleAirspaces={visibleAirspaces}
              pilots={pilots}
              settingsForm={settingsForm}
              setSettingsForm={setSettingsForm}
              saveChallengeSettings={saveChallengeSettings}
              canManagePlatform={canManageCurrentEvent}
              canManageOfficialEvents={canManagePlatform}
              canCreateChallenge={Boolean(user)}
              isAdmin={isAdmin ?? false}
              selectEvent={selectEvent}
              createEventDraft={createEventDraft}
              duplicateSelectedEvent={duplicateSelectedEvent}
              deleteEvent={deleteEvent}
                saveEvent={saveEvent}
                saveEventForm={persistEventForm}
                toggleTurnpointSource={toggleTurnpointSource}
                deleteTurnpointSource={deleteTurnpointSource}
                uploadAirspaceFile={uploadAirspaceFile}
                deleteAirspaceSource={deleteAirspaceSource}
                toggleAirspaceSource={updateAirspaceSource}
                uploadFile={uploadFile}
              loadEvent={(t, id) => loadEvent(t, id)}
              refreshPilotDirectory={(t) => refreshPilotDirectory(t)}
              refreshEvents={refreshEvents}
              token={token}
              telemetrySmoothing={siteSettings}
              setMessage={setMessage}
              setError={setError}
              renderParticipantCards={renderParticipantCardsNode}
            />
          );
        case "tasks":
          return (
            <TasksSection
              selectedEventId={selectedEventId}
              selectedEvent={selectedEvent}
              tasks={tasks}
              selectedTaskId={selectedTaskId}
              selectedTask={selectedTask}
              taskDraft={taskDraft}
              setTaskDraft={setTaskDraft}
              taskPointAdvanced={taskPointAdvanced}
              toggleTaskPointAdvanced={toggleTaskPointAdvanced}
              taskPointTypeOptions={taskPointTypeOptions}
              turnpoints={turnpoints}
              turnpointSearch={turnpointSearch}
              setTurnpointSearch={setTurnpointSearch}
              filteredTurnpoints={filteredTurnpoints}
              startGateLabels={startGateLabels}
              taskDistanceMetrics={taskDistanceMetrics}
              currentTaskTypeBehavior={currentTaskTypeBehavior}
              radiusDrafts={radiusDrafts}
              setRadiusDrafts={setRadiusDrafts}
              track={track}
              visibleAirspaces={visibleAirspaces}
              taskSectionMapTurnpoints={taskSectionMapTurnpoints}
              settingsForm={settingsForm}
              telemetrySmoothing={siteSettings}
              canManagePlatform={canManageCurrentEvent}
              taskFeedback={taskFeedback}
              token={token}
              activeSection={activeSection}
              loadTask={loadTask}
              addTurnpoint={addTurnpoint}
              updatePoint={updatePoint}
              removePoint={removePoint}
              movePoint={movePoint}
              saveTask={saveTask}
              publishTask={publishTask}
              unpublishTask={unpublishTask}
              deleteTask={deleteTask}
              startNewTask={startNewTask}
              duplicateTask={duplicateTask}
              handleRadiusInputChange={handleRadiusInputChange}
              handleRadiusInputBlur={handleRadiusInputBlur}
              handleRadiusInputKeyDown={handleRadiusInputKeyDown}
              radiusInputValue={radiusInputValue}
              overlayConfig={mapOverlayConfig.config?.task_builder}
            />
          );
        case "scoring":
          return (
            <ScoringSection
              selectedEventId={selectedEventId}
              selectedTaskId={selectedTaskId}
              selectedTask={selectedTask}
              tasks={tasks}
              results={results}
              uploads={uploads}
              pilots={pilots}
              pilotById={pilotById}
              pilotNameById={pilotNameById}
              uploadById={uploadById}
              pilotSummary={pilotSummary}
              taskResultSummary={taskResultSummary}
              scoredTasks={scoredTasks}
              taskMetricsById={taskMetricsById}
              taskDraft={taskDraft}
              taskDistanceMetrics={taskDistanceMetrics}
              taskDefinitionRows={taskDefinitionRows}
              startGateLabels={startGateLabels}
              taskResultsColumns={taskResultsColumns}
              eventForm={eventForm}
              settingsForm={settingsForm}
              canManagePlatform={canManageCurrentEvent}
              scoresPortalTab={scoresPortalTab}
              setScoresPortalTab={setScoresPortalTab}
              scoringTab={scoringTab}
              setScoringTab={setScoringTab}
              adminUploadPilotId={adminUploadPilotId}
              setAdminUploadPilotId={setAdminUploadPilotId}
              uploadFeedback={uploadFeedback}
              scoringFeedback={scoringFeedback}
                resultsDownloadFeedback={resultsDownloadFeedback}
                selectedResultUploadIds={selectedResultUploadIds}
                allResultTracksChecked={allResultTracksChecked}
                resultTrackColorsByUploadId={resultTrackColorsByUploadId}
                resultTrackPalette={resultTrackPalette}
              highlightedResultUploadId={highlightedResultUploadId}
              setHighlightedResultUploadId={setHighlightedResultUploadId}
              resultsTrackOverlay={resultsTrackOverlay}
              resultsTaskMapTurnpoints={resultsTaskMapTurnpoints}
              allTurnpoints={turnpoints}
              siteSettings={siteSettings}
              token={token}
              activeSection={activeSection}
              loadTask={loadTask}
              refreshPilotSummary={refreshPilotSummary}
              uploadIgc={uploadIgc}
              uploadIgcBatch={uploadIgcBatch}
              deleteUpload={deleteUpload}
              deleteScoredTask={deleteScoredTask}
                  downloadUploadFile={downloadUploadFile}
                  downloadAllIgcFiles={downloadAllIgcFiles}
                toggleResultTrack={toggleResultTrack}
                toggleAllResultTracks={toggleAllResultTracks}
                overlayConfig={mapOverlayConfig.config?.scoring}
              />
            );
        case "live_tracking":
          return (
            <LiveTrackingSection
              selectedEventId={selectedEventId}
              selectedTaskId={selectedTaskId}
              selectedTask={selectedTask}
              tasks={tasks}
              turnpoints={turnpoints}
              visibleAirspaces={visibleAirspaces}
              pilotNameById={pilotNameById}
              token={token}
              canManagePlatform={canManageCurrentEvent}
              units={{
                altitude: settingsForm.altitude_unit,
                speed: settingsForm.speed_unit,
                distance: settingsForm.distance_unit,
                vario: settingsForm.vario_unit,
              }}
              telemetrySmoothing={siteSettings}
              loadTask={loadTask}
              overlayConfig={mapOverlayConfig.config?.dashboard_live}
            />
          );
        case "live_backtest":
          return (
            <LiveTrackingBacktestSection
              token={token}
              units={{
                altitude: settingsForm.altitude_unit,
                speed: settingsForm.speed_unit,
                distance: settingsForm.distance_unit,
                vario: settingsForm.vario_unit,
              }}
              telemetrySmoothing={siteSettings}
              overlayConfig={mapOverlayConfig.config?.dashboard_live}
            />
          );
        case "drivers":
          return (
            <DriverDashboard
              token={token}
              user={user}
              selectedEventId={selectedEventId}
              tasks={tasks}
              pilots={pilots}
              isAdmin={isAdmin}
              canManagePlatform={canManageCurrentEvent}
            />
          );
        case "sos":
          return <SosSection apiBase={resolveApiBase()} token={token} />;
        case "logbook":
          return (
            <LogbookSection
              user={user}
              flights={logbookFlights}
              loading={logbookLoading}
              feedback={logbookFeedback}
              detailFlight={logbookDetailFlight}
              detailLoading={logbookDetailLoading}
              replayFlight={logbookReplayFlight}
              replayTrack={logbookReplayTrack}
              replayLoading={logbookReplayLoading}
              units={{
                altitude: settingsForm.altitude_unit,
                speed: settingsForm.speed_unit,
                distance: settingsForm.distance_unit,
                vario: settingsForm.vario_unit,
              }}
              telemetrySmoothing={siteSettings}
              createManualFlight={createManualLogbookFlight}
              uploadFlightFile={uploadLogbookFlight}
              scanFolderForFlights={scanLogbookFolderFlights}
              attachFlightFile={attachLogbookFlightFile}
              openFlightDetail={openLogbookFlightDetail}
              closeFlightDetail={closeLogbookFlightDetail}
              openFlightReplay={openLogbookFlightReplay}
              closeFlightReplay={closeLogbookFlightReplay}
              downloadFlight={downloadLogbookFlight}
              deleteFlight={deleteLogbookFlight}
              bulkDeleteFlights={bulkDeleteLogbookFlights}
              saveFlightNotes={saveLogbookFlightNotes}
              updateFlightSite={updateLogbookFlightSite}
              setFlightStar={setLogbookFlightStar}
              overlayConfig={mapOverlayConfig.config?.logbook_replay}
            />
          );
        case "weather":
          return <WeatherSection units={{ altitude: settingsForm.altitude_unit, vario: settingsForm.vario_unit }} overlayConfig={mapOverlayConfig.config?.soaring_forecast} />;
        case "airspace":
          return (
            <AirspaceSection
              overlayConfig={mapOverlayConfig.config?.airspace_explorer}
              refreshToken={airspaceRefreshToken}
              tfrRefreshToken={tfrRefreshToken}
              selectedTfrTime={selectedTfrTime}
              maxPitchDegrees={siteSettings.max_map_pitch_degrees}
            />
          );
        case "settings":
          return (
            <SettingsSection
              token={token}
              settingsForm={settingsForm}
              setSettingsForm={setSettingsForm}
              settingsPasswordForm={settingsPasswordForm}
              setSettingsPasswordForm={setSettingsPasswordForm}
              settingsFeedback={settingsFeedback}
              saveAccountSettings={saveAccountSettings}
              savePasswordSettings={savePasswordSettings}
              pilotId={settingsForm.pilot_id ?? null}
              onPilotClaimed={handlePilotClaimed}
              onMeshDevicesChanged={handleMeshDevicesChanged}
            />
          );
        case "admin":
          return isAdmin ? (
            <AdminSection
              user={user}
              adminUsers={adminUsers}
              setAdminUsers={setAdminUsers}
              adminFeedback={adminFeedback}
              saveAdminUser={saveAdminUser}
              deleteAdminUser={deleteAdminUser}
              clearAdminUserDevice={clearAdminUserDevice}
              updateUserCredentials={updateUserCredentials}
              adminSites={adminSites}
              setAdminSites={setAdminSites}
              adminSitesFeedback={adminSitesFeedback}
              saveAdminSite={saveAdminSite}
              deleteAdminSite={deleteAdminSite}
              rescanAdminFlightSites={rescanAdminFlightSites}
              scanIgcForNewSites={scanIgcForNewSites}
              siteSettings={siteSettings}
              setSiteSettings={setSiteSettings}
              siteSettingsFeedback={siteSettingsFeedback}
              saveSiteSettings={saveSiteSettings}
              debugStatus={debugStatus}
              refreshDebugStatus={refreshDebugStatus}
              mapOverlayConfig={mapOverlayConfig}
              setMapOverlayConfig={setMapOverlayConfig}
              mapOverlayConfigFeedback={mapOverlayConfigFeedback}
              saveMapOverlayConfig={saveMapOverlayConfig}
              token={token}
              apiBase={resolveApiBase()}
            />
          ) : (
            <SettingsSection
              token={token}
              settingsForm={settingsForm}
              setSettingsForm={setSettingsForm}
              settingsPasswordForm={settingsPasswordForm}
              setSettingsPasswordForm={setSettingsPasswordForm}
              settingsFeedback={settingsFeedback}
              saveAccountSettings={saveAccountSettings}
              savePasswordSettings={savePasswordSettings}
              pilotId={settingsForm.pilot_id ?? null}
              onPilotClaimed={handlePilotClaimed}
              onMeshDevicesChanged={handleMeshDevicesChanged}
            />
          );
      }
    }

  if (!user) {
    // Stay invisible while checking auth — the login page remains visible
    // until bootstrap completes, then we render the full dashboard.
    return null;
  }

  return (
    <main className="shell">
      <div className={sidebarCompact ? "workspace-shell sidebar-compact" : "workspace-shell"}>
          <AppSidebar
            items={sidebarItems}
            activeItem={activeSection}
            onSelect={(id) => { setActiveSection(id as SidebarSection); setMessage(""); setError(""); }}
            compact={sidebarCompact}
            onToggleCompact={() => setSidebarCompact((current) => !current)}
          />
          <section className="content-shell">
            <section className="panel hero content-hero">
              <div className="hero-title-row">
                <h1>{sidebarItems.find((item) => item.id === activeSection)?.label}</h1>
                {user.role === "pilot" && activeSection === "tasks" ? (
                  <label className="hero-event-select" aria-label="Current competition">
                    <select
                      value={selectedEventId ?? ""}
                      onChange={(event) => {
                        const nextEventId = Number(event.target.value);
                        const nextEvent = events.find((candidate) => candidate.id === nextEventId);
                        if (nextEvent) void loadEvent(token, nextEvent.id, nextEvent, user, undefined, "tasks");
                      }}
                      disabled={!events.length || workspaceLoading}
                    >
                      {!events.length ? <option value="">No available comps</option> : null}
                      {events.length && selectedEventId === null ? <option value="">Select comp</option> : null}
                      {events.map((event) => (
                        <option key={event.id} value={event.id}>
                          {event.name}{event.location ? ` - ${event.location}` : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {activeSection === "airspace" && (
                  <AirspaceFreshnessStatus
                    selectedTfrTime={selectedTfrTime}
                    onTfrTimeChange={setSelectedTfrTime}
                    onAirspaceRefreshComplete={() => setAirspaceRefreshToken((current) => current + 1)}
                    onTfrRefreshComplete={() => setTfrRefreshToken((current) => current + 1)}
                  />
                )}
                {!(user.role === "pilot" && activeSection === "tasks") && activeSection !== "logbook" && activeSection !== "settings" && activeSection !== "admin" && activeSection !== "weather" && activeSection !== "airspace" && activeSection !== "sos" && activeSection !== "live_backtest" ? (
                  <span className="hero-event-context">
                    {selectedEvent ? `${selectedEvent.name}${selectedEvent.location ? ` - ${selectedEvent.location}` : ""}` : "Select or create an event to begin."}
                  </span>
                ) : null}
              </div>
              <div className="hero-actions">
                <div className="role-pill">{user.role}</div>
                <ThemeToggle />
                <button className="signout" onClick={signOut}>Sign out</button>
              </div>
            </section>
            {workspaceLoading ? (
              <div className="status-row">
                <div className="status-chip pending">Loading event workspace...</div>
              </div>
            ) : null}
            {renderActiveSection()}
          </section>
        </div>
        {error ? (
          <div className="toast-container">
            <div className="toast-chip error" onClick={() => setError("")}>{error}</div>
          </div>
        ) : null}
        {message && message !== DEFAULT_MESSAGE ? (
          <div className="toast-container">
            <div className="toast-chip success" onClick={() => setMessage("")}>{message}</div>
          </div>
        ) : null}
    </main>
  );
}
