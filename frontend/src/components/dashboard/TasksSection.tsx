"use client";

import type { KeyboardEvent } from "react";
import { SectionCard } from "../SectionCard";
import { type MapAirspaceRegion, type MapLegMetric, type MapTurnpoint, type TrackCollection } from "../TaskMap";
import { TaskBuilderMap } from "../TaskBuilderMap";
import type { AccountSettingsRecord, TaskDraftState, TaskPointRecord, TaskRecord } from "./types";

const pointTypeLabels: Record<string, string> = {
  launch: "Launch",
  start: "Start",
  turnpoint: "Turnpoint",
  ESS: "ESS",
  goal: "Goal",
};
const taskTypeOptions = [
  { value: "race_to_goal_with_gates", label: "Race to Goal with Gates" },
  { value: "race_to_goal", label: "Race to Goal" },
  { value: "elapsed_time", label: "Elapsed Time" },
  { value: "open_distance", label: "Open Distance" },
] as const;

function toSimplePointType(pointType: string): string {
  if (pointType === "launch") return "start";
  if (pointType === "ESS") return "goal";
  return pointType;
}

function formatMeters(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(Math.max(0, Math.round(value || 0)));
}

function formatDistance(valueKm: number, unit: AccountSettingsRecord["distance_unit"]): string {
  const normalizedValue = Number.isFinite(valueKm) ? valueKm : 0;
  const displayValue = unit === "mi" ? normalizedValue * 0.621371 : normalizedValue;
  return `${displayValue.toFixed(1)} ${unit}`;
}

function sanitizeMeterInput(rawValue: string): string {
  return rawValue.replace(/[^\d]/g, "").replace(/^0+(?=\d)/, "");
}

function taskPointInputKey(point: TaskPointRecord, index: number): string {
  return `${point.id ?? point.turnpoint_id ?? point.name}-${index}`;
}

export interface TasksSectionProps {
  selectedEventId: number | null;
  selectedEvent: { name?: string } | null;
  tasks: TaskRecord[];
  selectedTaskId: number | null;
  selectedTask: TaskRecord | null;
  taskDraft: TaskDraftState;
  setTaskDraft: (draft: TaskDraftState | ((current: TaskDraftState) => TaskDraftState)) => void;
  taskPointAdvanced: boolean;
  toggleTaskPointAdvanced: (checked: boolean) => void;
  taskPointTypeOptions: Array<{ value: string; label: string }>;
  turnpoints: MapTurnpoint[];
  turnpointSearch: string;
  setTurnpointSearch: (value: string) => void;
  filteredTurnpoints: MapTurnpoint[];
  startGateLabels: string[];
  taskDistanceMetrics: {
    totalDistanceKm: number;
    optimizedDistanceKm: number;
    routeCoordinates: [number, number][];
    legMetrics: MapLegMetric[];
  };
  currentTaskTypeBehavior: { usesStartWindow: boolean; usesMultipleGates: boolean };
  radiusDrafts: Record<string, string>;
  setRadiusDrafts: (drafts: Record<string, string> | ((current: Record<string, string>) => Record<string, string>)) => void;
  track: TrackCollection | null;
  visibleAirspaces: MapAirspaceRegion[];
  taskSectionMapTurnpoints: MapTurnpoint[];
  settingsForm: AccountSettingsRecord;
  canManagePlatform: boolean;
  taskFeedback: { type: "success" | "error"; text: string } | null;
  token: string;
  activeSection: string;
  loadTask: (activeToken: string, taskId: number, loadedTask?: TaskRecord, includeScoringData?: boolean) => Promise<void>;
  addTurnpoint: (turnpoint: MapTurnpoint) => void;
  updatePoint: (index: number, patch: Partial<TaskPointRecord>) => void;
  removePoint: (index: number) => void;
  movePoint: (fromIndex: number, toIndex: number) => void;
  saveTask: () => void;
  publishTask: () => void;
  unpublishTask: () => void;
  deleteTask: () => void;
  startNewTask: () => void;
  handleRadiusInputChange: (index: number, point: TaskPointRecord, rawValue: string) => void;
  handleRadiusInputBlur: (index: number, point: TaskPointRecord) => void;
  handleRadiusInputKeyDown: (event: KeyboardEvent<HTMLInputElement>, index: number, point: TaskPointRecord) => void;
  radiusInputValue: (index: number, point: TaskPointRecord) => string;
}

export default function TasksSection(props: TasksSectionProps) {
  const {
    selectedEventId,
    tasks,
    selectedTaskId,
    selectedTask,
    taskDraft,
    setTaskDraft,
    taskPointAdvanced,
    toggleTaskPointAdvanced,
    taskPointTypeOptions,
    turnpoints,
    turnpointSearch,
    setTurnpointSearch,
    filteredTurnpoints,
    startGateLabels,
    taskDistanceMetrics,
    currentTaskTypeBehavior,
    radiusDrafts,
    track,
    visibleAirspaces,
    taskSectionMapTurnpoints,
    settingsForm,
    canManagePlatform,
    taskFeedback,
    token,
    activeSection,
    loadTask,
    addTurnpoint,
    updatePoint,
    removePoint,
    movePoint,
    saveTask,
    publishTask,
    unpublishTask,
    deleteTask,
    startNewTask,
    handleRadiusInputChange,
    handleRadiusInputBlur,
    handleRadiusInputKeyDown,
    radiusInputValue,
  } = props;
  if (!selectedEventId) return <SectionCard title="Tasks" description="Create or select an event first."><p className="hint">Tasks need an event context before they can be built.</p></SectionCard>;
  const usesGatedStart = taskDraft.task_type === "race_to_goal_with_gates" && currentTaskTypeBehavior.usesMultipleGates;
  const taskIsPublished = selectedTask?.status === "published";
  const fullscreenTaskEditor = canManagePlatform ? (
    <div className="map-task-editor">
      <div className="map-task-editor-header">
        <strong>Task turnpoints</strong>
        <span>{taskDraft.points.length ? `${taskDraft.points.length} in task` : "No turnpoints yet"}</span>
      </div>
      <div className="map-task-editor-table-wrap">
        <table className="map-task-editor-table">
          <thead>
            <tr>
              <th></th>
              <th>Name</th>
              <th>Type</th>
              <th>Radius (m)</th>
              <th className="map-task-editor-distance-heading">
                <strong>Distance</strong>
                <em>(optimized)</em>
              </th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {taskDraft.points.length ? (
              taskDraft.points.map((point, index) => {
                const legMetric = index > 0 ? taskDistanceMetrics.legMetrics[index - 1] ?? null : null;
                const legDistanceKm = legMetric?.centerDistanceKm ?? null;
                const optimizedLegDistanceKm = legMetric?.optimizedDistanceKm ?? null;
                return (
                  <tr
                    key={`fullscreen-${point.turnpoint_id ?? point.name}-${index}`}
                    draggable
                    onDragStart={(event) => event.dataTransfer.setData("text/plain", String(index))}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => {
                      event.preventDefault();
                      movePoint(Number(event.dataTransfer.getData("text/plain")), index);
                    }}
                  >
                    <td className="map-task-editor-drag">{point.position}. &#x22EE;&#x22EE;</td>
                    <td className="map-task-editor-name">
                      <strong>{point.name}</strong>
                    </td>
                    <td className="map-task-editor-type">
                      <select value={taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)} onChange={(event) => updatePoint(index, { point_type: event.target.value })}>
                        {taskPointTypeOptions.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </td>
                    <td className="map-task-editor-radius">
                      <input
                        value={radiusInputValue(index, point)}
                        onChange={(event) => handleRadiusInputChange(index, point, event.target.value)}
                        onFocus={(event) => event.currentTarget.select()}
                        onBlur={() => handleRadiusInputBlur(index, point)}
                        onKeyDown={(event) => handleRadiusInputKeyDown(event, index, point)}
                        inputMode="numeric"
                      />
                    </td>
                    <td className="map-task-editor-distance">
                      <strong>{legDistanceKm === null ? <span className="task-point-distance-empty">-</span> : formatDistance(legDistanceKm, settingsForm.distance_unit)}</strong>
                      <span className="map-task-editor-distance-secondary">
                        ({optimizedLegDistanceKm === null ? "-" : formatDistance(optimizedLegDistanceKm, settingsForm.distance_unit)})
                      </span>
                    </td>
                    <td className="map-task-editor-actions">
                      <button type="button" className="ghost-button danger-button" onClick={() => removePoint(index)}>Remove</button>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={6} className="map-task-editor-empty">Click turnpoints on the map or add them from search.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="map-task-editor-footer">
        <div className="map-task-editor-footer-row">
          <div className="map-task-editor-summary" aria-label="Fullscreen task distance summary">
            <div className="map-task-editor-summary-row">
              <strong>Total:</strong>
              <span>{formatDistance(taskDistanceMetrics.totalDistanceKm, settingsForm.distance_unit)}</span>
            </div>
            <div className="map-task-editor-summary-row">
              <strong>Optimized:</strong>
              <span>{formatDistance(taskDistanceMetrics.optimizedDistanceKm, settingsForm.distance_unit)}</span>
            </div>
          </div>
          <button type="button" className="map-task-editor-save" onClick={saveTask}>
            Save task
          </button>
        </div>
        {taskFeedback ? <div className={`status-chip ${taskFeedback.type} map-task-editor-feedback`}>{taskFeedback.text}</div> : null}
      </div>
    </div>
  ) : undefined;
  return (
    <div className="section-stack">
    <SectionCard title="Task details" description={canManagePlatform ? "Choose a task, review its scoring fields, and manage the ordered task turnpoints." : "Review the selected task, turnpoints, and route geometry."}>
      <div className="stack form-block compact-clusters">
        <div className="task-toolbar">
          <div className="task-toolbar-left">
            <label className="stack compact task-toolbar-picker">
              <span>Selected task</span>
              <select value={selectedTaskId ?? ""} onChange={(event) => { const nextId = Number(event.target.value); const nextTask = tasks.find((task) => task.id === nextId); if (nextTask) void loadTask(token, nextId, nextTask, activeSection === "scoring"); }}>
                <option value="">Select a task</option>
                {tasks.map((task) => <option key={task.id} value={task.id}>{task.name} - {task.status}</option>)}
              </select>
            </label>
            {canManagePlatform ? (
              <button type="button" className="ghost-button" onClick={startNewTask}>
                New task
              </button>
            ) : null}
          </div>
          {canManagePlatform ? (
            <>
              <div className="button-row task-toolbar-actions">
                <button type="button" onClick={saveTask}>Save task</button>
                <button
                  type="button"
                  className={`scoring-ops-footer-btn task-state-toggle ${taskIsPublished ? "state-official" : "state-unofficial"}`}
                  onClick={taskIsPublished ? unpublishTask : publishTask}
                  disabled={!taskDraft.id}
                >
                  {taskIsPublished ? "Published" : "Unpublished"}
                </button>
              </div>
              <div className="task-toolbar-spacer" />
              <button type="button" className="ghost-button danger-button task-delete-button task-toolbar-delete" onClick={deleteTask} disabled={!taskDraft.id}>Delete task</button>
            </>
          ) : null}
        </div>
        {canManagePlatform && taskFeedback ? <div className={`status-chip ${taskFeedback.type} task-toolbar-feedback`}>{taskFeedback.text}</div> : null}
        <div className="fieldset-grid two-up">
          <fieldset className="fieldset-cluster">
            <legend>Task setup</legend>
            <div className="cluster-stack">
              <label className="stack compact">
                <span>Task name</span>
                <input value={taskDraft.name} onChange={(event) => setTaskDraft({ ...taskDraft, name: event.target.value })} placeholder="Task name" disabled={!canManagePlatform} />
              </label>
              <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                <span>Task date</span>
                <input type="date" value={taskDraft.task_date} onChange={(event) => setTaskDraft({ ...taskDraft, task_date: event.target.value })} disabled={!canManagePlatform} />
              </label>
              <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                <span>Task type</span>
                <select value={taskDraft.task_type} onChange={(event) => setTaskDraft({ ...taskDraft, task_type: event.target.value })} disabled={!canManagePlatform}>
                  {taskTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
            </div>
          </fieldset>

          <fieldset className="fieldset-cluster">
            <legend>Timing and gates</legend>
            <div className="fieldset-grid two-up task-timing-layout">
              {usesGatedStart ? (
                <>
                  <div className="cluster-stack">
                    <label className={currentTaskTypeBehavior.usesStartWindow ? "stack compact" : "stack compact field-disabled"}>
                      <span>Start open</span>
                      <input type="time" step={60} value={taskDraft.start_open_time} onChange={(event) => setTaskDraft({ ...taskDraft, start_open_time: event.target.value })} disabled={!currentTaskTypeBehavior.usesStartWindow} />
                    </label>
                    <label className={currentTaskTypeBehavior.usesStartWindow ? "stack compact" : "stack compact field-disabled"}>
                      <span>Start close</span>
                      <input type="time" step={60} value={taskDraft.start_close_time} onChange={(event) => setTaskDraft({ ...taskDraft, start_close_time: event.target.value })} disabled={!currentTaskTypeBehavior.usesStartWindow} />
                    </label>
                    <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                      <span>Task finish</span>
                      <input type="time" step={60} value={taskDraft.task_finish_time} onChange={(event) => setTaskDraft({ ...taskDraft, task_finish_time: event.target.value })} disabled={!canManagePlatform} />
                    </label>
                  </div>
                  <div className="cluster-stack">
                    <label className={currentTaskTypeBehavior.usesMultipleGates ? "stack compact" : "stack compact field-disabled"}>
                      <span>Start gates</span>
                      <input type="number" min={1} value={taskDraft.start_gate_count} onChange={(event) => setTaskDraft({ ...taskDraft, start_gate_count: Math.max(1, Number(event.target.value) || 1) })} disabled={!currentTaskTypeBehavior.usesMultipleGates} />
                    </label>
                    <label className={currentTaskTypeBehavior.usesMultipleGates ? "stack compact" : "stack compact field-disabled"}>
                      <span>Gate interval</span>
                      <input type="number" min={0} value={taskDraft.start_gate_interval_minutes} onChange={(event) => setTaskDraft({ ...taskDraft, start_gate_interval_minutes: event.target.value === "" ? "" : Math.max(0, Number(event.target.value) || 0) })} disabled={!currentTaskTypeBehavior.usesMultipleGates} />
                    </label>
                    {startGateLabels.length ? (
                      <div className="task-gate-times" aria-label="Start gate times">
                        <strong>Start gate times</strong>
                        <div className="task-gate-time-list">
                          {startGateLabels.map((label) => (
                            <span key={label} className="task-gate-time-chip">{label}</span>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </>
              ) : (
                <>
                  <div className="cluster-stack">
                    <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                      <span>Task start</span>
                      <input type="time" step={60} value={taskDraft.task_start_time} onChange={(event) => setTaskDraft({ ...taskDraft, task_start_time: event.target.value })} disabled={!canManagePlatform} />
                    </label>
                    <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                      <span>Start close</span>
                      <input type="time" step={60} value={taskDraft.start_close_time} onChange={(event) => setTaskDraft({ ...taskDraft, start_close_time: event.target.value })} disabled={!canManagePlatform} />
                    </label>
                  </div>
                  <div className="cluster-stack">
                    <label className={canManagePlatform ? "stack compact" : "stack compact field-disabled"}>
                      <span>Task finish</span>
                      <input type="time" step={60} value={taskDraft.task_finish_time} onChange={(event) => setTaskDraft({ ...taskDraft, task_finish_time: event.target.value })} disabled={!canManagePlatform} />
                    </label>
                  </div>
                </>
              )}
            </div>
          </fieldset>
        </div>
        <div className="task-builder-layout">
            <div className="task-turnpoint-rail">
              <div className="section-header">
                <h3>Task turnpoints</h3>
                <div className="task-turnpoint-toolbar">
                  {canManagePlatform ? (
                  <label className="task-advanced-toggle">
                      <input type="checkbox" checked={taskPointAdvanced} onChange={(event) => toggleTaskPointAdvanced(event.target.checked)} />
                      <span>Advanced</span>
                    </label>
                  ) : null}
                </div>
              </div>
              <div className="task-point-list-table-wrap">
                {taskDraft.points.length ? (
                  <>
                    <div className={`task-point-list-grid-header${canManagePlatform ? " has-actions" : ""}`}>
                      <span></span>
                      <span>Name</span>
                      <span>Type</span>
                      <span>Radius (m)</span>
                      <span className="task-point-distance-heading">
                        <strong>Distance</strong>
                        <em>(optimized)</em>
                      </span>
                      {canManagePlatform ? <span></span> : null}
                    </div>
                    <div className="task-point-list-scroll">
                      {taskDraft.points.map((point, index) => {
                        const waypointCode = turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code;
                        const legMetric = index > 0 ? taskDistanceMetrics.legMetrics[index - 1] ?? null : null;
                        const legDistanceKm = legMetric?.centerDistanceKm ?? null;
                        const optimizedLegDistanceKm = legMetric?.optimizedDistanceKm ?? null;
                        return (
                          <div
                            key={`compact-${point.turnpoint_id ?? point.name}-${index}`}
                            className={`task-point-list-grid-row point-type-${(taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)).toLowerCase()}${canManagePlatform ? " has-actions" : ""}`}
                            draggable={canManagePlatform}
                            onDragStart={(event) => event.dataTransfer.setData("text/plain", String(index))}
                            onDragOver={(event) => event.preventDefault()}
                            onDrop={(event) => {
                              event.preventDefault();
                              movePoint(Number(event.dataTransfer.getData("text/plain")), index);
                            }}
                          >
                            <div className="task-point-row-order">
                              <span className="drag-handle" title="Drag to reorder">{point.position}. :::</span>
                            </div>
                            <div className="task-point-row-name">
                              <strong>{point.name}</strong>
                              {waypointCode ? <span>{waypointCode}</span> : null}
                            </div>
                            <div className="task-point-row-type">
                              {canManagePlatform ? (
                                <select value={taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)} onChange={(event) => updatePoint(index, { point_type: event.target.value })}>
                                  {taskPointTypeOptions.map((option) => (
                                    <option key={option.value} value={option.value}>{option.label}</option>
                                  ))}
                                </select>
                              ) : (
                                <span className="task-point-type-badge">{pointTypeLabels[taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)] ?? (taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type))}</span>
                              )}
                            </div>
                            <div className="task-point-row-radius">
                              {canManagePlatform ? (
                                <input
                                  type="text"
                                  inputMode="numeric"
                                  value={radiusInputValue(index, point)}
                                  onFocus={(event) => event.currentTarget.select()}
                                  onChange={(event) => handleRadiusInputChange(index, point, event.target.value)}
                                  onBlur={() => handleRadiusInputBlur(index, point)}
                                  onKeyDown={(event) => handleRadiusInputKeyDown(event, index, point)}
                                  placeholder="400"
                                  aria-label={`Radius in meters for ${point.name}`}
                                />
                              ) : (
                                <span>{formatMeters(point.radius_m)}</span>
                              )}
                            </div>
                            <div className="task-point-row-distance">
                              <div className="task-point-distance-stack">
                                <strong>{legDistanceKm === null ? <span className="task-point-distance-empty">-</span> : formatDistance(legDistanceKm, settingsForm.distance_unit)}</strong>
                                <span className="task-point-distance-secondary">
                                  ({optimizedLegDistanceKm === null ? "-" : formatDistance(optimizedLegDistanceKm, settingsForm.distance_unit)})
                                </span>
                              </div>
                            </div>
                            {canManagePlatform ? (
                              <div className="task-point-row-actions">
                                <button type="button" className="ghost-button danger-button" onClick={() => removePoint(index)}>Remove</button>
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </>
                ) : null}
              </div>
              <p className="hint">{canManagePlatform ? "Click waypoint markers on the map to add them. Drag cards to reorder the task." : "Published task turnpoints are shown here in route order."}</p>
              {canManagePlatform ? (
                <div className="task-search-panel">
                  <label className="stack compact">
                    <span>Search turnpoints</span>
                    <input
                      type="text"
                      value={turnpointSearch}
                      onChange={(event) => setTurnpointSearch(event.target.value)}
                      placeholder="Search by name, waypoint code, or * for all"
                    />
                  </label>
                  {turnpointSearch.trim() ? (
                    filteredTurnpoints.length ? (
                      <div className="task-search-results">
                        {filteredTurnpoints.map((turnpoint) => (
                          <div key={`search-${turnpoint.id}`} className="task-search-row">
                            <div>
                              <strong>{turnpoint.name}</strong>
                              <span>{turnpoint.code ?? ""}</span>
                            </div>
                            <button type="button" className="ghost-button" onClick={() => addTurnpoint(turnpoint)}>Add</button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="hint">No turnpoints match that search.</p>
                    )
                  ) : null}
                </div>
              ) : null}
              <div className="task-point-list task-point-list-legacy" aria-hidden="true">
                {taskDraft.points.map((point, index) => (
                  <div
                    key={`${point.turnpoint_id ?? point.name}-${index}`}
                    className={`task-point-card point-type-${(taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)).toLowerCase()}`}
                    draggable={canManagePlatform}
                    onDragStart={(event) => event.dataTransfer.setData("text/plain", String(index))}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => {
                    event.preventDefault();
                    movePoint(Number(event.dataTransfer.getData("text/plain")), index);
                  }}
                >
                    <div className="task-point-card-top">
                      <span className="drag-handle" title="Drag to reorder">{point.position}. &#x22EE;&#x22EE;</span>
                      <strong>{point.name}</strong>
                      <span className="task-point-description">{turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code ?? ""}</span>
                      <span className="task-point-type-badge">{pointTypeLabels[taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)] ?? (taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type))}</span>
                    </div>
                    <div className="task-point-card-grid">
                      {canManagePlatform ? (
                        <>
                          <label className="stack compact">
                            <span>Type</span>
                            <select value={taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)} onChange={(event) => updatePoint(index, { point_type: event.target.value })}>
                              {taskPointTypeOptions.map((option) => (
                                <option key={option.value} value={option.value}>{option.label}</option>
                              ))}
                            </select>
                          </label>
                        <label className="stack compact">
                          <span>Radius (m)</span>
                          <input
                            type="text"
                            inputMode="numeric"
                            value={radiusInputValue(index, point)}
                            onFocus={(event) => event.currentTarget.select()}
                            onChange={(event) => handleRadiusInputChange(index, point, event.target.value)}
                            onBlur={() => handleRadiusInputBlur(index, point)}
                            onKeyDown={(event) => handleRadiusInputKeyDown(event, index, point)}
                            placeholder="400"
                            aria-label={`Radius in meters for ${point.name}`}
                          />
                        </label>
                      </>
                    ) : (
                      <>
                        <div className="record-card">
                          <strong>Type</strong>
                          <span>{pointTypeLabels[taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)] ?? (taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type))}</span>
                        </div>
                        <div className="record-card">
                          <strong>Radius</strong>
                          <span>{point.radius_m.toFixed(0)} m</span>
                        </div>
                      </>
                    )}
                  </div>
                  {canManagePlatform ? (
                    <div className="task-point-card-actions">
                      <button type="button" className="ghost-button danger-button" onClick={() => removePoint(index)}>Remove</button>
                    </div>
                  ) : null}
                </div>
              ))}
              {taskDraft.points.length === 0 ? <p className="hint">No turnpoints selected yet. Click waypoint markers on the map to add them to this task.</p> : null}
            </div>
            <p className="hint">{taskPointAdvanced ? "Advanced mode keeps Launch, Start, ESS, and Goal separate for scoring." : "Simple mode uses Start, Turnpoint, and Goal only. Launch scores as Start, and ESS scores as Goal."}</p>
          </div>
          <div className="task-map-panel">
              <TaskBuilderMap
                selectedEventId={selectedEventId}
                selectedTaskId={selectedTaskId}
                turnpoints={taskSectionMapTurnpoints}
                airspaces={visibleAirspaces}
                taskPoints={taskDraft.points}
                optimizedRoute={taskDistanceMetrics.routeCoordinates}
                legMetrics={taskDistanceMetrics.legMetrics}
                totalDistanceKm={taskDistanceMetrics.totalDistanceKm}
                optimizedDistanceKm={taskDistanceMetrics.optimizedDistanceKm}
                track={track}
                editable={canManagePlatform}
                onSelectTurnpoint={canManagePlatform ? addTurnpoint : undefined}
                taskEditorOverlay={fullscreenTaskEditor}
                hideFullscreenDistanceOverlay={canManagePlatform}
                units={{
                  altitude: settingsForm.altitude_unit,
                  speed: settingsForm.speed_unit,
                  distance: settingsForm.distance_unit,
                  vario: settingsForm.vario_unit,
                }}
              />
            </div>
          </div>
      </div>
    </SectionCard>
  </div>
  );
}
