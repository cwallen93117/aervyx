"use client";

import { TaskMap, type MapAirspaceRegion, type MapLegMetric, type MapTaskPoint, type MapTurnpoint, type MapUnitPreferences, type TrackCollection } from "./TaskMap";

export interface TaskBuilderMapProps {
  selectedEventId: number | null;
  selectedTaskId: number | null;
  turnpoints: MapTurnpoint[];
  airspaces?: MapAirspaceRegion[];
  taskPoints: MapTaskPoint[];
  optimizedRoute?: [number, number][];
  legMetrics?: MapLegMetric[];
  totalDistanceKm?: number;
  optimizedDistanceKm?: number;
  track?: TrackCollection | null;
  editable?: boolean;
  onSelectTurnpoint?: (turnpoint: MapTurnpoint) => void;
  taskEditorOverlay?: React.ReactNode;
  hideFullscreenDistanceOverlay?: boolean;
  units?: MapUnitPreferences;
  overlayConfig?: Record<string, boolean>;
}

export function TaskBuilderMap({
  selectedEventId,
  selectedTaskId,
  turnpoints,
  airspaces = [],
  taskPoints,
  optimizedRoute = [],
  legMetrics = [],
  totalDistanceKm = 0,
  optimizedDistanceKm = 0,
  track = null,
  editable = false,
  onSelectTurnpoint,
  taskEditorOverlay,
  hideFullscreenDistanceOverlay = false,
  units,
  overlayConfig,
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
      totalDistanceKm={totalDistanceKm}
      optimizedDistanceKm={optimizedDistanceKm}
      track={track}
      editable={editable}
      onSelectTurnpoint={onSelectTurnpoint}
      taskEditorOverlay={taskEditorOverlay}
      hideFullscreenDistanceOverlay={hideFullscreenDistanceOverlay}
      fitKey={selectedTaskId}
      viewStateKey={viewStateKey}
      units={units}
      overlayConfig={overlayConfig}
    />
  );
}

export default TaskBuilderMap;
