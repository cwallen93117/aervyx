"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { TaskMap, type MapTaskPoint, type MapTurnpoint, type TrackCollection } from "../components/TaskMap";

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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_KEY = "flightcomp-platform-token";

async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`);
  return (await response.json()) as T;
}

export default function HomePage() {
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
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
  const [eventForm, setEventForm] = useState({ name: "", location: "", starts_on: "2026-04-18", ends_on: "2026-04-24", timezone: "America/Los_Angeles" });
  const [pilotForm, setPilotForm] = useState({ first_name: "", last_name: "", email: "", nation: "", competition_number: "", civl_id: "" });
  const [taskDraft, setTaskDraft] = useState<{ id: number | null; name: string; nominal_distance_km: number; nominal_time_hours: number; nominal_launch: number; minimum_distance_km: number; penalties_text: string; points: TaskPointRecord[] }>({ id: null, name: "New Task", nominal_distance_km: 60, nominal_time_hours: 1.5, nominal_launch: 0.95, minimum_distance_km: 5, penalties_text: "{}", points: [] });

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
    const me = await apiFetch<User>("/api/auth/me", activeToken);
    const loadedEvents = await apiFetch<EventRecord[]>("/api/events", activeToken);
    setUser(me);
    setEvents(loadedEvents);
    if (loadedEvents[0]) await loadEvent(activeToken, loadedEvents[0].id);
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
    if (loadedTasks[0]) await loadTask(activeToken, loadedTasks[0].id, loadedTasks[0]);
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
    setTaskDraft({ id: task.id, name: task.name, nominal_distance_km: task.nominal_distance_km, nominal_time_hours: task.nominal_time_hours, nominal_launch: task.nominal_launch, minimum_distance_km: task.minimum_distance_km, penalties_text: JSON.stringify(task.penalties_json, null, 2), points: task.points });
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

  async function createEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    await apiFetch("/api/events", token, { method: "POST", body: JSON.stringify(eventForm) });
    setMessage(`Created event ${eventForm.name}.`);
    await bootstrap(token);
  }

  async function createPilot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedEventId) return;
    const payload = await apiFetch<PilotRecord>(`/api/events/${selectedEventId}/pilots`, token, { method: "POST", body: JSON.stringify(pilotForm) });
    setPilotForm({ first_name: "", last_name: "", email: "", nation: "", competition_number: "", civl_id: "" });
    setMessage(`Created pilot ${payload.first_name} ${payload.last_name}${payload.temp_password ? ` with temp password ${payload.temp_password}` : ""}.`);
    await loadEvent(token, selectedEventId);
  }

  async function uploadFile<T>(path: string, file: File): Promise<T> {
    if (!token) throw new Error("You must be signed in to upload files.");
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<T>(path, token, { method: "POST", body: formData });
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
  }

  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">FlightComp Platform</p>
          <h1>AirScore-aligned scoring for NAS deployment</h1>
          <p className="lede">Admin workflows, pilot uploads, and task visualization now sit on top of the new backend scoring slice.</p>
        </div>
        {user ? <button className="signout" onClick={() => { window.localStorage.removeItem(TOKEN_KEY); setToken(""); setUser(null); }}>Sign out</button> : null}
      </section>

      {!user ? (
        <form className="panel login-panel" onSubmit={handleLogin}>
          <h2>Log in</h2>
          <label>Username<input value={loginForm.username} onChange={(event) => setLoginForm({ ...loginForm, username: event.target.value })} /></label>
          <label>Password<input type="password" value={loginForm.password} onChange={(event) => setLoginForm({ ...loginForm, password: event.target.value })} /></label>
          <button type="submit">Sign in</button>
        </form>
      ) : (
        <div className="workspace-grid">
          <section className="panel sidebar">
            <div className="section-header"><h2>Events</h2><span>{events.length}</span></div>
            {events.map((event) => (
              <button key={event.id} className={event.id === selectedEventId ? "item active" : "item"} onClick={() => loadEvent(token, event.id)}>
                <strong>{event.name}</strong>
                <span>{event.location}</span>
              </button>
            ))}
            {user.role === "admin" ? (
              <form className="stack form-block" onSubmit={createEvent}>
                <h3>Create event</h3>
                <input placeholder="Name" value={eventForm.name} onChange={(event) => setEventForm({ ...eventForm, name: event.target.value })} />
                <input placeholder="Location" value={eventForm.location} onChange={(event) => setEventForm({ ...eventForm, location: event.target.value })} />
                <input type="date" value={eventForm.starts_on} onChange={(event) => setEventForm({ ...eventForm, starts_on: event.target.value })} />
                <input type="date" value={eventForm.ends_on} onChange={(event) => setEventForm({ ...eventForm, ends_on: event.target.value })} />
                <input placeholder="Timezone" value={eventForm.timezone} onChange={(event) => setEventForm({ ...eventForm, timezone: event.target.value })} />
                <button type="submit">Create</button>
              </form>
            ) : null}
          </section>

          <section className="panel main-panel">
            <div className="section-header"><h2>{user.full_name}</h2><span>{user.role}</span></div>
            <div className="status-chip">{message}</div>
            {error ? <div className="status-chip error">{error}</div> : null}
            <TaskMap turnpoints={turnpoints} taskPoints={taskDraft.points} track={track} editable={user.role === "admin"} onAddPoint={user.role === "admin" ? addMapPoint : undefined} />
            <p className="hint">Map shows imported turnpoints, task route and cylinders, plus a selected uploaded track. Admins can click to add task points.</p>

            <div className="three-up">
              <div className="stack form-block">
                <h3>Pilots</h3>
                {user.role === "admin" ? (
                  <form className="stack compact" onSubmit={createPilot}>
                    <input placeholder="First name" value={pilotForm.first_name} onChange={(event) => setPilotForm({ ...pilotForm, first_name: event.target.value })} />
                    <input placeholder="Last name" value={pilotForm.last_name} onChange={(event) => setPilotForm({ ...pilotForm, last_name: event.target.value })} />
                    <input placeholder="Email" value={pilotForm.email} onChange={(event) => setPilotForm({ ...pilotForm, email: event.target.value })} />
                    <input placeholder="Nation" value={pilotForm.nation} onChange={(event) => setPilotForm({ ...pilotForm, nation: event.target.value })} />
                    <input placeholder="Competition #" value={pilotForm.competition_number} onChange={(event) => setPilotForm({ ...pilotForm, competition_number: event.target.value })} />
                    <input placeholder="CIVL ID" value={pilotForm.civl_id} onChange={(event) => setPilotForm({ ...pilotForm, civl_id: event.target.value })} />
                    <button type="submit">Add pilot</button>
                    <label className="file-input">Import CSV<input type="file" accept=".csv" onChange={async (event) => { const file = event.target.files?.[0]; if (!file || !selectedEventId) return; await uploadFile<unknown>(`/api/events/${selectedEventId}/pilots/import-csv`, file); setMessage(`Imported pilots from ${file.name}.`); await loadEvent(token, selectedEventId); }} /></label>
                  </form>
                ) : null}
                {pilots.map((pilot) => <div key={pilot.id} className="record-card"><strong>{pilot.first_name} {pilot.last_name}</strong><span>{pilot.competition_number ?? "No comp #"}</span></div>)}
              </div>

              <div className="stack form-block">
                <h3>Turnpoints and task</h3>
                <input
                  placeholder="Search turnpoints"
                  value={turnpointSearch}
                  onChange={(event) => {
                    setTurnpointSearch(event.target.value);
                    setTurnpointDisplayCount(30);
                  }}
                />
                {user.role === "admin" ? <label className="file-input">Upload turnpoints<input type="file" accept=".csv,.geojson,.json,.gpx" onChange={async (event) => { const file = event.target.files?.[0]; if (!file || !selectedEventId) return; try { setError(""); const response = await uploadFile<TurnpointUploadResponse>(`/api/events/${selectedEventId}/turnpoints/upload`, file); setTurnpointSearch(""); setTurnpointDisplayCount(30); setMessage(`Imported ${response.imported_count} turnpoints from ${file.name}. Latest import is shown first below.`); await loadEvent(token, selectedEventId); } catch (caught) { setError(caught instanceof Error ? caught.message : `Failed to import ${file.name}.`); } finally { event.currentTarget.value = ""; } }} /></label> : null}
                <div className="list-meta">
                  <span>Showing {visibleTurnpoints.length} of {filteredTurnpoints.length} matching turnpoints.</span>
                  <span>{turnpoints.length} total in this event.</span>
                </div>
                <div className="turnpoint-list">
                  {visibleTurnpoints.map((turnpoint) => <button key={turnpoint.id} className="item" onClick={() => addTurnpoint(turnpoint)}><strong>{turnpoint.name}</strong><span>{turnpoint.code ?? "No code"}</span></button>)}
                </div>
                {filteredTurnpoints.length > visibleTurnpoints.length ? <button className="secondary ghost-button" onClick={() => setTurnpointDisplayCount((current) => current + 30)}>Show more turnpoints</button> : null}
                <select value={selectedTaskId ?? ""} onChange={(event) => { const nextId = Number(event.target.value); const nextTask = tasks.find((task) => task.id === nextId); if (nextTask) void loadTask(token, nextId, nextTask); }}>
                  <option value="">Select a task</option>
                  {tasks.map((task) => <option key={task.id} value={task.id}>{task.name}</option>)}
                </select>
                <input value={taskDraft.name} onChange={(event) => setTaskDraft({ ...taskDraft, name: event.target.value })} placeholder="Task name" />
                <textarea value={taskDraft.penalties_text} onChange={(event) => setTaskDraft({ ...taskDraft, penalties_text: event.target.value })} rows={3} />
                {user.role === "admin" ? <div className="button-row"><button onClick={saveTask}>Save task</button><button className="secondary" onClick={publishTask} disabled={!taskDraft.id}>Publish</button></div> : null}
                {taskDraft.points.map((point, index) => (
                  <div key={`${point.name}-${index}`} className="point-row">
                    <span>{point.position}</span>
                    <input value={point.name} onChange={(event) => updatePoint(index, { name: event.target.value })} />
                    <select value={point.point_type} onChange={(event) => updatePoint(index, { point_type: event.target.value })}>
                      <option value="launch">launch</option><option value="start">start</option><option value="turnpoint">turnpoint</option><option value="ESS">ESS</option><option value="goal">goal</option>
                    </select>
                    <input type="number" value={point.radius_m} onChange={(event) => updatePoint(index, { radius_m: Number(event.target.value) })} />
                  </div>
                ))}
              </div>

              <div className="stack form-block">
                <h3>Results and uploads</h3>
                {user.role === "pilot" ? <label className="file-input">Upload IGC<input type="file" accept=".igc" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadIgc(file); }} /></label> : null}
                {results.map((result) => <button key={result.id} className="item" onClick={() => viewTrack(result.upload_id)}><strong>{result.rank ?? "-"}. {result.pilot_name}</strong><span>{result.status} · {result.distance_flown_km.toFixed(1)} km · {result.score_points.toFixed(1)} pts</span></button>)}
                {uploads.map((upload) => <button key={upload.id} className="item" onClick={() => viewTrack(upload.id)}><strong>{upload.filename}</strong><span>{upload.sha256.slice(0, 12)}...</span></button>)}
                {pilotSummary.map((summary) => <div key={summary.pilot_id} className="record-card"><strong>{summary.pilot_name}</strong><span>{summary.total_score_points.toFixed(1)} pts · best {summary.best_distance_km.toFixed(1)} km</span></div>)}
              </div>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
