"use client";

import type { CSSProperties, KeyboardEvent, ReactNode } from "react";
import type { MapLegMetric, MapTurnpoint } from "../TaskMap";
import type { AccountSettingsRecord, TaskPointRecord } from "./types";

const pointTypeLabels: Record<string, string> = {
  launch: "Launch",
  start: "Start",
  turnpoint: "Turnpoint",
  ESS: "ESS",
  goal: "Goal",
};

const pointDirectionLabels: Record<string, string> = {
  enter: "Enter",
  exit: "Exit",
};

const pointDirectionOptions = [
  { value: "enter", label: "Enter" },
  { value: "exit", label: "Exit" },
] as const;

export type TaskDistanceMetrics = {
  totalDistanceKm: number;
  optimizedDistanceKm: number;
  routeCoordinates: [number, number][];
  legMetrics: MapLegMetric[];
};

type EditableTaskTurnpointsTableProps = {
  editable: true;
  taskPointTypeOptions: Array<{ value: string; label: string }>;
  onTaskPointAdvancedChange: (checked: boolean) => void;
  updatePoint: (index: number, patch: Partial<TaskPointRecord>) => void;
  removePoint: (index: number) => void;
  movePoint: (fromIndex: number, toIndex: number) => void;
  handleRadiusInputChange: (index: number, point: TaskPointRecord, rawValue: string) => void;
  handleRadiusInputBlur: (index: number, point: TaskPointRecord) => void;
  handleRadiusInputKeyDown: (event: KeyboardEvent<HTMLInputElement>, index: number, point: TaskPointRecord) => void;
  radiusInputValue: (index: number, point: TaskPointRecord) => string;
};

type ReadonlyTaskTurnpointsTableProps = {
  editable?: false;
};

type SharedTaskTurnpointsTableProps = {
  points: TaskPointRecord[];
  taskPointAdvanced?: boolean;
  turnpoints: MapTurnpoint[];
  taskDistanceMetrics: TaskDistanceMetrics;
  distanceUnit: AccountSettingsRecord["distance_unit"];
  collapsed?: boolean;
  contentId?: string;
  titleAction?: ReactNode;
  emptyMessage?: string;
};

export type TaskTurnpointsTableProps = SharedTaskTurnpointsTableProps &
  (EditableTaskTurnpointsTableProps | ReadonlyTaskTurnpointsTableProps);

function toSimplePointType(pointType: string): string {
  if (pointType === "launch") return "start";
  if (pointType === "ESS") return "goal";
  return pointType;
}

function formatMeters(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(Math.max(0, Math.round(value || 0)));
}

export function formatTaskDistance(valueKm: number, unit: AccountSettingsRecord["distance_unit"]): string {
  const normalizedValue = Number.isFinite(valueKm) ? valueKm : 0;
  const displayValue = unit === "mi" ? normalizedValue * 0.621371 : normalizedValue;
  return `${displayValue.toFixed(1)} ${unit}`;
}

export function TaskTurnpointsTable(props: TaskTurnpointsTableProps) {
  const {
    points,
    taskPointAdvanced = false,
    turnpoints,
    taskDistanceMetrics,
    distanceUnit,
    collapsed = false,
    contentId,
    titleAction,
    emptyMessage = "No task turnpoints available.",
  } = props;
  const editable = props.editable === true;
  const gridClassName = `task-point-list-grid-header${editable ? " has-actions" : ""}`;
  const scrollClassName = `task-point-list-scroll${editable ? " has-actions" : ""}`;
  const nameColumnCharacters = Math.max(
    "Name".length,
    ...points.flatMap((point) => {
      const waypointCode = turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code;
      return [point.name.length, waypointCode?.length ?? 0];
    }),
  );
  const panelStyle = {
    "--task-name-column-width": `${Math.max(8, nameColumnCharacters + 1)}ch`,
  } as CSSProperties;

  return (
    <div className={`task-turnpoints-panel${collapsed ? " is-collapsed" : ""}`} style={panelStyle}>
      <div className="section-header task-turnpoints-panel-header">
        <div className="task-turnpoints-panel-title-row">
          <h3>Task turnpoints</h3>
          {titleAction}
        </div>
        {!collapsed && props.editable ? (
          <div className="task-turnpoint-toolbar">
            <label className="task-advanced-toggle">
              <input type="checkbox" checked={taskPointAdvanced} onChange={(event) => props.onTaskPointAdvancedChange(event.target.checked)} />
              <span>Advanced</span>
            </label>
          </div>
        ) : null}
      </div>
      <div id={contentId} className="task-turnpoints-panel-body" hidden={collapsed}>
        <div className="task-turnpoints-distance-summary" aria-label="Task distance summary">
          <span>
            <strong>Total</strong>
            {formatTaskDistance(taskDistanceMetrics.totalDistanceKm, distanceUnit)}
          </span>
          <span>
            <strong>Optimized</strong>
            {formatTaskDistance(taskDistanceMetrics.optimizedDistanceKm, distanceUnit)}
          </span>
        </div>
        <div className="task-point-list-table-wrap">
          {points.length ? (
            <>
              <div className={gridClassName}>
                <span></span>
                <span>Name</span>
                <span>Type</span>
                <span>Direction</span>
                <span>Radius (m)</span>
                <span className="task-point-distance-heading">
                  <strong>Distance</strong>
                  <em>(optimized)</em>
                </span>
                {editable ? <span></span> : null}
              </div>
              <div className={scrollClassName}>
                {points.map((point, index) => {
                  const waypointCode = turnpoints.find((turnpoint) => turnpoint.id === point.turnpoint_id)?.code;
                  const legMetric = index > 0 ? taskDistanceMetrics.legMetrics[index - 1] ?? null : null;
                  const legDistanceKm = legMetric?.centerDistanceKm ?? null;
                  const optimizedLegDistanceKm = legMetric?.optimizedDistanceKm ?? null;
                  return (
                    <div
                      key={`compact-${point.turnpoint_id ?? point.name}-${index}`}
                      className={`task-point-list-grid-row point-type-${point.point_type.toLowerCase()}${editable ? " has-actions" : ""}`}
                      draggable={editable}
                      onDragStart={props.editable ? (event) => event.dataTransfer.setData("text/plain", String(index)) : undefined}
                      onDragOver={props.editable ? (event) => event.preventDefault() : undefined}
                      onDrop={
                        props.editable
                          ? (event) => {
                              event.preventDefault();
                              props.movePoint(Number(event.dataTransfer.getData("text/plain")), index);
                            }
                          : undefined
                      }
                    >
                      <div className="task-point-row-order">
                        <span className="drag-handle" title={editable ? "Drag to reorder" : undefined}>
                          {point.position}.{editable ? " :::" : ""}
                        </span>
                      </div>
                      <div className="task-point-row-name">
                        <strong>{point.name}</strong>
                        {waypointCode ? <span>{waypointCode}</span> : null}
                      </div>
                      <div className="task-point-row-type">
                        {props.editable ? (
                          <select value={taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)} onChange={(event) => props.updatePoint(index, { point_type: event.target.value })}>
                            {props.taskPointTypeOptions.map((option) => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                        ) : (
                          <span className="task-point-type-badge">{pointTypeLabels[taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type)] ?? (taskPointAdvanced ? point.point_type : toSimplePointType(point.point_type))}</span>
                        )}
                      </div>
                      <div className="task-point-row-direction">
                        {props.editable ? (
                          <select value={point.direction ?? "enter"} onChange={(event) => props.updatePoint(index, { direction: event.target.value as "enter" | "exit" })}>
                            {pointDirectionOptions.map((option) => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>
                        ) : (
                          <span className="task-point-type-badge">{pointDirectionLabels[point.direction ?? "enter"] ?? point.direction}</span>
                        )}
                      </div>
                      <div className="task-point-row-radius">
                        {props.editable ? (
                          <input
                            type="text"
                            inputMode="numeric"
                            value={props.radiusInputValue(index, point)}
                            onFocus={(event) => event.currentTarget.select()}
                            onChange={(event) => props.handleRadiusInputChange(index, point, event.target.value)}
                            onBlur={() => props.handleRadiusInputBlur(index, point)}
                            onKeyDown={(event) => props.handleRadiusInputKeyDown(event, index, point)}
                            placeholder="400"
                            aria-label={`Radius in meters for ${point.name}`}
                          />
                        ) : (
                          <span>{formatMeters(point.radius_m)}</span>
                        )}
                      </div>
                      <div className="task-point-row-distance">
                        <div className="task-point-distance-stack">
                          <strong>{legDistanceKm === null ? <span className="task-point-distance-empty">-</span> : formatTaskDistance(legDistanceKm, distanceUnit)}</strong>
                          <span className="task-point-distance-secondary">
                            ({optimizedLegDistanceKm === null ? "-" : formatTaskDistance(optimizedLegDistanceKm, distanceUnit)})
                          </span>
                        </div>
                      </div>
                      {props.editable ? (
                        <div className="task-point-row-actions">
                          <button type="button" className="ghost-button danger-button" onClick={() => props.removePoint(index)}>Remove</button>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <p className="task-point-list-empty">{emptyMessage}</p>
          )}
        </div>
      </div>
    </div>
  );
}
