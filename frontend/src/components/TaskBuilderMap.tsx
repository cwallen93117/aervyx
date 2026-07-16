"use client";

import { TaskMap, type MapAirspaceRegion, type MapLegMetric, type MapTaskPoint, type MapTelemetrySmoothing, type MapTurnpoint, type MapUnitPreferences, type TaskEditorOverlayContent, type TrackCollection } from "./TaskMap";
import type { AirspaceCategory } from "../lib/faaAirspace";

export interface TaskBuilderMapProps {
  selectedEventId: number | null;
  selectedTaskId: number | null;
  turnpoints: MapTurnpoint[];
  airspaces?: MapAirspaceRegion[];
  taskPoints: MapTaskPoint[];
  optimizedRoute?: [number, number][];
  legMetrics?: MapLegMetric[];
  track?: TrackCollection | null;
  editable?: boolean;
  onSelectTurnpoint?: (turnpoint: MapTurnpoint) => void;
  taskEditorOverlay?: TaskEditorOverlayContent;
  units?: MapUnitPreferences;
  telemetrySmoothing?: MapTelemetrySmoothing;
  overlayConfig?: Record<string, boolean>;
  faaAirspaceCategories?: AirspaceCategory[];
}

export function TaskBuilderMap({
  selectedEventId,
  selectedTaskId,
  turnpoints,
  airspaces = [],
  taskPoints,
  optimizedRoute = [],
  legMetrics = [],
  track = null,
  editable = false,
  onSelectTurnpoint,
  taskEditorOverlay,
  units,
  telemetrySmoothing,
  overlayConfig,
  faaAirspaceCategories,
}: TaskBuilderMapProps) {
  const viewStateKey = `tasks-${selectedEventId ?? "none"}-${selectedTaskId ?? "draft"}`;

  return (
    <TaskMap
      key={`task-builder-${selectedEventId ?? "none"}-${selectedTaskId ?? "draft"}`}
      turnpoints={turnpoints}
      airspaces={airspaces}
      taskPoints={taskPoints}
      optimizedRoute={optimizedRoute}
      legMetrics={legMetrics}
      track={track}
      editable={editable}
      onSelectTurnpoint={onSelectTurnpoint}
      taskEditorOverlay={taskEditorOverlay}
      fitKey={selectedTaskId}
      viewStateKey={viewStateKey}
      units={units}
      telemetrySmoothing={telemetrySmoothing}
      overlayConfig={overlayConfig}
      faaAirspaceCategories={faaAirspaceCategories}
    />
  );
}

export default TaskBuilderMap;
