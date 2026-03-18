"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppSidebar } from "../components/AppSidebar";
import { SectionCard } from "../components/SectionCard";
import { TaskMap, type MapTaskPoint, type MapTurnpoint, type TrackCollection } from "../components/TaskMap";

type SidebarSection = "events" | "tasks" | "scoring";
type User = { id: number; username: string; full_name: string; role: "admin" | "pilot"; pilot_id: number | null };
type EventRecord = {
  id: number;
  name: string;
  location: string;
  starts_on: string;
  ends_on: string;
  timezone: string;
  scoring_formula: string;
  nominal_distance_km: number;
  nominal_time_hours: number;
  nominal_launch: number;
  minimum_distance_km: number;
  nominal_goal_percent: number;
  score_back_time_minutes: number;
  goal_ss_penalty: number;
  jump_the_gun_factor: number;
  jump_the_gun_max_seconds: number;
  stopped_glide_bonus: number;
  use_distance_points: boolean;
  use_time_points: boolean;
  use_leading_points: boolean;
  use_arrival_position_points: boolean;
  use_arrival_time_points: boolean;
  use_departure_points: boolean;
  penalties_json: Record<string, unknown>;
  pilot_count: number;
  task_count: number;
  turnpoint_count: number;
};
type PilotRecord = { id: number; first_name: string; last_name: string; competition_number: string | null; portal_username: string | null; temp_password: string | null };
type TurnpointRecord = MapTurnpoint & { event_id: number; source_id: number | null; elevation_m: number | null };
type TurnpointSlotRecord = { slot_number: number; source_id: number | null; filename: string | null; file_format: string | null; sha256: string | null; uploaded_at: string | null; turnpoint_count: number };
type TaskPointRecord = MapTaskPoint & { id?: number; turnpoint_id: number | null };
type TaskRecord = {
  id: number;
  event_id: number;
  name: string;
  status: string;
  task_type: string;
  task_start_time: string | null;
  task_finish_time: string | null;
  start_open_time: string | null;
  start_close_time: string | null;
  start_gate_count: number;
  start_gate_interval_seconds: number | null;
  version: number;
  nominal_distance_km: number;
  nominal_time_hours: number;
  nominal_launch: number;
  minimum_distance_km: number;
  penalties_json: Record<string, unknown>;
  published_at: string | null;
  points: TaskPointRecord[];
};
type ResultRecord = { id: number; upload_id: number; pilot_name: string; status: string; distance_flown_km: number; score_points: number; rank: number | null };
type PilotSummaryRecord = { pilot_id: number; pilot_name: string; total_score_points: number; tasks_scored: number; best_distance_km: number };
type UploadRecord = { id: number; filename: string; sha256: string; uploaded_at: string };
type TurnpointUploadResponse = { source_id: number; format: string; imported_count: number; sha256: string; filename: string };
type TaskDraftState = {
  id: number | null;
  name: string;
  task_type: string;
  task_start_time: string;
  task_finish_time: string;
  start_open_time: string;
  start_close_time: string;
  start_gate_count: number;
  start_gate_interval_seconds: number | "";
  nominal_distance_km: number;
  nominal_time_hours: number;
  nominal_launch: number;
  minimum_distance_km: number;
  penalties_text: string;
  points: TaskPointRecord[];
};
type ScoringTab = "task" | "overall";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_KEY = "flightcomp-platform-token";
const SIDEBAR_COMPACT_KEY = "flightcomp-platform-sidebar-compact";
const sidebarItems = [
  { id: "events", label: "Events", description: "Configure comps and dates." },
  { id: "tasks", label: "Tasks", description: "Build routes and use imported turnpoints." },
  { id: "scoring", label: "Scoring", description: "Uploads, results, and rankings." },
] satisfies Array<{ id: SidebarSection; label: string; description: string }>;

const scoringFormulaOptions = [
  { value: "GAP2021", label: "GAP 2021" },
  { value: "GAP2020", label: "GAP 2020" },
  { value: "GAP2018", label: "GAP 2018" },
  { value: "GAP2016", label: "GAP 2016" },
  { value: "GAP2008", label: "GAP 2008" },
  { value: "OzGAP2005", label: "OzGAP 2005" },
  { value: "PWC2016", label: "PWC 2016" },
] as const;

const pointTypeLabels: Record<string, string> = {
  launch: "Launch",
  start: "Start",
  turnpoint: "Turnpoint",
  ESS: "ESS",
  goal: "Goal",
};
const taskTypeOptions = [
  { value: "race_to_goal", label: "Race to Goal" },
  { value: "elapsed_time", label: "Elapsed Time" },
  { value: "open_distance", label: "Open Distance" },
  { value: "race_to_goal_with_gates", label: "Race to Goal with Gates" },
] as const;

function blankEventForm() {
  return {
    name: "",
    location: "",
    starts_on: "2026-04-18",
    ends_on: "2026-04-24",
    timezone: "America/Los_Angeles",
    scoring_formula: "GAP2021",
    nominal_distance_km: 60,
    nominal_time_hours: 1.5,
    nominal_launch: 0.95,
    minimum_distance_km: 5,
    nominal_goal_percent: 0.3,
    score_back_time_minutes: 15,
    goal_ss_penalty: 0,
    jump_the_gun_factor: 0,
    jump_the_gun_max_seconds: 0,
    stopped_glide_bonus: 0,
    use_distance_points: true,
    use_time_points: true,
    use_leading_points: true,
    use_arrival_position_points: false,
    use_arrival_time_points: false,
    use_departure_points: false,
    penalties_text: "{}",
  };
}

function blankTaskDraft(overrides: Partial<TaskDraftState> = {}): TaskDraftState {
  return {
    id: null,
    name: "New Task",
    task_type: "race_to_goal",
    task_start_time: "",
    task_finish_time: "",
    start_open_time: "",
    start_close_time: "",
    start_gate_count: 1,
    start_gate_interval_seconds: "",
    nominal_distance_km: 60,
    nominal_time_hours: 1.5,
    nominal_launch: 0.95,
    minimum_distance_km: 5,
    penalties_text: "{}",
    points: [],
    ...overrides,
  };
}

function normalizeTaskType(value: string | null | undefined): string {
  switch (value) {
    case "race":
      return "race_to_goal";
    case "speedrun":
      return "elapsed_time";
    case "speedrun_interval":
      return "race_to_goal_with_gates";
    default:
      return value ?? "race_to_goal";
  }
}

function taskDraftFromEvent(event: EventRecord | null | undefined): TaskDraftState {
  return blankTaskDraft({
    nominal_distance_km: event?.nominal_distance_km ?? 60,
    nominal_time_hours: event?.nominal_time_hours ?? 1.5,
    nominal_launch: event?.nominal_launch ?? 0.95,
    minimum_distance_km: event?.minimum_distance_km ?? 5,
    penalties_text: JSON.stringify(event?.penalties_json ?? {}, null, 2),
  });
}

function normalizeTimeValue(value: string | null | undefined): string {
  return value ?? "";
}

function timeOrNull(value: string): string | null {
  return value.trim() ? value : null;
}

function haversineKm(from: { latitude: number; longitude: number }, to: { latitude: number; longitude: number }): number {
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
  const earthRadiusKm = 6371;
  const deltaLat = toRadians(to.latitude - from.latitude);
  const deltaLon = toRadians(to.longitude - from.longitude);
  const fromLat = toRadians(from.latitude);
  const toLat = toRadians(to.latitude);
  const a = Math.sin(deltaLat / 2) ** 2 + Math.cos(fromLat) * Math.cos(toLat) * Math.sin(deltaLon / 2) ** 2;
  return 2 * earthRadiusKm * Math.asin(Math.sqrt(a));
}

function entryRadiusKm(point: TaskPointRecord): number {
  return point.point_type === "turnpoint" || point.point_type === "ESS" || point.point_type === "goal" ? point.radius_m / 1000 : 0;
}

function exitRadiusKm(point: TaskPointRecord): number {
  return point.point_type === "launch" || point.point_type === "start" ? point.radius_m / 1000 : 0;
}

function computeTaskDistanceMetrics(points: TaskPointRecord[]) {
  let totalDistanceKm = 0;
  let optimizedDistanceKm = 0;
  for (let index = 1; index < points.length; index += 1) {
    const previousPoint = points[index - 1];
    const currentPoint = points[index];
    const legDistanceKm = haversineKm(previousPoint, currentPoint);
    totalDistanceKm += legDistanceKm;
    optimizedDistanceKm += Math.max(0, legDistanceKm - exitRadiusKm(previousPoint) - entryRadiusKm(currentPoint));
  }
  return { totalDistanceKm, optimizedDistanceKm };
}

function eventToForm(event: EventRecord | null | undefined) {
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
        jump_the_gun_factor: event.jump_the_gun_factor,
        jump_the_gun_max_seconds: event.jump_the_gun_max_seconds,
        stopped_glide_bonus: event.stopped_glide_bonus,
        use_distance_points: event.use_distance_points,
        use_time_points: event.use_time_points,
        use_leading_points: event.use_leading_points,
        use_arrival_position_points: event.use_arrival_position_points,
        use_arrival_time_points: event.use_arrival_time_points,
        use_departure_points: event.use_departure_points,
        penalties_text: JSON.stringify(event.penalties_json ?? {}, null, 2),
      }
    : blankEventForm();
}

async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export default function HomePage() {
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [activeSection, setActiveSection] = useState<SidebarSection>("events");
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [eventEditorId, setEventEditorId] = useState<number | null>(null);
  const [pilots, setPilots] = useState<PilotRecord[]>([]);
  const [turnpoints, setTurnpoints] = useState<TurnpointRecord[]>([]);
  const [turnpointSlots, setTurnpointSlots] = useState<TurnpointSlotRecord[]>([]);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [results, setResults] = useState<ResultRecord[]>([]);
  const [pilotSummary, setPilotSummary] = useState<PilotSummaryRecord[]>([]);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [track, setTrack] = useState<TrackCollection | null>(null);
  const [message, setMessage] = useState("Use admin / admin1234 or pilot-demo / pilot1234 after the backend seed runs.");
  const [error, setError] = useState("");
  const [loginForm, setLoginForm] = useState({ username: "admin", password: "admin1234" });
  const [eventForm, setEventForm] = useState(blankEventForm());
  const [pilotForm, setPilotForm] = useState({ first_name: "", last_name: "", email: "", nation: "", competition_number: "", civl_id: "" });
  const [taskDraft, setTaskDraft] = useState<TaskDraftState>(blankTaskDraft());
  const [taskAdvancedOpen, setTaskAdvancedOpen] = useState(false);
  const [sidebarCompact, setSidebarCompact] = useState(false);
  const [scoringTab, setScoringTab] = useState<ScoringTab>("task");

  const selectedEvent = useMemo(() => events.find((event) => event.id === selectedEventId) ?? null, [events, selectedEventId]);
  const taskDistanceMetrics = useMemo(() => computeTaskDistanceMetrics(taskDraft.points), [taskDraft.points]);

  useEffect(() => {
    const savedToken = window.localStorage.getItem(TOKEN_KEY);
    if (savedToken) void bootstrap(savedToken);
    setSidebarCompact(window.localStorage.getItem(SIDEBAR_COMPACT_KEY) === "true");
  }, []);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COMPACT_KEY, String(sidebarCompact));
  }, [sidebarCompact]);

  async function bootstrap(activeToken: string) {
    setToken(activeToken);
    setError("");
    const [me, loadedEvents] = await Promise.all([
      apiFetch<User>("/api/auth/me", activeToken),
      apiFetch<EventRecord[]>("/api/events", activeToken),
    ]);
    setUser(me);
    setEvents(loadedEvents);
    if (loadedEvents[0]) {
      setSelectedEventId(loadedEvents[0].id);
      setEventEditorId(loadedEvents[0].id);
      setEventForm(eventToForm(loadedEvents[0]));
      await loadEvent(activeToken, loadedEvents[0].id, loadedEvents[0]);
    } else {
      setSelectedEventId(null);
      setEventEditorId(null);
      setEventForm(blankEventForm());
      setPilots([]);
      setTurnpoints([]);
      setTurnpointSlots([]);
      setTasks([]);
      setPilotSummary([]);
      setResults([]);
      setUploads([]);
      setTrack(null);
      setTaskDraft(taskDraftFromEvent(null));
    }
  }

  async function refreshEvents(activeToken: string) {
    const loadedEvents = await apiFetch<EventRecord[]>("/api/events", activeToken);
    setEvents(loadedEvents);
    return loadedEvents;
  }

  async function loadEvent(activeToken: string, eventId: number, currentEvent?: EventRecord | null) {
    setSelectedEventId(eventId);
    const activeEvent = currentEvent ?? events.find((event) => event.id === eventId) ?? null;
    setEventEditorId(eventId);
    setEventForm(eventToForm(activeEvent));
    const [loadedPilots, loadedTurnpoints, loadedTurnpointSlots, loadedTasks, loadedSummary] = await Promise.all([
      apiFetch<PilotRecord[]>(`/api/events/${eventId}/pilots`, activeToken),
      apiFetch<TurnpointRecord[]>(`/api/events/${eventId}/turnpoints`, activeToken),
      apiFetch<TurnpointSlotRecord[]>(`/api/events/${eventId}/turnpoint-slots`, activeToken),
      apiFetch<TaskRecord[]>(`/api/events/${eventId}/tasks`, activeToken),
      apiFetch<PilotSummaryRecord[]>(`/api/events/${eventId}/pilot-summary`, activeToken),
    ]);
    setPilots(loadedPilots);
    setTurnpoints(loadedTurnpoints);
    setTurnpointSlots(loadedTurnpointSlots);
    setTasks(loadedTasks);
    setPilotSummary(loadedSummary);
    setTrack(null);
    if (loadedTasks[0]) {
      await loadTask(activeToken, loadedTasks[0].id, loadedTasks[0]);
    } else {
      setSelectedTaskId(null);
      setResults([]);
      setUploads([]);
      setTaskDraft(taskDraftFromEvent(activeEvent));
    }
  }

  async function selectEvent(event: EventRecord) {
    if (!token) return;
    setEventEditorId(event.id);
    setEventForm(eventToForm(event));
    await loadEvent(token, event.id, event);
  }

  async function loadTask(activeToken: string, taskId: number, loadedTask?: TaskRecord) {
    const task = loadedTask ?? (await apiFetch<TaskRecord>(`/api/tasks/${taskId}`, activeToken));
    const [loadedResults, loadedUploads] = await Promise.all([
      apiFetch<ResultRecord[]>(`/api/tasks/${taskId}/results`, activeToken),
      apiFetch<UploadRecord[]>(`/api/tasks/${taskId}/uploads`, activeToken),
    ]);
    setSelectedTaskId(taskId);
    setResults(loadedResults);
    setUploads(loadedUploads);
    setTrack(null);
    setTaskDraft({
      id: task.id,
      name: task.name,
      task_type: normalizeTaskType(task.task_type),
      task_start_time: normalizeTimeValue(task.task_start_time),
      task_finish_time: normalizeTimeValue(task.task_finish_time),
      start_open_time: normalizeTimeValue(task.start_open_time),
      start_close_time: normalizeTimeValue(task.start_close_time),
      start_gate_count: task.start_gate_count || 1,
      start_gate_interval_seconds: task.start_gate_interval_seconds ?? "",
      nominal_distance_km: task.nominal_distance_km,
      nominal_time_hours: task.nominal_time_hours,
      nominal_launch: task.nominal_launch,
      minimum_distance_km: task.minimum_distance_km,
      penalties_text: JSON.stringify(task.penalties_json, null, 2),
      points: task.points,
    });
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const response = await fetch(`${API_BASE}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(loginForm) });
      if (!response.ok) throw new Error(await response.text());
      const payload = (await response.json()) as { access_token: string; user: User };
      window.localStorage.setItem(TOKEN_KEY, payload.access_token);
      setMessage(`Signed in as ${payload.user.full_name}.`);
      await bootstrap(payload.access_token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Login failed");
    }
  }

  async function saveEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    let penaltiesJson: Record<string, unknown>;
    try {
      penaltiesJson = JSON.parse(eventForm.penalties_text || "{}") as Record<string, unknown>;
    } catch {
      setError("Scoring penalties must be valid JSON before saving the event.");
      return;
    }
    const payload = {
      name: eventForm.name,
      location: eventForm.location,
      starts_on: eventForm.starts_on,
      ends_on: eventForm.ends_on,
      timezone: eventForm.timezone,
      scoring_formula: eventForm.scoring_formula,
      nominal_distance_km: eventForm.nominal_distance_km,
      nominal_time_hours: eventForm.nominal_time_hours,
      nominal_launch: eventForm.nominal_launch,
      minimum_distance_km: eventForm.minimum_distance_km,
      nominal_goal_percent: eventForm.nominal_goal_percent,
      score_back_time_minutes: eventForm.score_back_time_minutes,
      goal_ss_penalty: eventForm.goal_ss_penalty,
      jump_the_gun_factor: eventForm.jump_the_gun_factor,
      jump_the_gun_max_seconds: eventForm.jump_the_gun_max_seconds,
      stopped_glide_bonus: eventForm.stopped_glide_bonus,
      use_distance_points: eventForm.use_distance_points,
      use_time_points: eventForm.use_time_points,
      use_leading_points: eventForm.use_leading_points,
      use_arrival_position_points: eventForm.use_arrival_position_points,
      use_arrival_time_points: eventForm.use_arrival_time_points,
      use_departure_points: eventForm.use_departure_points,
      penalties_json: penaltiesJson,
    };
    const savedEvent = await apiFetch<EventRecord>(eventEditorId ? `/api/events/${eventEditorId}` : "/api/events", token, { method: eventEditorId ? "PUT" : "POST", body: JSON.stringify(payload) });
    const loadedEvents = await refreshEvents(token);
    const nextEvent = loadedEvents.find((candidate) => candidate.id === savedEvent.id) ?? savedEvent;
    setEventEditorId(nextEvent.id);
    setEventForm(eventToForm(nextEvent));
    setMessage(`${eventEditorId ? "Updated" : "Created"} event ${savedEvent.name}.`);
    await loadEvent(token, nextEvent.id, nextEvent);
    if (!selectedTaskId) {
      setTaskDraft(taskDraftFromEvent(nextEvent));
    }
  }

  function startNewEvent() {
    setEventEditorId(null);
    setEventForm(blankEventForm());
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
      await loadEvent(token, nextEvent.id, nextEvent);
    } else {
      setMessage(`Deleted event ${eventToDelete?.name ?? ""}.`);
      setSelectedEventId(null);
      setEventEditorId(null);
      setEventForm(blankEventForm());
      setPilots([]);
      setTurnpoints([]);
      setTurnpointSlots([]);
      setTasks([]);
      setResults([]);
      setPilotSummary([]);
      setUploads([]);
      setTrack(null);
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
    await refreshEvents(token);
  }

  async function removePilot(pilot: PilotRecord) {
    if (!token || !selectedEventId) return;
    await apiFetch<void>(`/api/events/${selectedEventId}/pilots/${pilot.id}`, token, { method: "DELETE" });
    setMessage(`Removed ${pilot.first_name} ${pilot.last_name} from ${selectedEvent?.name ?? "the event"}.`);
    await loadEvent(token, selectedEventId);
    await refreshEvents(token);
  }

  async function uploadFile<T>(path: string, file: File): Promise<T> {
    if (!token) throw new Error("You must be signed in to upload files.");
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<T>(path, token, { method: "POST", body: formData });
  }

  async function deleteTurnpointSlot(slotNumber: number) {
    if (!token || !selectedEventId) return;
    const slot = turnpointSlots.find((candidate) => candidate.slot_number === slotNumber);
    const confirmed = window.confirm(`Delete the turnpoint file in slot ${slotNumber}${slot?.filename ? ` (${slot.filename})` : ""}? This removes its imported waypoints from the database.`);
    if (!confirmed) return;
    await apiFetch<void>(`/api/events/${selectedEventId}/turnpoint-slots/${slotNumber}`, token, { method: "DELETE" });
    setMessage(`Deleted turnpoint file from slot ${slotNumber}.`);
    await loadEvent(token, selectedEventId, selectedEvent);
    await refreshEvents(token);
  }

  function startNewTask() {
    setSelectedTaskId(null);
    setTrack(null);
    setResults([]);
    setUploads([]);
    setTaskDraft(taskDraftFromEvent(selectedEvent));
  }

  function addTurnpoint(turnpoint: MapTurnpoint) {
    setTaskDraft((current) => ({ ...current, points: [...current.points, { position: current.points.length + 1, point_type: current.points.length === 0 ? "launch" : "turnpoint", radius_m: current.points.length === 0 ? 300 : 400, turnpoint_id: turnpoint.id, name: turnpoint.name, latitude: turnpoint.latitude, longitude: turnpoint.longitude }] }));
  }

  function updatePoint(index: number, patch: Partial<TaskPointRecord>) {
    setTaskDraft((current) => ({ ...current, points: current.points.map((point, pointIndex) => (pointIndex === index ? { ...point, ...patch } : point)).map((point, pointIndex) => ({ ...point, position: pointIndex + 1 })) }));
  }

  function removePoint(index: number) {
    setTaskDraft((current) => ({ ...current, points: current.points.filter((_, pointIndex) => pointIndex !== index).map((point, pointIndex) => ({ ...point, position: pointIndex + 1 })) }));
  }

  function movePoint(fromIndex: number, toIndex: number) {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) {
      return;
    }
    setTaskDraft((current) => {
      const points = [...current.points];
      const [movedPoint] = points.splice(fromIndex, 1);
      points.splice(toIndex, 0, movedPoint);
      return { ...current, points: points.map((point, pointIndex) => ({ ...point, position: pointIndex + 1 })) };
    });
  }

  async function saveTask() {
    if (!token || !selectedEventId) return;
    const payload = {
      name: taskDraft.name,
      status: "draft",
      task_type: taskDraft.task_type,
      task_start_time: timeOrNull(taskDraft.task_start_time),
      task_finish_time: timeOrNull(taskDraft.task_finish_time),
      start_open_time: timeOrNull(taskDraft.start_open_time),
      start_close_time: timeOrNull(taskDraft.start_close_time),
      start_gate_count: taskDraft.start_gate_count,
      start_gate_interval_seconds: taskDraft.start_gate_interval_seconds === "" ? null : taskDraft.start_gate_interval_seconds,
      nominal_distance_km: taskDraft.nominal_distance_km,
      nominal_time_hours: taskDraft.nominal_time_hours,
      nominal_launch: taskDraft.nominal_launch,
      minimum_distance_km: taskDraft.minimum_distance_km,
      penalties_json: JSON.parse(taskDraft.penalties_text || "{}"),
      points: taskDraft.points.map((point, index) => ({ ...point, position: index + 1 })),
    };
    if (taskDraft.id) {
      await apiFetch(`/api/tasks/${taskDraft.id}`, token, { method: "PUT", body: JSON.stringify(payload) });
      setMessage(`Updated task ${taskDraft.name}.`);
    } else {
      await apiFetch(`/api/events/${selectedEventId}/tasks`, token, { method: "POST", body: JSON.stringify(payload) });
      setMessage(`Created task ${taskDraft.name}.`);
    }
    await loadEvent(token, selectedEventId);
    await refreshEvents(token);
    setActiveSection("tasks");
  }

  async function publishTask() {
    if (!token || !taskDraft.id) return;
    await apiFetch(`/api/tasks/${taskDraft.id}/publish`, token, { method: "POST" });
    setMessage(`Published task ${taskDraft.name}.`);
    if (selectedEventId) await loadEvent(token, selectedEventId);
  }

  async function uploadIgc(file: File) {
    if (!token || !selectedTaskId) return;
    const formData = new FormData();
    formData.append("file", file);
    await apiFetch(`/api/tasks/${selectedTaskId}/uploads`, token, { method: "POST", body: formData });
    setMessage(`Uploaded ${file.name}.`);
    await loadTask(token, selectedTaskId);
  }

  function renderParticipantCards() {
    if (!selectedEventId) {
      return (
        <SectionCard title="Participants" description="Create or select an event first.">
          <p className="hint">An event must be selected before participants can be managed.</p>
        </SectionCard>
      );
    }
    return (
      <div className="section-grid two-column">
        <SectionCard title="Participant intake" description="Add a pilot manually or import a roster CSV for the selected event.">
          {user?.role === "admin" ? (
            <form className="stack form-block" onSubmit={createPilot}>
              <div className="inline-grid">
                <input placeholder="First name" value={pilotForm.first_name} onChange={(event) => setPilotForm({ ...pilotForm, first_name: event.target.value })} />
                <input placeholder="Last name" value={pilotForm.last_name} onChange={(event) => setPilotForm({ ...pilotForm, last_name: event.target.value })} />
              </div>
              <input placeholder="Email" value={pilotForm.email} onChange={(event) => setPilotForm({ ...pilotForm, email: event.target.value })} />
              <div className="inline-grid">
                <input placeholder="Nation" value={pilotForm.nation} onChange={(event) => setPilotForm({ ...pilotForm, nation: event.target.value })} />
                <input placeholder="Competition #" value={pilotForm.competition_number} onChange={(event) => setPilotForm({ ...pilotForm, competition_number: event.target.value })} />
              </div>
              <input placeholder="CIVL ID" value={pilotForm.civl_id} onChange={(event) => setPilotForm({ ...pilotForm, civl_id: event.target.value })} />
              <div className="button-row">
                <button type="submit">Add pilot</button>
                <label className="file-input">
                  Import CSV
                  <input
                    type="file"
                    accept=".csv"
                    onChange={async (event) => {
                      const file = event.target.files?.[0];
                      if (!file) return;
                      await uploadFile<unknown>(`/api/events/${selectedEventId}/pilots/import-csv`, file);
                      setMessage(`Imported pilots from ${file.name}.`);
                      await loadEvent(token, selectedEventId);
                      await refreshEvents(token);
                      event.currentTarget.value = "";
                    }}
                  />
                </label>
              </div>
            </form>
          ) : (
            <p className="hint">Pilot management is available to admins. Pilots can still review the roster below.</p>
          )}
        </SectionCard>
        <SectionCard title="Current participants" description={`${pilots.length} pilots assigned to ${selectedEvent?.name ?? "this event"}.`}>
          <div className="stack">
            {pilots.map((pilot) => (
              <div key={pilot.id} className="record-card roster-row">
                <div>
                  <strong>{pilot.first_name} {pilot.last_name}</strong>
                  <span>{pilot.competition_number ?? "No comp #"}{pilot.portal_username ? ` - ${pilot.portal_username}` : ""}</span>
                </div>
                {user?.role === "admin" ? <button type="button" className="ghost-button danger-button" onClick={() => removePilot(pilot)}>Remove</button> : null}
              </div>
            ))}
          </div>
        </SectionCard>
      </div>
    );
  }

  function renderEventsSection() {
    return (
      <div className="section-stack">
        <div className="section-grid two-column">
          <SectionCard title="Current events" description="Select an event to load its participants, turnpoint files, task builder, and scoring context." actions={user?.role === "admin" ? <button className="ghost-button" type="button" onClick={startNewEvent}>New event</button> : null}>
            <div className="stack">
              {events.map((event) => (
                <button key={event.id} type="button" className={event.id === selectedEventId ? "item active" : "item"} onClick={() => selectEvent(event)}>
                  <strong>{event.name}</strong>
                  <span>{event.location} - {event.starts_on} to {event.ends_on}</span>
                </button>
              ))}
            </div>
          </SectionCard>
          <SectionCard title={eventEditorId ? "Edit event" : "Create event"} description="Event details, participants, and turnpoint files are managed at the event level.">
            <div className="stack">
              <form className="stack form-block" onSubmit={saveEvent}>
                <input placeholder="Name" value={eventForm.name} onChange={(event) => setEventForm({ ...eventForm, name: event.target.value })} />
                <input placeholder="Location" value={eventForm.location} onChange={(event) => setEventForm({ ...eventForm, location: event.target.value })} />
                <div className="inline-grid">
                  <input type="date" value={eventForm.starts_on} onChange={(event) => setEventForm({ ...eventForm, starts_on: event.target.value })} />
                  <input type="date" value={eventForm.ends_on} onChange={(event) => setEventForm({ ...eventForm, ends_on: event.target.value })} />
                </div>
                <input placeholder="Timezone" value={eventForm.timezone} onChange={(event) => setEventForm({ ...eventForm, timezone: event.target.value })} />
                {user?.role === "admin" ? (
                  <div className="button-row">
                    <button type="submit">{eventEditorId ? "Save event" : "Create event"}</button>
                    {eventEditorId ? <button type="button" className="ghost-button danger-button" onClick={() => void deleteEvent()}>Delete event</button> : null}
                  </div>
                ) : null}
              </form>
              {eventEditorId ? (
                <div className="stack">
                  <div className="section-header">
                    <h3>Turnpoint files</h3>
                    <span>{turnpoints.length} turnpoints loaded</span>
                  </div>
                  <p className="hint">Each event has three stored turnpoint slots. Uploading to a slot replaces that slot&apos;s prior file and refreshes the event turnpoints in the database.</p>
                  <div className="turnpoint-slot-grid">
                    {turnpointSlots.map((slot) => (
                      <div key={slot.slot_number} className="record-card slot-card">
                        <div className="stack compact">
                          <strong>Slot {slot.slot_number}</strong>
                          <span>{slot.filename ? `${slot.filename} - ${slot.turnpoint_count} turnpoints` : "No file uploaded yet"}</span>
                          {slot.uploaded_at ? <span>{new Date(slot.uploaded_at).toLocaleString()}</span> : null}
                        </div>
                        {user?.role === "admin" ? (
                          <div className="stack compact">
                            <label className="file-input">
                              {slot.filename ? "Replace file" : "Upload file"}
                              <input
                                type="file"
                                accept=".csv,.geojson,.json,.gpx"
                                onChange={async (event) => {
                                  const file = event.target.files?.[0];
                                  if (!file || !selectedEventId) return;
                                  try {
                                    setError("");
                                    const response = await uploadFile<TurnpointUploadResponse>(`/api/events/${selectedEventId}/turnpoints/upload?slot_number=${slot.slot_number}`, file);
                                    setMessage(`Stored ${response.imported_count} turnpoints in event slot ${slot.slot_number} from ${file.name}.`);
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
                            {slot.filename ? <button type="button" className="ghost-button danger-button" onClick={() => void deleteTurnpointSlot(slot.slot_number)}>Delete file</button> : null}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </SectionCard>
        </div>
        <SectionCard title="Scoring parameters" description="AirScore-style event defaults for GAP scoring. New task drafts inherit the core values for the selected event.">
          {eventEditorId ? (
            <form className="stack form-block" onSubmit={saveEvent}>
              <label className="stack compact">
                <span>Scoring formula</span>
                <select value={eventForm.scoring_formula} onChange={(event) => setEventForm({ ...eventForm, scoring_formula: event.target.value })}>
                  {scoringFormulaOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Nominal distance (km)</span>
                  <input type="number" value={eventForm.nominal_distance_km} onChange={(event) => setEventForm({ ...eventForm, nominal_distance_km: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <span>Nominal time (hours)</span>
                  <input type="number" step="0.1" value={eventForm.nominal_time_hours} onChange={(event) => setEventForm({ ...eventForm, nominal_time_hours: Number(event.target.value) })} />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Nominal launch</span>
                  <input type="number" step="0.01" value={eventForm.nominal_launch} onChange={(event) => setEventForm({ ...eventForm, nominal_launch: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <span>Minimum distance (km)</span>
                  <input type="number" value={eventForm.minimum_distance_km} onChange={(event) => setEventForm({ ...eventForm, minimum_distance_km: Number(event.target.value) })} />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Nominal goal (%)</span>
                  <input type="number" step="0.01" value={eventForm.nominal_goal_percent} onChange={(event) => setEventForm({ ...eventForm, nominal_goal_percent: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <span>Score-back time (minutes)</span>
                  <input type="number" value={eventForm.score_back_time_minutes} onChange={(event) => setEventForm({ ...eventForm, score_back_time_minutes: Number(event.target.value) })} />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Goal / SS penalty</span>
                  <input type="number" step="0.1" value={eventForm.goal_ss_penalty} onChange={(event) => setEventForm({ ...eventForm, goal_ss_penalty: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <span>Stopped-task glide bonus</span>
                  <input type="number" step="0.1" value={eventForm.stopped_glide_bonus} onChange={(event) => setEventForm({ ...eventForm, stopped_glide_bonus: Number(event.target.value) })} />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Jump-the-gun factor</span>
                  <input type="number" step="0.1" value={eventForm.jump_the_gun_factor} onChange={(event) => setEventForm({ ...eventForm, jump_the_gun_factor: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <span>Jump-the-gun max (seconds)</span>
                  <input type="number" value={eventForm.jump_the_gun_max_seconds} onChange={(event) => setEventForm({ ...eventForm, jump_the_gun_max_seconds: Number(event.target.value) })} />
                </label>
              </div>
              <div className="three-up">
                <label className="record-card checkbox-card">
                  <input type="checkbox" checked={eventForm.use_distance_points} onChange={(event) => setEventForm({ ...eventForm, use_distance_points: event.target.checked })} />
                  <span>Distance points</span>
                </label>
                <label className="record-card checkbox-card">
                  <input type="checkbox" checked={eventForm.use_time_points} onChange={(event) => setEventForm({ ...eventForm, use_time_points: event.target.checked })} />
                  <span>Time points</span>
                </label>
                <label className="record-card checkbox-card">
                  <input type="checkbox" checked={eventForm.use_leading_points} onChange={(event) => setEventForm({ ...eventForm, use_leading_points: event.target.checked })} />
                  <span>Leading points</span>
                </label>
                <label className="record-card checkbox-card">
                  <input type="checkbox" checked={eventForm.use_arrival_position_points} onChange={(event) => setEventForm({ ...eventForm, use_arrival_position_points: event.target.checked })} />
                  <span>Arrival position points</span>
                </label>
                <label className="record-card checkbox-card">
                  <input type="checkbox" checked={eventForm.use_arrival_time_points} onChange={(event) => setEventForm({ ...eventForm, use_arrival_time_points: event.target.checked })} />
                  <span>Arrival time points</span>
                </label>
                <label className="record-card checkbox-card">
                  <input type="checkbox" checked={eventForm.use_departure_points} onChange={(event) => setEventForm({ ...eventForm, use_departure_points: event.target.checked })} />
                  <span>Departure points</span>
                </label>
              </div>
              <label className="stack compact">
                <span>Penalty rules JSON</span>
                <textarea value={eventForm.penalties_text} onChange={(event) => setEventForm({ ...eventForm, penalties_text: event.target.value })} rows={4} placeholder='{"jump_the_gun": 0, "airspace": 0}' />
              </label>
              <p className="hint">Formula choices and labels follow the AirScore/GAP workflow, while the current MVP scorer still uses the stored event config as its setup source rather than full AirScore parity for every toggle yet.</p>
              {user?.role === "admin" ? <button type="submit">Save scoring parameters</button> : null}
            </form>
          ) : (
            <p className="hint">Create or select an event to define its scoring defaults.</p>
          )}
        </SectionCard>
        {renderParticipantCards()}
      </div>
    );
  }

  function renderTasksSection() {
    if (!selectedEventId) return <SectionCard title="Tasks" description="Create or select an event first."><p className="hint">Tasks need an event context before they can be built.</p></SectionCard>;
    return (
      <div className="section-stack">
        <SectionCard title="Task details" description="Choose a task, review its scoring fields, and manage the ordered task turnpoints.">
          <div className="stack form-block">
            <label className="stack compact">
              <span>Selected task</span>
              <select value={selectedTaskId ?? ""} onChange={(event) => { const nextId = Number(event.target.value); const nextTask = tasks.find((task) => task.id === nextId); if (nextTask) void loadTask(token, nextId, nextTask); }}>
                <option value="">Select a task</option>
                {tasks.map((task) => <option key={task.id} value={task.id}>{task.name} - {task.status}</option>)}
              </select>
            </label>
            <label className="stack compact">
              <span>Task name</span>
              <input value={taskDraft.name} onChange={(event) => setTaskDraft({ ...taskDraft, name: event.target.value })} placeholder="Task name" />
            </label>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Task type</span>
                <select value={taskDraft.task_type} onChange={(event) => setTaskDraft({ ...taskDraft, task_type: event.target.value })}>
                  {taskTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label className="stack compact">
                <span>Task start (launch open)</span>
                <input type="time" step={1} value={taskDraft.task_start_time} onChange={(event) => setTaskDraft({ ...taskDraft, task_start_time: event.target.value })} />
              </label>
            </div>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Task finish (goal close)</span>
                <input type="time" step={1} value={taskDraft.task_finish_time} onChange={(event) => setTaskDraft({ ...taskDraft, task_finish_time: event.target.value })} />
              </label>
              <label className="stack compact">
                <span>Start open</span>
                <input type="time" step={1} value={taskDraft.start_open_time} onChange={(event) => setTaskDraft({ ...taskDraft, start_open_time: event.target.value })} />
              </label>
            </div>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Start close</span>
                <input type="time" step={1} value={taskDraft.start_close_time} onChange={(event) => setTaskDraft({ ...taskDraft, start_close_time: event.target.value })} />
              </label>
              <label className="stack compact">
                <span>Number of start gates</span>
                <input type="number" min={1} value={taskDraft.start_gate_count} onChange={(event) => setTaskDraft({ ...taskDraft, start_gate_count: Math.max(1, Number(event.target.value) || 1) })} />
              </label>
            </div>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Gate interval (seconds)</span>
                <input type="number" min={0} value={taskDraft.start_gate_interval_seconds} onChange={(event) => setTaskDraft({ ...taskDraft, start_gate_interval_seconds: event.target.value === "" ? "" : Math.max(0, Number(event.target.value) || 0) })} placeholder="900" />
              </label>
              <div className="distance-summary-grid">
                <div className="record-card">
                  <strong>Total task distance</strong>
                  <span>{taskDistanceMetrics.totalDistanceKm.toFixed(1)} km center-to-center</span>
                </div>
                <div className="record-card">
                  <strong>Optimized distance</strong>
                  <span>{taskDistanceMetrics.optimizedDistanceKm.toFixed(1)} km cylinder-adjusted</span>
                </div>
              </div>
            </div>
            <div className="task-builder-layout">
              <div className="task-turnpoint-rail">
                <div className="section-header">
                  <h3>Task turnpoints</h3>
                  <span>{taskDraft.points.length} selected</span>
                </div>
                <p className="hint">Click waypoint markers on the map to add them. Drag cards to reorder the task.</p>
                <div className="task-point-list">
                  {taskDraft.points.map((point, index) => (
                    <div
                      key={`${point.turnpoint_id ?? point.name}-${index}`}
                      className={`task-point-card point-type-${point.point_type.toLowerCase()}`}
                      draggable={user?.role === "admin"}
                      onDragStart={(event) => event.dataTransfer.setData("text/plain", String(index))}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => {
                        event.preventDefault();
                        movePoint(Number(event.dataTransfer.getData("text/plain")), index);
                      }}
                    >
                      <div className="task-point-card-top">
                        <span className="drag-handle" title="Drag to reorder">{point.position}. ⋮⋮</span>
                        <strong>{point.name}</strong>
                        <span className="task-point-description">{turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code ?? "No waypoint code"}</span>
                        <span className="task-point-type-badge">{pointTypeLabels[point.point_type] ?? point.point_type}</span>
                      </div>
                      <div className="task-point-card-grid">
                        <label className="stack compact">
                          <span>Type</span>
                          <select value={point.point_type} onChange={(event) => updatePoint(index, { point_type: event.target.value })}>
                            <option value="launch">launch</option>
                            <option value="start">start</option>
                            <option value="turnpoint">turnpoint</option>
                            <option value="ESS">ESS</option>
                            <option value="goal">goal</option>
                          </select>
                        </label>
                        <label className="stack compact">
                          <span>Radius (m)</span>
                          <input type="number" value={point.radius_m} onChange={(event) => updatePoint(index, { radius_m: Number(event.target.value) })} />
                        </label>
                      </div>
                      <div className="task-point-card-actions">
                        <button type="button" className="ghost-button danger-button" onClick={() => removePoint(index)}>Remove</button>
                      </div>
                    </div>
                  ))}
                  {taskDraft.points.length === 0 ? <p className="hint">No turnpoints selected yet. Click waypoint markers on the map to add them to this task.</p> : null}
                </div>
              </div>
              <div className="task-map-panel">
                <TaskMap turnpoints={turnpoints} taskPoints={taskDraft.points} track={track} editable={user?.role === "admin"} onSelectTurnpoint={user?.role === "admin" ? addTurnpoint : undefined} />
                <p className="hint">Launch, Start, ESS, and Goal are color-themed in both the list and map to make task structure easier to scan.</p>
              </div>
            </div>
            <div className="stack">
              <button type="button" className="ghost-button advanced-toggle" onClick={() => setTaskAdvancedOpen((current) => !current)}>
                {taskAdvancedOpen ? "Hide Advanced Settings" : "Advanced Settings"}
              </button>
              {taskAdvancedOpen ? (
                <div className="stack">
                  <div className="inline-grid">
                    <label className="stack compact">
                      <span>Nominal distance (km)</span>
                      <input type="number" value={taskDraft.nominal_distance_km} onChange={(event) => setTaskDraft({ ...taskDraft, nominal_distance_km: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <span>Nominal time (hours)</span>
                      <input type="number" value={taskDraft.nominal_time_hours} onChange={(event) => setTaskDraft({ ...taskDraft, nominal_time_hours: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <span>Nominal launch</span>
                      <input type="number" step="0.01" value={taskDraft.nominal_launch} onChange={(event) => setTaskDraft({ ...taskDraft, nominal_launch: Number(event.target.value) })} />
                    </label>
                    <label className="stack compact">
                      <span>Minimum distance (km)</span>
                      <input type="number" value={taskDraft.minimum_distance_km} onChange={(event) => setTaskDraft({ ...taskDraft, minimum_distance_km: Number(event.target.value) })} />
                    </label>
                  </div>
                  <label className="stack compact">
                    <span>Task penalty / notes JSON</span>
                    <textarea value={taskDraft.penalties_text} onChange={(event) => setTaskDraft({ ...taskDraft, penalties_text: event.target.value })} rows={4} />
                  </label>
                </div>
              ) : null}
            </div>
            {user?.role === "admin" ? <div className="button-row"><button type="button" onClick={saveTask}>Save task</button><button type="button" className="secondary" onClick={publishTask} disabled={!taskDraft.id}>Publish task</button></div> : null}
          </div>
        </SectionCard>
      </div>
    );
  }

  function renderScoringSection() {
    if (!selectedEventId) return <SectionCard title="Scoring" description="Create or select an event first."><p className="hint">Scoring depends on an event and, usually, a selected task.</p></SectionCard>;
    return (
      <div className="section-stack">
        <SectionCard title="Results" description="Review task standings or switch to the overall event results summary.">
          <div className="stack">
            <div className="tab-row">
              <button type="button" className={scoringTab === "task" ? "tab-button active" : "tab-button"} onClick={() => setScoringTab("task")}>Task results</button>
              <button type="button" className={scoringTab === "overall" ? "tab-button active" : "tab-button"} onClick={() => setScoringTab("overall")}>Overall results</button>
            </div>
            {scoringTab === "task" ? (
              <div className="stack form-block">
                <label className="stack compact">
                  <span>Selected task</span>
                  <select value={selectedTaskId ?? ""} onChange={(event) => { const nextId = Number(event.target.value); const nextTask = tasks.find((task) => task.id === nextId); if (nextTask) void loadTask(token, nextId, nextTask); }}>
                    <option value="">Select a task</option>
                    {tasks.map((task) => <option key={task.id} value={task.id}>{task.name} - {task.status}</option>)}
                  </select>
                </label>
                {user?.role === "pilot" ? <label className="file-input">Upload IGC<input type="file" accept=".igc" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadIgc(file); }} /></label> : null}
                {uploads.length ? (
                  <div className="stack">
                    {uploads.map((upload) => <div key={upload.id} className="record-card"><strong>{upload.filename}</strong><span>{upload.sha256.slice(0, 12)}... uploaded {new Date(upload.uploaded_at).toLocaleString()}</span></div>)}
                  </div>
                ) : <p className="hint">No IGC uploads have been stored for this task yet.</p>}
                {results.length ? (
                  <div className="stack">
                    {results.map((result) => <div key={result.id} className="record-card"><strong>{result.rank ?? "-"}. {result.pilot_name}</strong><span>{result.status} - {result.distance_flown_km.toFixed(1)} km - {result.score_points.toFixed(1)} pts</span></div>)}
                  </div>
                ) : <p className="hint">No scored task results are available yet for the selected task.</p>}
              </div>
            ) : (
              <div className="stack">
                {pilotSummary.length ? (
                  pilotSummary.map((summary) => <div key={summary.pilot_id} className="record-card"><strong>{summary.pilot_name}</strong><span>{summary.total_score_points.toFixed(1)} pts - {summary.tasks_scored} tasks scored - best {summary.best_distance_km.toFixed(1)} km</span></div>)
                ) : <p className="hint">No overall event results are available yet.</p>}
              </div>
            )}
          </div>
        </SectionCard>
      </div>
    );
  }

  function renderActiveSection() {
    switch (activeSection) {
      case "events":
        return renderEventsSection();
      case "tasks":
        return renderTasksSection();
      case "scoring":
        return renderScoringSection();
    }
  }

  return (
    <main className="shell">
      {!user ? (
        <>
          <section className="hero">
            <div>
              <p className="eyebrow">FlightComp Platform</p>
              <h1>AirScore-aligned scoring for NAS deployment</h1>
              <p className="lede">Competition operations, task geometry, and scoring now live in a single admin workspace.</p>
            </div>
          </section>
          <form className="panel login-panel" onSubmit={handleLogin}>
            <h2>Log in</h2>
            <label>Username<input value={loginForm.username} onChange={(event) => setLoginForm({ ...loginForm, username: event.target.value })} /></label>
            <label>Password<input type="password" value={loginForm.password} onChange={(event) => setLoginForm({ ...loginForm, password: event.target.value })} /></label>
            <button type="submit">Sign in</button>
          </form>
        </>
      ) : (
        <div className={sidebarCompact ? "workspace-shell sidebar-compact" : "workspace-shell"}>
          <AppSidebar
            items={sidebarItems}
            activeItem={activeSection}
            onSelect={(id) => setActiveSection(id as SidebarSection)}
            eventName={selectedEvent?.name ?? null}
            compact={sidebarCompact}
            onToggleCompact={() => setSidebarCompact((current) => !current)}
          />
          <section className="content-shell">
            <section className="panel hero content-hero">
              <div>
                <p className="eyebrow">Flight Director</p>
                <h1>{sidebarItems.find((item) => item.id === activeSection)?.label}</h1>
                <p className="lede">{selectedEvent ? `${selectedEvent.name} - ${selectedEvent.location}` : "Select or create an event to begin."}</p>
              </div>
              <div className="hero-actions">
                <div className="role-pill">{user.role}</div>
                <button className="signout" onClick={() => { window.localStorage.removeItem(TOKEN_KEY); setToken(""); setUser(null); }}>Sign out</button>
              </div>
            </section>
            <div className="status-row">
              <div className="status-chip">{message}</div>
              {error ? <div className="status-chip error">{error}</div> : null}
            </div>
            {renderActiveSection()}
          </section>
        </div>
      )}
    </main>
  );
}
