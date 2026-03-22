"use client";

import type { ReactNode } from "react";
import { SectionCard } from "../SectionCard";
import { TaskMap, type MapLegMetric, type MapTurnpoint, type TrackCollection } from "../TaskMap";
import type {
  AccountSettingsRecord,
  EventFormState,
  PilotRecord,
  PilotSummaryRecord,
  ResultRecord,
  ScoresPortalTab,
  ScoringTab,
  TaskDraftState,
  TaskRecord,
  UploadRecord,
} from "./types";

const taskTypeOptions = [
  { value: "race_to_goal_with_gates", label: "Race to Goal with Gates" },
  { value: "race_to_goal", label: "Race to Goal" },
  { value: "elapsed_time", label: "Elapsed Time" },
  { value: "open_distance", label: "Open Distance" },
] as const;

function normalizeTaskType(value: string | null | undefined): string {
  switch (value) {
    case "race": return "race_to_goal";
    case "speedrun": return "elapsed_time";
    case "speedrun_interval": return "race_to_goal_with_gates";
    default: return value ?? "race_to_goal";
  }
}

function taskTypeLabel(value: string): string {
  return taskTypeOptions.find((option) => option.value === normalizeTaskType(value))?.label ?? value;
}

function formatClockTime(value: string | null | undefined, includeSeconds = false): string {
  if (!value) return "-";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: includeSeconds ? "2-digit" : undefined });
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

function formatElapsedSeconds(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "-";
  const totalSeconds = Math.max(0, Math.round(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatResultPoints(value: number | null | undefined): string {
  return (value ?? 0).toFixed(1);
}

function formatSpeedKmh(distanceKm: number, elapsedSeconds: number | null | undefined): string {
  if (!elapsedSeconds || elapsedSeconds <= 0) return "-";
  return (distanceKm / (elapsedSeconds / 3600)).toFixed(1);
}

function formatDateLabel(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString([], { year: "numeric", month: "2-digit", day: "2-digit" });
}

function formatMeters(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(Math.max(0, Math.round(value || 0)));
}

function taskDayQuality(results: ResultRecord[]): string {
  const firstGap = results.find((result) => result.details_json?.gap)?.details_json?.gap as
    | { validity?: { overall?: number } }
    | undefined;
  const overall = Number(firstGap?.validity?.overall ?? NaN);
  return Number.isFinite(overall) ? overall.toFixed(3) : "-";
}

function taskResultsHeaderLabel(key: "distance" | "speed" | "arrival" | "departure" | "leading"): ReactNode {
  switch (key) {
    case "distance":
      return <span className="results-header-stack"><span>Dist.</span><span>Points</span></span>;
    case "speed":
      return <span className="results-header-stack"><span>Time</span><span>Points</span></span>;
    case "arrival":
      return <span className="results-header-stack"><span>Arrival</span><span>Points</span></span>;
    case "departure":
      return <span className="results-header-stack"><span>Departure</span><span>Points</span></span>;
    case "leading":
      return <span className="results-header-stack"><span>Leading</span><span>Points</span></span>;
    default:
      return key;
  }
}

function gapAwardedPoints(result: ResultRecord, key: "distance" | "speed" | "arrival" | "departure" | "leading") {
  const gap = result.details_json?.gap as { awarded_points?: Record<string, number> } | undefined;
  return Number(gap?.awarded_points?.[key] ?? 0);
}

export interface ScoringSectionProps {
  selectedEventId: number | null;
  selectedTaskId: number | null;
  selectedTask: TaskRecord | null;
  tasks: TaskRecord[];
  results: ResultRecord[];
  uploads: UploadRecord[];
  pilots: PilotRecord[];
  pilotById: Map<number, PilotRecord>;
  pilotNameById: Map<number, string>;
  uploadById: Map<number, UploadRecord>;
  pilotSummary: PilotSummaryRecord[];
  scoredTasks: TaskRecord[];
  taskMetricsById: Map<number, { totalDistanceKm: number; optimizedDistanceKm: number; routeCoordinates: [number, number][]; legMetrics: MapLegMetric[] }>;
  taskDraft: TaskDraftState;
  taskDistanceMetrics: {
    totalDistanceKm: number;
    optimizedDistanceKm: number;
    routeCoordinates: [number, number][];
    legMetrics: MapLegMetric[];
  };
  taskDefinitionRows: Array<{
    label: string;
    legDistanceKm: number;
    identifier: string;
    radiusLabel: string;
    openLabel: string;
    closeLabel: string;
  }>;
  startGateLabels: string[];
  taskResultsColumns: Array<{ key: "distance" | "speed" | "arrival" | "departure" | "leading"; label: string }>;
  eventForm: EventFormState;
  settingsForm: AccountSettingsRecord;
  canManagePlatform: boolean;
  scoresPortalTab: ScoresPortalTab;
  setScoresPortalTab: (tab: ScoresPortalTab) => void;
  scoringTab: ScoringTab;
  setScoringTab: (tab: ScoringTab) => void;
  adminUploadPilotId: number | null;
  setAdminUploadPilotId: (id: number | null) => void;
  uploadFeedback: { type: "success" | "error" | "pending"; text: string } | null;
  scoringFeedback: { type: "success" | "error"; text: string } | null;
  resultsDownloadFeedback: { type: "success" | "error" | "pending"; text: string; uploadId: number | null; all: boolean } | null;
  selectedResultUploadIds: number[];
  resultTrackColorsByUploadId: Map<number, string>;
  resultTrackPalette: string[];
  highlightedResultUploadId: number | null;
  setHighlightedResultUploadId: (id: number | null) => void;
  resultsTrackOverlay: TrackCollection | null;
  resultsTrackPilotList: ReactNode;
  resultsTaskMapTurnpoints: MapTurnpoint[];
  token: string;
  activeSection: string;
  loadTask: (activeToken: string, taskId: number, loadedTask?: TaskRecord, includeScoringData?: boolean) => Promise<void>;
  uploadIgc: (file: File, pilotId?: number | null) => void;
  uploadIgcBatch: (files: FileList | File[]) => void;
  deleteUpload: (upload: UploadRecord) => void;
  rescoreSelectedTask: () => void;
  promoteResult: (resultId: number) => void;
  downloadUploadFile: (uploadId: number, filename: string) => void;
  downloadAllIgcFiles: () => void;
  toggleResultTrack: (uploadId: number, checked: boolean) => void;
}

export default function ScoringSection(props: ScoringSectionProps) {
  const {
    selectedEventId,
    selectedTaskId,
    selectedTask,
    tasks,
    results,
    uploads,
    pilots,
    pilotById,
    pilotNameById,
    uploadById,
    pilotSummary,
    scoredTasks,
    taskMetricsById,
    taskDraft,
    taskDistanceMetrics,
    taskDefinitionRows,
    startGateLabels,
    taskResultsColumns,
    settingsForm,
    canManagePlatform,
    scoresPortalTab,
    setScoresPortalTab,
    scoringTab,
    setScoringTab,
    adminUploadPilotId,
    setAdminUploadPilotId,
    uploadFeedback,
    scoringFeedback,
    resultsDownloadFeedback,
    selectedResultUploadIds,
    resultTrackColorsByUploadId,
    resultTrackPalette,
    highlightedResultUploadId,
    setHighlightedResultUploadId,
    resultsTrackOverlay,
    resultsTrackPilotList,
    resultsTaskMapTurnpoints,
    token,
    activeSection,
    loadTask,
    uploadIgc,
    uploadIgcBatch,
    deleteUpload,
    rescoreSelectedTask,
    promoteResult,
    downloadUploadFile,
    downloadAllIgcFiles,
    toggleResultTrack,
  } = props;

  if (!selectedEventId) return <SectionCard title="Scoring" description="Create or select an event first."><p className="hint">Scoring depends on an event and, usually, a selected task.</p></SectionCard>;
  return (
    <div className="section-stack">
      {canManagePlatform ? (
        <div className="tab-row">
          <button type="button" className={scoresPortalTab === "admin" ? "tab-button active" : "tab-button"} onClick={() => setScoresPortalTab("admin")}>Scoring operations</button>
          <button type="button" className={scoresPortalTab === "results" ? "tab-button active" : "tab-button"} onClick={() => setScoresPortalTab("results")}>Results portal</button>
        </div>
      ) : null}
      {canManagePlatform && scoresPortalTab === "admin" ? (
        <SectionCard title="Scoring operations" description="Upload missing IGC files on behalf of pilots, then run scoring manually for the selected task.">
          <div className="stack form-block">
            <label className="stack compact">
              <span>Selected task</span>
              <select value={selectedTaskId ?? ""} onChange={(event) => { const nextId = Number(event.target.value); const nextTask = tasks.find((task) => task.id === nextId); if (nextTask) void loadTask(token, nextId, nextTask, activeSection === "scoring"); }}>
                <option value="">Select a task</option>
                {tasks.map((task) => <option key={task.id} value={task.id}>{task.name} - {task.status}</option>)}
              </select>
            </label>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Pilot for upload</span>
                <select value={adminUploadPilotId ?? ""} onChange={(event) => setAdminUploadPilotId(event.target.value ? Number(event.target.value) : null)}>
                  <option value="">Select a pilot</option>
                  {pilots.map((pilot) => (
                    <option key={pilot.id} value={pilot.id}>
                      {pilot.first_name} {pilot.last_name}{pilot.competition_number ? ` - #${pilot.competition_number}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label className="file-input">
                Upload IGC for pilot
                <input
                  type="file"
                  accept=".igc"
                  disabled={!selectedTaskId || !adminUploadPilotId}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file && adminUploadPilotId) void uploadIgc(file, adminUploadPilotId);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
            </div>
            <label className="file-input">
              Upload multiple IGC files and auto-match pilots
              <input
                type="file"
                accept=".igc"
                multiple
                disabled={!selectedTaskId}
                onChange={(event) => {
                  const files = event.target.files;
                  if (files?.length) void uploadIgcBatch(files);
                  event.currentTarget.value = "";
                }}
              />
            </label>
              {uploadFeedback ? <div className={`status-chip ${uploadFeedback.type}`}>{uploadFeedback.text}</div> : null}
              <p className="hint">Bulk upload matches files to pilots using the IGC pilot header plus the filename against the event roster. Files that cannot be matched confidently are skipped and reported back to you.</p>
              <div className="button-row">
                <button type="button" onClick={() => void rescoreSelectedTask()}>Run scoring</button>
                {scoringFeedback ? <div className={`status-chip ${scoringFeedback.type}`}>{scoringFeedback.text}</div> : null}
              </div>
              {uploads.length ? (
              <div className="stack">
                {uploads.map((upload) => (
                  <div key={upload.id} className="record-card upload-record">
                    <div>
                      <strong>{upload.filename}</strong>
                      <span>{pilotNameById.get(upload.pilot_id) ?? `Pilot ${upload.pilot_id}`} - {upload.sha256.slice(0, 12)}... uploaded {new Date(upload.uploaded_at).toLocaleString()}</span>
                    </div>
                    <button type="button" className="ghost-button danger-button" onClick={() => void deleteUpload(upload)}>Delete</button>
                  </div>
                ))}
              </div>
            ) : <p className="hint">No IGC uploads have been stored for this task yet.</p>}
          </div>
        </SectionCard>
      ) : null}
      {!canManagePlatform || scoresPortalTab === "results" ? (
      <SectionCard title="Results portal" description="Task results and overall standings are visible to all signed-in users.">
        <div className="stack">
          <div className="tab-row">
            <button type="button" className={scoringTab === "task" ? "tab-button active" : "tab-button"} onClick={() => setScoringTab("task")}>Task results</button>
            <button type="button" className={scoringTab === "overall" ? "tab-button active" : "tab-button"} onClick={() => setScoringTab("overall")}>Overall results</button>
          </div>
          {scoringTab === "task" ? (
            <div className="stack form-block">
              <label className="stack compact">
                <span>Selected task</span>
                <select value={selectedTaskId ?? ""} onChange={(event) => { const nextId = Number(event.target.value); const nextTask = tasks.find((task) => task.id === nextId); if (nextTask) void loadTask(token, nextId, nextTask, activeSection === "scoring"); }}>
                  <option value="">Select a task</option>
                  {tasks.map((task) => <option key={task.id} value={task.id}>{task.name} - {task.status}</option>)}
                </select>
              </label>
              {taskDefinitionRows.length ? (
                <div className="results-sheet task-definition-sheet">
                  <div className="results-sheet-header">
                    <h3>Task definition</h3>
                    <p>{selectedTask?.name ?? taskDraft.name} {taskTypeLabel(selectedTask?.task_type ?? taskDraft.task_type) ? `- ${taskTypeLabel(selectedTask?.task_type ?? taskDraft.task_type)}` : ""}</p>
                  </div>
                  <div className="results-table-wrap">
                    <table className="results-table results-table-compact">
                      <thead>
                        <tr>
                          <th>No</th>
                          <th>Leg Dist.</th>
                          <th>Id</th>
                          <th>Radius</th>
                          <th>Open</th>
                          <th>Close</th>
                        </tr>
                      </thead>
                      <tbody>
                        {taskDefinitionRows.map((row) => (
                          <tr key={row.label}>
                            <td><strong>{row.label}</strong></td>
                            <td>{row.legDistanceKm.toFixed(1)} km</td>
                            <td>{row.identifier}</td>
                            <td>{row.radiusLabel}</td>
                            <td>{row.openLabel}</td>
                            <td>{row.closeLabel}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {startGateLabels.length ? <p className="hint task-definition-gates">Start gates: {startGateLabels.join(", ")}</p> : null}
                </div>
              ) : null}
              {results.length ? (
                <div className="results-sheet">
                  <div className="results-sheet-header results-sheet-header-actions">
                    <div>
                      <h3>{selectedTask?.name ?? "Task results"}</h3>
                      <p>{taskTypeLabel(selectedTask?.task_type ?? taskDraft.task_type)} {taskDistanceMetrics.optimizedDistanceKm ? `- ${taskDistanceMetrics.optimizedDistanceKm.toFixed(1)} km` : ""}</p>
                    </div>
                    <div className="button-row">
                      <a href={`/dashboard/live?task=${selectedTaskId}`} className="ghost-button">Live View</a>
                      <a href={`/dashboard/replay?task=${selectedTaskId}`} className="ghost-button">Replay</a>
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => void downloadAllIgcFiles()}
                        disabled={resultsDownloadFeedback?.type === "pending" && resultsDownloadFeedback.all}
                      >
                        {resultsDownloadFeedback?.type === "pending" && resultsDownloadFeedback.all ? "Preparing..." : "Download all IGC files"}
                      </button>
                      {resultsDownloadFeedback?.all ? <div className={`status-chip ${resultsDownloadFeedback.type}`}>{resultsDownloadFeedback.text}</div> : null}
                    </div>
                  </div>
                  <div className="results-table-wrap">
                    <table className="results-table results-table-task">
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>Name</th>
                            <th>Nat</th>
                            <th>Glider</th>
                            <th>SS</th>
                            <th>ES</th>
                            <th><span className="results-header-stack"><span>Time</span><span>[h:m:s]</span></span></th>
                            <th><span className="results-header-stack"><span>Speed</span><span>[km/h]</span></span></th>
                            <th><span className="results-header-stack"><span>Distance</span><span>[km]</span></span></th>
                            {taskResultsColumns.map((column) => <th key={column.key}>{taskResultsHeaderLabel(column.key)}</th>)}
                            <th>Total</th>
                            <th>IGC file</th>
                            {canManagePlatform ? <th>State</th> : null}
                          </tr>
                        </thead>
                        <tbody>
                          {results.map((result) => {
                            const pilot = pilotById.get(result.pilot_id);
                            return (
                              <tr key={result.id}>
                                <td>{result.rank ?? "-"}</td>
                              <td>
                                <strong>{result.pilot_name}</strong>
                                <div className="results-name-meta">{result.status.toUpperCase()}{result.result_state === "provisional" ? <span className="result-state-badge provisional"> &middot; PROVISIONAL</span> : null}</div>
                              </td>
                              <td>{pilot?.nation ?? "-"}</td>
                              <td>-</td>
                              <td>{formatClockTime(result.started_at, true)}</td>
                                <td>{formatClockTime(result.goal_at ?? result.ess_at, true)}</td>
                                <td>{formatElapsedSeconds(result.elapsed_seconds)}</td>
                                <td>{formatSpeedKmh(result.distance_flown_km, result.elapsed_seconds)}</td>
                                <td>{result.distance_flown_km.toFixed(1)}</td>
                                {taskResultsColumns.map((column) => (
                                  <td key={column.key}>{formatResultPoints(gapAwardedPoints(result, column.key))}</td>
                                ))}
                                <td className="results-table-total">{result.score_points.toFixed(1)}</td>
                                <td>
                                  <button
                                    type="button"
                                    className="ghost-button"
                                    disabled={resultsDownloadFeedback?.type === "pending" && resultsDownloadFeedback.uploadId === result.upload_id}
                                    onClick={() => void downloadUploadFile(result.upload_id, uploadById.get(result.upload_id)?.filename ?? `${result.pilot_name}.igc`)}
                                  >
                                    {resultsDownloadFeedback?.type === "pending" && resultsDownloadFeedback.uploadId === result.upload_id ? "Preparing..." : "Download"}
                                  </button>
                                </td>
                                {canManagePlatform ? (
                                  <td>
                                    {result.result_state === "provisional" ? (
                                      <button
                                        type="button"
                                        className="ghost-button"
                                        onClick={() => void promoteResult(result.id)}
                                      >
                                        Promote to Official
                                      </button>
                                    ) : (
                                      <span className="result-state-badge official">Official</span>
                                    )}
                                  </td>
                                ) : null}
                              </tr>
                            );
                        })}
                      </tbody>
                    </table>
                  </div>
                  {taskDraft.points.length ? (
                    <div className="results-task-map">
                      <div className="results-sheet-header">
                        <h3>Task map</h3>
                        <p>Waypoints, cylinders, course line, and checked pilot tracks for the selected task.</p>
                      </div>
                      <div className="results-task-map-layout">
                        <div className="results-task-map-pilot-list">
                          <div className="results-task-map-pilot-header">
                            <strong>Show pilot tracks</strong>
                          </div>
                          <div className="results-task-map-pilot-items">
                            {results.map((result) => {
                              const isChecked = selectedResultUploadIds.includes(result.upload_id);
                              const pilotTrackColor = resultTrackColorsByUploadId.get(result.upload_id) ?? resultTrackPalette[0];
                              return (
                                <div key={result.id} className={`results-task-map-pilot-item${highlightedResultUploadId === result.upload_id ? " is-highlighted" : ""}`}>
                                  <input
                                    type="checkbox"
                                    checked={isChecked}
                                    onChange={(event) => void toggleResultTrack(result.upload_id, event.target.checked)}
                                  />
                                  <span className="results-task-map-pilot-rank">{result.rank ?? "-"}</span>
                                  <button type="button" className="results-task-map-pilot-button" onClick={() => setHighlightedResultUploadId(result.upload_id)}>
                                    <span className="results-task-map-pilot-copy">
                                    <strong style={{ color: pilotTrackColor }}>{result.pilot_name}</strong>
                                    <small>{result.status.toUpperCase()} &middot; {result.score_points.toFixed(1)} pts</small>
                                    </span>
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                        <TaskMap
                          turnpoints={resultsTaskMapTurnpoints}
                          airspaces={[]}
                          taskPoints={taskDraft.points}
                          optimizedRoute={taskDistanceMetrics.routeCoordinates}
                          legMetrics={taskDistanceMetrics.legMetrics}
                          totalDistanceKm={taskDistanceMetrics.totalDistanceKm}
                          optimizedDistanceKm={taskDistanceMetrics.optimizedDistanceKm}
                          track={resultsTrackOverlay}
                          editable={false}
                          taskEditorOverlay={resultsTrackPilotList}
                          highlightedTrackUploadId={highlightedResultUploadId}
                          fitKey={`${selectedTaskId}:${selectedResultUploadIds.join(",")}`}
                          units={{
                            altitude: settingsForm.altitude_unit,
                            speed: settingsForm.speed_unit,
                            distance: settingsForm.distance_unit,
                            vario: settingsForm.vario_unit,
                          }}
                        />
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : <p className="hint">No scored task results are available yet for the selected task.</p>}
            </div>
          ) : (
            <div className="stack form-block">
              {pilotSummary.length ? (
                <>
                  <div className="results-table-wrap">
                    <table className="results-table results-table-compact">
                      <thead>
                        <tr>
                          <th>Task</th>
                          <th>Date</th>
                          <th>Distance [km]</th>
                          <th>Day Quality</th>
                          <th>Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {scoredTasks.map((task) => (
                          <tr key={task.id}>
                            <td><strong>{task.name}</strong></td>
                            <td>{formatDateLabel(task.published_at)}</td>
                            <td>{(taskMetricsById.get(task.id)?.optimizedDistanceKm ?? 0).toFixed(1)}</td>
                            <td>{selectedTaskId === task.id ? taskDayQuality(results) : "-"}</td>
                            <td>{taskTypeLabel(task.task_type)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="results-table-wrap">
                    <table className="results-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Name</th>
                          <th>Nat</th>
                          <th>Glider</th>
                          {scoredTasks.map((task, index) => <th key={task.id}>{`T ${index + 1}`}</th>)}
                          <th>Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pilotSummary.map((summary, index) => {
                          const pilot = pilotById.get(summary.pilot_id);
                          return (
                            <tr key={summary.pilot_id}>
                              <td>{index + 1}</td>
                              <td><strong>{summary.pilot_name}</strong></td>
                              <td>{pilot?.nation ?? "-"}</td>
                              <td>-</td>
                              {scoredTasks.map((task) => <td key={task.id}>{summary.task_scores[String(task.id)] != null ? formatResultPoints(summary.task_scores[String(task.id)]) : "-"}</td>)}
                              <td className="results-table-total">{summary.total_score_points.toFixed(1)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : <p className="hint">No overall event results are available yet.</p>}
            </div>
          )}
        </div>
      </SectionCard>
      ) : null}
    </div>
  );
}
