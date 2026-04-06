"use client";
import AirspaceExplorerMap from "./AirspaceExplorerMap";

export function AirspaceSection() {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <AirspaceExplorerMap />
    </div>
  );
}
