"use client";
import AirspaceExplorerMap from "./AirspaceExplorerMap";

export function AirspaceSection({ overlayConfig, refreshToken }: { overlayConfig?: Record<string, boolean>; refreshToken?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <AirspaceExplorerMap overlayConfig={overlayConfig} refreshToken={refreshToken} />
    </div>
  );
}
