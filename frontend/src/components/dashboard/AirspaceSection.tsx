"use client";
import AirspaceExplorerMap from "./AirspaceExplorerMap";

export function AirspaceSection({
  overlayConfig,
  refreshToken,
  tfrRefreshToken,
  selectedTfrTime,
  maxPitchDegrees,
}: {
  overlayConfig?: Record<string, boolean>;
  refreshToken?: number;
  tfrRefreshToken?: number;
  selectedTfrTime?: string;
  maxPitchDegrees?: number;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <AirspaceExplorerMap
        overlayConfig={overlayConfig}
        refreshToken={refreshToken}
        tfrRefreshToken={tfrRefreshToken}
        selectedTfrTime={selectedTfrTime}
        maxPitchDegrees={maxPitchDegrees}
      />
    </div>
  );
}
