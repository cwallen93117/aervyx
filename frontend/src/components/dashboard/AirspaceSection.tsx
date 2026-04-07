"use client";
import AirspaceExplorerMap from "./AirspaceExplorerMap";

export function AirspaceSection({ overlayConfig }: { overlayConfig?: Record<string, boolean> }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <AirspaceExplorerMap overlayConfig={overlayConfig} />
    </div>
  );
}
