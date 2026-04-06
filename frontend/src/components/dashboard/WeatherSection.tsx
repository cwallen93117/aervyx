"use client";
import { SoaringForecastMap } from "./SoaringForecastMap";

export function WeatherSection() {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <div className="content-hero">
        <h2>Soaring Forecast Lab</h2>
        <p style={{ color: "var(--muted)", marginTop: 4 }}>
          Evaluate thermal, lift, and wind overlays across 5 NWP models before integrating into task maps.
          Click anywhere on the map for a multi-model point comparison.
        </p>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <SoaringForecastMap />
      </div>
    </div>
  );
}
