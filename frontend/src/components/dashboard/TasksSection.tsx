"use client";

import type { KeyboardEvent } from "react";
import { SectionCard } from "../SectionCard";
import { type MapAirspaceRegion, type MapLegMetric, type MapTurnpoint, type TaskEditorOverlayRenderProps, type TrackCollection } from "../TaskMap";
import { TaskBuilderMap } from "../TaskBuilderMap";
import { TaskTurnpointsTable } from "./TaskTurnpointsTable";
import { sortTasksByDateAsc } from "./taskSorting";
import type { AccountSettingsRecord, TaskDraftState, TaskPointRecord, TaskRecord } from "./types";

const taskTypeOptions = [
  { value: "race_to_goal_with_gates", label: "Race to Goal" },
  { value: "elapsed_time", label: "Elapsed Time" },
  { value: "open_distance", label: "Open Distance" },
] as const;

function taskTypeLabel(value: string | null | undefined): string {
  return taskTypeOptions.find((option) => option.value === value)?.label ?? "Not set";
}

function displayTaskValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "Not set";
  return String(value);
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
  duplicateTask: () => void;
  handleRadiusInputChange: (index: number, point: TaskPointRecord, rawValue: string) => void;
  handleRadiusInputBlur: (index: number, point: TaskPointRecord) => void;
  handleRadiusInputKeyDown: (event: KeyboardEvent<HTMLInputElement>, index: number, point: TaskPointRecord) => void;
  radiusInputValue: (index: number, point: TaskPointRecord) => string;
  overlayConfig?: Record<string, boolean>;
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
    duplicateTask,
    handleRadiusInputChange,
    handleRadiusInputBlur,
    handleRadiusInputKeyDown,
    radiusInputValue,
    overlayConfig,
  } = props;
  const sortedTasks = sortTasksByDateAsc(tasks);
  if (!selectedEventId) {
    return canManagePlatform ? (
      <SectionCard title="Tasks" description="Create or select an event first.">
        <p className="hint">Tasks need an event context before they can be built.</p>
      </SectionCard>
    ) : (
      <SectionCard title="Tasks" description="No competition selected.">
        <p className="hint">Choose an available competition from the Tasks header. If none are listed, no competitions are visible to this account yet.</p>
      </SectionCard>
    );
  }
  const usesGatedStart = currentTaskTypeBehavior.usesMultipleGates;
  const taskIsPublished = selectedTask?.status === "published";
  const canEditStartWindow = canManagePlatform && currentTaskTypeBehavior.usesStartWindow;
  const canEditTaskFinish = canManagePlatform;
  const canEditStartGates = canManagePlatform && currentTaskTypeBehavior.usesMultipleGates;
  const startGateTimesLabel = `Start gate times (${startGateLabels.length})`;
  const pilotTaskSetupRows = [
    { label: "Task name", value: displayTaskValue(taskDraft.name) },
    { label: "Task date", value: displayTaskValue(taskDraft.task_date) },
    { label: "Task type", value: taskTypeLabel(taskDraft.task_type) },
  ];
  const showTimingAndGates = canManagePlatform || usesGatedStart;
  const fullscreenTaskEditor = ({ collapsed, contentId, overlayId, toggleButton }: TaskEditorOverlayRenderProps) => (
    <div id={overlayId} className={`map-task-editor${collapsed ? " is-collapsed" : ""}`}>
      {canManagePlatform ? (
        <TaskTurnpointsTable
          points={taskDraft.points}
          taskPointAdvanced={taskPointAdvanced}
          onTaskPointAdvancedChange={toggleTaskPointAdvanced}
          taskPointTypeOptions={taskPointTypeOptions}
          turnpoints={turnpoints}
          taskDistanceMetrics={taskDistanceMetrics}
          distanceUnit={settingsForm.distance_unit}
          editable
          collapsed={collapsed}
          contentId={contentId}
          titleAction={toggleButton}
          updatePoint={updatePoint}
          removePoint={removePoint}
          movePoint={movePoint}
          handleRadiusInputChange={handleRadiusInputChange}
          handleRadiusInputBlur={handleRadiusInputBlur}
          handleRadiusInputKeyDown={handleRadiusInputKeyDown}
          radiusInputValue={radiusInputValue}
          emptyMessage="No turnpoints selected yet. Click waypoint markers on the map to add them to this task."
        />
      ) : (
        <TaskTurnpointsTable
          points={taskDraft.points}
          taskPointAdvanced={taskPointAdvanced}
          turnpoints={turnpoints}
          taskDistanceMetrics={taskDistanceMetrics}
          distanceUnit={settingsForm.distance_unit}
          collapsed={collapsed}
          contentId={contentId}
          titleAction={toggleButton}
        />
      )}
      {canManagePlatform ? (
        <div className="map-task-editor-body" hidden={collapsed}>
          <div className="map-task-editor-footer">
            <div className="map-task-editor-footer-row">
              <button type="button" className="map-task-editor-save" onClick={saveTask}>
                Save task
              </button>
            </div>
            {taskFeedback ? <div className={`status-chip ${taskFeedback.type} map-task-editor-feedback`}>{taskFeedback.text}</div> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
  return (
    <div className="section-stack">
    <SectionCard>
      <div className="stack form-block compact-clusters">
        <div className="task-toolbar">
          {canManagePlatform ? (
            <>
              <label className="stack compact task-toolbar-picker">
                <span>Selected task</span>
                <select value={selectedTaskId ?? ""} onChange={(event) => { const nextId = Number(event.target.value); const nextTask = sortedTasks.find((task) => task.id === nextId); if (nextTask) void loadTask(token, nextId, nextTask, activeSection === "scoring"); }}>
                  <option value="">Select a task</option>
                  {sortedTasks.map((task) => <option key={task.id} value={task.id}>{task.name} - {task.status}</option>)}
                </select>
              </label>
              <button type="button" className="ghost-button" onClick={startNewTask}>New task</button>
              <button type="button" className="ghost-button" onClick={duplicateTask} disabled={!taskDraft.id}>Duplicate</button>
              <button type="button" className="primary-button" onClick={saveTask}>Save task</button>
              <button
                type="button"
                className={`scoring-ops-footer-btn task-state-toggle ${taskIsPublished ? "state-official" : "state-unofficial"}`}
                onClick={taskIsPublished ? unpublishTask : publishTask}
                disabled={!taskDraft.id}
              >
                {taskIsPublished ? "Published" : "Unpublished"}
              </button>
              <button type="button" className="ghost-button danger-button task-delete-button task-toolbar-delete" onClick={deleteTask} disabled={!taskDraft.id}>Delete task</button>
            </>
          ) : (
            <div className="scoring-nav pilot-task-nav" aria-label="Select task">
              {sortedTasks.length ? sortedTasks.map((task, index) => (
                <button
                  key={task.id}
                  type="button"
                  className={selectedTaskId === task.id ? "scoring-nav-btn active" : "scoring-nav-btn"}
                  onClick={() => void loadTask(token, task.id, task, activeSection === "scoring")}
                >
                  {task.name || `Task ${index + 1}`}
                </button>
              )) : <span className="pilot-task-nav-empty">No tasks available</span>}
            </div>
          )}
        </div>
        {canManagePlatform && taskFeedback ? <div className={`status-chip ${taskFeedback.type} task-toolbar-feedback`}>{taskFeedback.text}</div> : null}
        <div className="fieldset-grid two-up task-setup-grid">
          <fieldset className="fieldset-cluster">
            <legend>Task setup</legend>
            {canManagePlatform ? (
              <div className="cluster-stack">
                <label className="stack compact">
                  <span>Task name</span>
                  <input value={taskDraft.name} onChange={(event) => setTaskDraft({ ...taskDraft, name: event.target.value })} placeholder="Task name" disabled={!canManagePlatform} />
                </label>
                <label className="stack compact">
                  <span>Task date</span>
                  <input type="date" value={taskDraft.task_date} onChange={(event) => setTaskDraft({ ...taskDraft, task_date: event.target.value })} disabled={!canManagePlatform} />
                </label>
                <label className="stack compact">
                  <span>Task type</span>
                  <select value={taskDraft.task_type} onChange={(event) => setTaskDraft({ ...taskDraft, task_type: event.target.value })} disabled={!canManagePlatform}>
                    {taskTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
              </div>
            ) : (
              <div className="task-readonly-list">
                {pilotTaskSetupRows.map((row) => (
                  <div key={row.label} className="task-readonly-row">
                    <span>{row.label}</span>
                    <strong>{row.value}</strong>
                  </div>
                ))}
              </div>
            )}
          </fieldset>

          {showTimingAndGates ? (
            <fieldset className="fieldset-cluster">
              <legend>Timing and gates</legend>
              {canManagePlatform ? (
                <div className="fieldset-grid two-up task-timing-layout">
                  {usesGatedStart ? (
                    <>
                      <div className="cluster-stack">
                        <label className={canEditStartWindow ? "stack compact" : "stack compact field-disabled"}>
                          <span>Start open</span>
                          <input type="time" step={60} value={taskDraft.start_open_time} onChange={(event) => setTaskDraft({ ...taskDraft, start_open_time: event.target.value })} disabled={!canEditStartWindow} />
                        </label>
                        <label className={canEditStartWindow ? "stack compact" : "stack compact field-disabled"}>
                          <span>Start close</span>
                          <input type="time" step={60} value={taskDraft.start_close_time} onChange={(event) => setTaskDraft({ ...taskDraft, start_close_time: event.target.value })} disabled={!canEditStartWindow} />
                        </label>
                        <label className={canEditTaskFinish ? "stack compact" : "stack compact field-disabled"}>
                          <span>Task finish</span>
                          <input type="time" step={60} value={taskDraft.task_finish_time} onChange={(event) => setTaskDraft({ ...taskDraft, task_finish_time: event.target.value })} disabled={!canEditTaskFinish} />
                        </label>
                      </div>
                      {canManagePlatform || startGateLabels.length ? (
                        <div className="cluster-stack task-gate-settings">
                          <label className={canEditStartGates ? "stack compact" : "stack compact field-disabled"}>
                            <span>Start gates</span>
                            <input type="number" min={1} value={taskDraft.start_gate_count} onChange={(event) => setTaskDraft({ ...taskDraft, start_gate_count: Math.max(1, Number(event.target.value) || 1) })} disabled={!canEditStartGates} />
                          </label>
                          <label className={canEditStartGates ? "stack compact" : "stack compact field-disabled"}>
                            <span>Gate interval (min)</span>
                            <input type="number" min={0} value={taskDraft.start_gate_interval_minutes} onChange={(event) => setTaskDraft({ ...taskDraft, start_gate_interval_minutes: event.target.value === "" ? "" : Math.max(0, Number(event.target.value) || 0) })} disabled={!canEditStartGates} />
                          </label>
                        </div>
                      ) : null}
                      <div className="task-gate-times" aria-label="Start gate times">
                        <strong>{startGateTimesLabel}</strong>
                        <div className="task-gate-time-list">
                          {startGateLabels.length ? startGateLabels.map((label) => (
                            <span key={label} className="task-gate-time-chip">{label}</span>
                          )) : <span className="task-readonly-empty">Set Start open to preview gate times.</span>}
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="cluster-stack">
                        <label className="stack compact">
                          <span>Task start</span>
                          <input type="time" step={60} value={taskDraft.task_start_time} onChange={(event) => setTaskDraft({ ...taskDraft, task_start_time: event.target.value })} disabled={!canManagePlatform} />
                        </label>
                        <label className="stack compact">
                          <span>Start close</span>
                          <input type="time" step={60} value={taskDraft.start_close_time} onChange={(event) => setTaskDraft({ ...taskDraft, start_close_time: event.target.value })} disabled={!canManagePlatform} />
                        </label>
                      </div>
                      <div className="cluster-stack">
                        <label className="stack compact">
                          <span>Task finish</span>
                          <input type="time" step={60} value={taskDraft.task_finish_time} onChange={(event) => setTaskDraft({ ...taskDraft, task_finish_time: event.target.value })} disabled={!canManagePlatform} />
                        </label>
                      </div>
                    </>
                  )}
                </div>
              ) : (
                <div className="task-readonly-list task-readonly-list-gates-only">
                  <div className="task-gate-times task-readonly-gates" aria-label="Start gate times">
                    <strong>{startGateTimesLabel}</strong>
                    <div className="task-gate-time-list">
                      {startGateLabels.length ? startGateLabels.map((label) => (
                        <span key={label} className="task-gate-time-chip">{label}</span>
                      )) : <span className="task-readonly-empty">Not set</span>}
                    </div>
                  </div>
                </div>
              )}
            </fieldset>
          ) : null}
        </div>
        <div className="task-builder-layout">
            <div className="task-turnpoint-rail">
              {canManagePlatform ? (
                <TaskTurnpointsTable
                  points={taskDraft.points}
                  taskPointAdvanced={taskPointAdvanced}
                  onTaskPointAdvancedChange={toggleTaskPointAdvanced}
                  taskPointTypeOptions={taskPointTypeOptions}
                  turnpoints={turnpoints}
                  taskDistanceMetrics={taskDistanceMetrics}
                  distanceUnit={settingsForm.distance_unit}
                  editable
                  updatePoint={updatePoint}
                  removePoint={removePoint}
                  movePoint={movePoint}
                  handleRadiusInputChange={handleRadiusInputChange}
                  handleRadiusInputBlur={handleRadiusInputBlur}
                  handleRadiusInputKeyDown={handleRadiusInputKeyDown}
                  radiusInputValue={radiusInputValue}
                  emptyMessage="No turnpoints selected yet. Click waypoint markers on the map to add them to this task."
                />
              ) : (
                <TaskTurnpointsTable
                  points={taskDraft.points}
                  taskPointAdvanced={taskPointAdvanced}
                  turnpoints={turnpoints}
                  taskDistanceMetrics={taskDistanceMetrics}
                  distanceUnit={settingsForm.distance_unit}
                />
              )}
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
                track={track}
                editable={canManagePlatform}
                onSelectTurnpoint={canManagePlatform ? addTurnpoint : undefined}
                taskEditorOverlay={fullscreenTaskEditor}
                units={{
                  altitude: settingsForm.altitude_unit,
                  speed: settingsForm.speed_unit,
                  distance: settingsForm.distance_unit,
                  vario: settingsForm.vario_unit,
                }}
                overlayConfig={overlayConfig}
              />
            </div>
          </div>
      </div>
    </SectionCard>
  </div>
  );
}
