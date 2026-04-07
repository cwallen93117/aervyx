"use client";
import { SoaringForecastMap } from "./SoaringForecastMap";

export function WeatherSection({ units }: { units: { altitude: "ft" | "m"; vario: "fpm" | "ms" } }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <SoaringForecastMap units={units} />
    </div>
  );
}
