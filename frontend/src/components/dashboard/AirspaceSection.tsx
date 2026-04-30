"use client";
import AirspaceExplorerMap from "./AirspaceExplorerMap";

export function AirspaceSection({
  overlayConfig,
  refreshToken,
  tfrRefreshToken,
  selectedTfrTime,
}: {
  overlayConfig?: Record<string, boolean>;
  refreshToken?: number;
  tfrRefreshToken?: number;
  selectedTfrTime?: string;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <AirspaceExplorerMap
        overlayConfig={overlayConfig}
        refreshToken={refreshToken}
        tfrRefreshToken={tfrRefreshToken}
        selectedTfrTime={selectedTfrTime}
      />
    </div>
  );
}
