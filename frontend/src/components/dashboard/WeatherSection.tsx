"use client";
import { SoaringForecastMap } from "./SoaringForecastMap";

export function WeatherSection({ units, overlayConfig }: { units: { altitude: "ft" | "m"; vario: "fpm" | "ms" }; overlayConfig?: Record<string, boolean> }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <SoaringForecastMap units={units} overlayConfig={overlayConfig} />
    </div>
  );
}
