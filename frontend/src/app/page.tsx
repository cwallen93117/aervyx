"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppSidebar } from "../components/AppSidebar";
import { SectionCard } from "../components/SectionCard";
import { TaskMap, type MapTaskPoint, type MapTurnpoint, type TrackCollection } from "../components/TaskMap";

type SidebarSection = "events" | "participants" | "tasks" | "scoring";
type User = { id: number; username: string; full_name: string; role: "admin" | "pilot"; pilot_id: number | null };
type EventRecord = { id: number; name: string; location: string; starts_on: string; ends_on: string; timezone: string; pilot_count: number; task_count: number; turnpoint_count: number };
type PilotRecord = { id: number; first_name: string; last_name: string; competition_number: string | null; portal_username: string | null; temp_password: string | null };
type TurnpointRecord = MapTurnpoint & { event_id: number; source_id: number | null; elevation_m: number | null };
type TaskPointRecord = MapTaskPoint & { id?: number; turnpoint_id: number | null };
type TaskRecord = { id: number; event_id: number; name: string; status: string; version: number; nominal_distance_km: number; nominal_time_hours: number; nominal_launch: number; minimum_distance_km: number; penalties_json: Record<string, unknown>; published_at: string | null; points: TaskPointRecord[] };
type ResultRecord = { id: number; upload_id: number; pilot_name: string; status: string; distance_flown_km: number; score_points: number; rank: number | null };
type PilotSummaryRecord = { pilot_id: number; pilot_name: string; total_score_points: number; tasks_scored: number; best_distance_km: number };
type UploadRecord = { id: number; filename: string; sha256: string; uploaded_at: string };
type TurnpointUploadResponse = { source_id: number; format: string; imported_count: number; sha256: string; filename: string };
type TaskDraftState = { id: number | null; name: string; nominal_distance_km: number; nominal_time_hours: number; nominal_launch: number; minimum_distance_km: number; penalties_text: string; points: TaskPointRecord[] };

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_KEY = "flightcomp-platform-token";
const sidebarItems = [
  { id: "events", label: "Events", description: "Configure comps and dates." },
  { id: "participants", label: "Participants", description: "Manage pilots and rosters." },
  { id: "tasks", label: "Tasks", description: "Build routes and upload turnpoints." },
  { id: "scoring", label: "Scoring", description: "Uploads, results, and rankings." },
] satisfies Array<{ id: SidebarSection; label: string; description: string }>;

function blankEventForm() {
  return { name: "", location: "", starts_on: "2026-04-18", ends_on: "2026-04-24", timezone: "America/Los_Angeles" };
}

function blankTaskDraft(): TaskDraftState {
  return { id: null, name: "New Task", nominal_distance_km: 60, nominal_time_hours: 1.5, nominal_launch: 0.95, minimum_distance_km: 5, penalties_text: "{}", points: [] };
}

function eventToForm(event: EventRecord | null | undefined) {
  return event ? { name: event.name, location: event.location, starts_on: event.starts_on, ends_on: event.ends_on, timezone: event.timezone } : blankEventForm();
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
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [results, setResults] = useState<ResultRecord[]>([]);
  const [pilotSummary, setPilotSummary] = useState<PilotSummaryRecord[]>([]);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [track, setTrack] = useState<TrackCollection | null>(null);
  const [message, setMessage] = useState("Use admin / admin1234 or pilot-demo / pilot1234 after the backend seed runs.");
  const [error, setError] = useState("");
  const [turnpointSearch, setTurnpointSearch] = useState("");
  const [turnpointDisplayCount, setTurnpointDisplayCount] = useState(30);
  const [loginForm, setLoginForm] = useState({ username: "admin", password: "admin1234" });
  const [eventForm, setEventForm] = useState(blankEventForm());
  const [pilotForm, setPilotForm] = useState({ first_name: "", last_name: "", email: "", nation: "", competition_number: "", civl_id: "" });
  const [taskDraft, setTaskDraft] = useState<TaskDraftState>(blankTaskDraft());

  const selectedEvent = useMemo(() => events.find((event) => event.id === selectedEventId) ?? null, [events, selectedEventId]);
  const filteredTurnpoints = useMemo(
    () =>
      turnpoints
        .filter((turnpoint) => `${turnpoint.name} ${turnpoint.code ?? ""}`.toLowerCase().includes(turnpointSearch.toLowerCase()))
        .sort((left, right) => (right.source_id ?? 0) - (left.source_id ?? 0) || left.name.localeCompare(right.name)),
    [turnpoints, turnpointSearch],
  );
  const visibleTurnpoints = useMemo(() => filteredTurnpoints.slice(0, turnpointDisplayCount), [filteredTurnpoints, turnpointDisplayCount]);

  useEffect(() => {
    const savedToken = window.localStorage.getItem(TOKEN_KEY);
    if (savedToken) void bootstrap(savedToken);
  }, []);

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
      await loadEvent(activeToken, loadedEvents[0].id);
    } else {
      setSelectedEventId(null);
      setEventEditorId(null);
      setEventForm(blankEventForm());
      setPilots([]);
      setTurnpoints([]);
      setTasks([]);
      setPilotSummary([]);
      setResults([]);
      setUploads([]);
      setTrack(null);
      setTaskDraft(blankTaskDraft());
    }
  }

  async function refreshEvents(activeToken: string) {
    const loadedEvents = await apiFetch<EventRecord[]>("/api/events", activeToken);
    setEvents(loadedEvents);
    return loadedEvents;
  }

  async function loadEvent(activeToken: string, eventId: number) {
    setSelectedEventId(eventId);
    const [loadedPilots, loadedTurnpoints, loadedTasks, loadedSummary] = await Promise.all([
      apiFetch<PilotRecord[]>(`/api/events/${eventId}/pilots`, activeToken),
      apiFetch<TurnpointRecord[]>(`/api/events/${eventId}/turnpoints`, activeToken),
      apiFetch<TaskRecord[]>(`/api/events/${eventId}/tasks`, activeToken),
      apiFetch<PilotSummaryRecord[]>(`/api/events/${eventId}/pilot-summary`, activeToken),
    ]);
    setPilots(loadedPilots);
    setTurnpoints(loadedTurnpoints);
    setTasks(loadedTasks);
    setPilotSummary(loadedSummary);
    setTrack(null);
    if (loadedTasks[0]) {
      await loadTask(activeToken, loadedTasks[0].id, loadedTasks[0]);
    } else {
      setSelectedTaskId(null);
      setResults([]);
      setUploads([]);
      setTaskDraft(blankTaskDraft());
    }
  }

  async function selectEvent(event: EventRecord) {
    if (!token) return;
    setEventEditorId(event.id);
    setEventForm(eventToForm(event));
    await loadEvent(token, event.id);
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
    const savedEvent = await apiFetch<EventRecord>(eventEditorId ? `/api/events/${eventEditorId}` : "/api/events", token, { method: eventEditorId ? "PUT" : "POST", body: JSON.stringify(eventForm) });
    const loadedEvents = await refreshEvents(token);
    const nextEvent = loadedEvents.find((candidate) => candidate.id === savedEvent.id) ?? savedEvent;
    setEventEditorId(nextEvent.id);
    setEventForm(eventToForm(nextEvent));
    setMessage(`${eventEditorId ? "Updated" : "Created"} event ${savedEvent.name}.`);
    await loadEvent(token, nextEvent.id);
  }

  function startNewEvent() {
    setEventEditorId(null);
    setEventForm(blankEventForm());
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

  function startNewTask() {
    setSelectedTaskId(null);
    setTrack(null);
    setResults([]);
    setUploads([]);
    setTaskDraft(blankTaskDraft());
  }

  function addMapPoint(longitude: number, latitude: number) {
    setTaskDraft((current) => ({ ...current, points: [...current.points, { position: current.points.length + 1, point_type: current.points.length === 0 ? "launch" : "turnpoint", radius_m: current.points.length === 0 ? 300 : 400, turnpoint_id: null, name: `Point ${current.points.length + 1}`, latitude, longitude }] }));
  }

  function addTurnpoint(turnpoint: TurnpointRecord) {
    setTaskDraft((current) => ({ ...current, points: [...current.points, { position: current.points.length + 1, point_type: current.points.length === 0 ? "launch" : "turnpoint", radius_m: current.points.length === 0 ? 300 : 400, turnpoint_id: turnpoint.id, name: turnpoint.name, latitude: turnpoint.latitude, longitude: turnpoint.longitude }] }));
  }

  function updatePoint(index: number, patch: Partial<TaskPointRecord>) {
    setTaskDraft((current) => ({ ...current, points: current.points.map((point, pointIndex) => (pointIndex === index ? { ...point, ...patch } : point)).map((point, pointIndex) => ({ ...point, position: pointIndex + 1 })) }));
  }

  async function saveTask() {
    if (!token || !selectedEventId) return;
    const payload = { name: taskDraft.name, status: "draft", nominal_distance_km: taskDraft.nominal_distance_km, nominal_time_hours: taskDraft.nominal_time_hours, nominal_launch: taskDraft.nominal_launch, minimum_distance_km: taskDraft.minimum_distance_km, penalties_json: JSON.parse(taskDraft.penalties_text || "{}"), points: taskDraft.points.map((point, index) => ({ ...point, position: index + 1 })) };
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

  async function viewTrack(uploadId: number) {
    if (!token) return;
    const data = await apiFetch<TrackCollection>(`/api/uploads/${uploadId}/track`, token);
    setTrack(data);
    setActiveSection("scoring");
  }

  function renderEventsSection() {
    return (
      <div className="section-grid two-column">
        <SectionCard title="Current events" description="Select an event to load its participants, task builder, and scoring context." actions={user?.role === "admin" ? <button className="ghost-button" type="button" onClick={startNewEvent}>New event</button> : null}>
          <div className="stack">
            {events.map((event) => (
              <button key={event.id} type="button" className={event.id === selectedEventId ? "item active" : "item"} onClick={() => selectEvent(event)}>
                <strong>{event.name}</strong>
                <span>{event.location} · {event.starts_on} to {event.ends_on}</span>
              </button>
            ))}
          </div>
        </SectionCard>
        <SectionCard title={eventEditorId ? "Edit event" : "Create event"} description="Event details stay reusable across scoring, turnpoints, and participant workflows.">
          <form className="stack form-block" onSubmit={saveEvent}>
            <input placeholder="Name" value={eventForm.name} onChange={(event) => setEventForm({ ...eventForm, name: event.target.value })} />
            <input placeholder="Location" value={eventForm.location} onChange={(event) => setEventForm({ ...eventForm, location: event.target.value })} />
            <div className="inline-grid">
              <input type="date" value={eventForm.starts_on} onChange={(event) => setEventForm({ ...eventForm, starts_on: event.target.value })} />
              <input type="date" value={eventForm.ends_on} onChange={(event) => setEventForm({ ...eventForm, ends_on: event.target.value })} />
            </div>
            <input placeholder="Timezone" value={eventForm.timezone} onChange={(event) => setEventForm({ ...eventForm, timezone: event.target.value })} />
            {user?.role === "admin" ? <button type="submit">{eventEditorId ? "Save event" : "Create event"}</button> : null}
          </form>
        </SectionCard>
      </div>
    );
  }

  function renderParticipantsSection() {
    if (!selectedEventId) return <SectionCard title="Participants" description="Create or select an event first."><p className="hint">An event must be selected before participants can be managed.</p></SectionCard>;
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
                  <input type="file" accept=".csv" onChange={async (event) => { const file = event.target.files?.[0]; if (!file) return; await uploadFile<unknown>(`/api/events/${selectedEventId}/pilots/import-csv`, file); setMessage(`Imported pilots from ${file.name}.`); await loadEvent(token, selectedEventId); await refreshEvents(token); }} />
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
                  <span>{pilot.competition_number ?? "No comp #"}{pilot.portal_username ? ` · ${pilot.portal_username}` : ""}</span>
                </div>
                {user?.role === "admin" ? <button type="button" className="ghost-button danger-button" onClick={() => removePilot(pilot)}>Remove</button> : null}
              </div>
            ))}
          </div>
        </SectionCard>
      </div>
    );
  }

  function renderTasksSection() {
    if (!selectedEventId) return <SectionCard title="Tasks" description="Create or select an event first."><p className="hint">Tasks need an event context before they can be built.</p></SectionCard>;
    return (
      <div className="section-stack">
        <SectionCard title="Task map builder" description="Upload turnpoints, click on the map to add points, and save draft or published task geometry." actions={user?.role === "admin" ? <button className="ghost-button" type="button" onClick={startNewTask}>New task draft</button> : null}>
          <TaskMap turnpoints={turnpoints} taskPoints={taskDraft.points} track={track} editable={user?.role === "admin"} onAddPoint={user?.role === "admin" ? addMapPoint : undefined} />
          <p className="hint">Map shows imported turnpoints, task route and cylinders, plus a selected uploaded track. Admins can click to add task points.</p>
        </SectionCard>
        <div className="section-grid two-column">
          <SectionCard title="Turnpoints and uploads" description="Search imported turnpoints, upload waypoint files, and add them to the current draft.">
            <div className="stack form-block">
              <input placeholder="Search turnpoints" value={turnpointSearch} onChange={(event) => { setTurnpointSearch(event.target.value); setTurnpointDisplayCount(30); }} />
              {user?.role === "admin" ? <label className="file-input">Upload turnpoints<input type="file" accept=".csv,.geojson,.json,.gpx" onChange={async (event) => { const file = event.target.files?.[0]; if (!file) return; try { setError(""); const response = await uploadFile<TurnpointUploadResponse>(`/api/events/${selectedEventId}/turnpoints/upload`, file); setTurnpointSearch(""); setTurnpointDisplayCount(30); setMessage(`Imported ${response.imported_count} turnpoints from ${file.name}. Latest import is shown first below.`); await loadEvent(token, selectedEventId); await refreshEvents(token); } catch (caught) { setError(caught instanceof Error ? caught.message : `Failed to import ${file.name}.`); } finally { event.currentTarget.value = ""; } }} /></label> : null}
              <div className="list-meta">
                <span>Showing {visibleTurnpoints.length} of {filteredTurnpoints.length} matching turnpoints.</span>
                <span>{turnpoints.length} total in this event.</span>
              </div>
              <div className="turnpoint-list">
                {visibleTurnpoints.map((turnpoint) => <button key={turnpoint.id} type="button" className="item" onClick={() => addTurnpoint(turnpoint)}><strong>{turnpoint.name}</strong><span>{turnpoint.code ?? "No code"}</span></button>)}
              </div>
              {filteredTurnpoints.length > visibleTurnpoints.length ? <button type="button" className="ghost-button" onClick={() => setTurnpointDisplayCount((current) => current + 30)}>Show more turnpoints</button> : null}
            </div>
          </SectionCard>
          <SectionCard title="Task details" description="Manage drafts, route geometry, scoring settings, and publish when ready.">
            <div className="stack form-block">
              <select value={selectedTaskId ?? ""} onChange={(event) => { const nextId = Number(event.target.value); const nextTask = tasks.find((task) => task.id === nextId); if (nextTask) void loadTask(token, nextId, nextTask); }}>
                <option value="">Select a task</option>
                {tasks.map((task) => <option key={task.id} value={task.id}>{task.name} · {task.status}</option>)}
              </select>
              <input value={taskDraft.name} onChange={(event) => setTaskDraft({ ...taskDraft, name: event.target.value })} placeholder="Task name" />
              <div className="inline-grid">
                <input type="number" value={taskDraft.nominal_distance_km} onChange={(event) => setTaskDraft({ ...taskDraft, nominal_distance_km: Number(event.target.value) })} placeholder="Nominal distance" />
                <input type="number" value={taskDraft.nominal_time_hours} onChange={(event) => setTaskDraft({ ...taskDraft, nominal_time_hours: Number(event.target.value) })} placeholder="Nominal time" />
              </div>
              <div className="inline-grid">
                <input type="number" step="0.01" value={taskDraft.nominal_launch} onChange={(event) => setTaskDraft({ ...taskDraft, nominal_launch: Number(event.target.value) })} placeholder="Nominal launch" />
                <input type="number" value={taskDraft.minimum_distance_km} onChange={(event) => setTaskDraft({ ...taskDraft, minimum_distance_km: Number(event.target.value) })} placeholder="Minimum distance" />
              </div>
              <textarea value={taskDraft.penalties_text} onChange={(event) => setTaskDraft({ ...taskDraft, penalties_text: event.target.value })} rows={4} />
              {user?.role === "admin" ? <div className="button-row"><button type="button" onClick={saveTask}>Save task</button><button type="button" className="secondary" onClick={publishTask} disabled={!taskDraft.id}>Publish</button></div> : null}
              <div className="stack">
                {taskDraft.points.map((point, index) => (
                  <div key={`${point.name}-${index}`} className="point-row">
                    <span>{point.position}</span>
                    <input value={point.name} onChange={(event) => updatePoint(index, { name: event.target.value })} />
                    <select value={point.point_type} onChange={(event) => updatePoint(index, { point_type: event.target.value })}>
                      <option value="launch">launch</option>
                      <option value="start">start</option>
                      <option value="turnpoint">turnpoint</option>
                      <option value="ESS">ESS</option>
                      <option value="goal">goal</option>
                    </select>
                    <input type="number" value={point.radius_m} onChange={(event) => updatePoint(index, { radius_m: Number(event.target.value) })} />
                  </div>
                ))}
              </div>
            </div>
          </SectionCard>
        </div>
      </div>
    );
  }

  function renderScoringSection() {
    if (!selectedEventId) return <SectionCard title="Scoring" description="Create or select an event first."><p className="hint">Scoring depends on an event and, usually, a selected task.</p></SectionCard>;
    return (
      <div className="section-stack">
        <SectionCard title="Scoring map" description="Review the selected task overlay and any uploaded track you open from the results or upload list.">
          <TaskMap turnpoints={turnpoints} taskPoints={taskDraft.points} track={track} editable={false} />
        </SectionCard>
        <div className="section-grid two-column">
          <SectionCard title="Task scoring workflow" description="Select a task, upload IGC evidence, and review task results.">
            <div className="stack form-block">
              <select value={selectedTaskId ?? ""} onChange={(event) => { const nextId = Number(event.target.value); const nextTask = tasks.find((task) => task.id === nextId); if (nextTask) void loadTask(token, nextId, nextTask); }}>
                <option value="">Select a task</option>
                {tasks.map((task) => <option key={task.id} value={task.id}>{task.name} · {task.status}</option>)}
              </select>
              {user?.role === "pilot" ? <label className="file-input">Upload IGC<input type="file" accept=".igc" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadIgc(file); }} /></label> : null}
              {uploads.map((upload) => <button key={upload.id} type="button" className="item" onClick={() => viewTrack(upload.id)}><strong>{upload.filename}</strong><span>{upload.sha256.slice(0, 12)}...</span></button>)}
            </div>
          </SectionCard>
          <SectionCard title="Results" description="Existing scoring logic stays intact and is surfaced here as task standings and pilot summaries.">
            <div className="stack">
              {results.map((result) => <button key={result.id} type="button" className="item" onClick={() => viewTrack(result.upload_id)}><strong>{result.rank ?? "-"}. {result.pilot_name}</strong><span>{result.status} · {result.distance_flown_km.toFixed(1)} km · {result.score_points.toFixed(1)} pts</span></button>)}
              {pilotSummary.map((summary) => <div key={summary.pilot_id} className="record-card"><strong>{summary.pilot_name}</strong><span>{summary.total_score_points.toFixed(1)} pts · best {summary.best_distance_km.toFixed(1)} km</span></div>)}
            </div>
          </SectionCard>
        </div>
      </div>
    );
  }

  function renderActiveSection() {
    switch (activeSection) {
      case "events":
        return renderEventsSection();
      case "participants":
        return renderParticipantsSection();
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
        <div className="workspace-shell">
          <AppSidebar items={sidebarItems} activeItem={activeSection} onSelect={(id) => setActiveSection(id as SidebarSection)} eventName={selectedEvent?.name ?? null} />
          <section className="content-shell">
            <section className="panel hero content-hero">
              <div>
                <p className="eyebrow">Flight Director</p>
                <h1>{sidebarItems.find((item) => item.id === activeSection)?.label}</h1>
                <p className="lede">{selectedEvent ? `${selectedEvent.name} · ${selectedEvent.location}` : "Select or create an event to begin."}</p>
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
