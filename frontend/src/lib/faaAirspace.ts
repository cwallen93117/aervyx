/**
 * FAA Airspace data — fetched from our backend cache (which syncs from FAA ArcGIS).
 * Backend: GET /api/faa-airspace/features?west=&south=&east=&north=&categories=
 */

// ---------------------------------------------------------------------------
// API base resolution (same pattern as page.tsx)
// ---------------------------------------------------------------------------

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") {
    if (configured) {
      try {
        const parsed = new URL(configured);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
          return `${window.location.protocol}//${window.location.hostname}:${parsed.port || "8000"}`;
        }
      } catch {
        return configured;
      }
      return configured;
    }
    return "/backend";
  }
  return configured ?? "/backend";
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AirspaceCategory = "B" | "C" | "D" | "E" | "MODE-C" | "P" | "R" | "W" | "A" | "MOA" | "TFR";

export interface AirspaceProperties {
  /** Normalized display category */
  category: AirspaceCategory;
  name: string;
  ident?: string;
  upperVal: number | null;
  upperUom: string;
  lowerVal: number | null;
  lowerUom: string;
  upperDesc: string;
  lowerDesc: string;
  city?: string;
  state?: string;
  /** "class" for controlled, "sua" for special-use, "tfr" for defense TFRs */
  source: "class" | "sua" | "tfr";
}

type GeoJSONFeature = GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon, AirspaceProperties>;
type GeoJSONFC = GeoJSON.FeatureCollection<GeoJSON.Polygon | GeoJSON.MultiPolygon, AirspaceProperties>;

// ---------------------------------------------------------------------------
// Category colors (matches TaskMap.tsx palette)
// ---------------------------------------------------------------------------

export const CATEGORY_COLORS: Record<AirspaceCategory, string> = {
  B: "#2563eb",
  C: "#f59e0b",
  D: "#14b8a6",
  E: "#6366f1",
  "MODE-C": "#94a3b8",
  P: "#dc2626",
  R: "#7c3aed",
  W: "#ea580c",
  A: "#db2777",
  MOA: "#0ea5e9",
  TFR: "#dc2626",
};

export const CATEGORY_LABELS: Record<AirspaceCategory, string> = {
  B: "Class B",
  C: "Class C",
  D: "Class D",
  E: "Class E",
  "MODE-C": "Mode C",
  P: "Prohibited",
  R: "Restricted",
  W: "Warning",
  A: "Alert",
  MOA: "MOA",
  TFR: "TFR",
};

// ---------------------------------------------------------------------------
// Bounds type
// ---------------------------------------------------------------------------

interface BoundsBox {
  west: number;
  south: number;
  east: number;
  north: number;
}

// ---------------------------------------------------------------------------
// Internal: fetch from backend cache
// ---------------------------------------------------------------------------

async function fetchFromBackend(
  bounds: BoundsBox,
  categories: string,
  signal?: AbortSignal,
): Promise<GeoJSONFC> {
  const api = resolveApiBase();
  const params = new URLSearchParams({
    west: String(bounds.west),
    south: String(bounds.south),
    east: String(bounds.east),
    north: String(bounds.north),
    categories,
  });
  const resp = await fetch(`${api}/api/faa-airspace/features?${params}`, { signal });
  if (!resp.ok) throw new Error(`Airspace API failed: ${resp.status}`);
  return resp.json();
}

// ---------------------------------------------------------------------------
// Public API (same signatures — AirspaceExplorerMap needs no changes)
// ---------------------------------------------------------------------------

export async function fetchClassAirspace(bounds: BoundsBox, signal?: AbortSignal): Promise<GeoJSONFC> {
  return fetchFromBackend(bounds, "B,C,D", signal);
}

export async function fetchSpecialUseAirspace(bounds: BoundsBox, signal?: AbortSignal): Promise<GeoJSONFC> {
  return fetchFromBackend(bounds, "P,R,W,A,MOA", signal);
}

export async function fetchTFRs(signal?: AbortSignal): Promise<GeoJSONFC> {
  // Global bbox for TFRs
  return fetchFromBackend({ west: -180, south: -90, east: 180, north: 90 }, "TFR", signal);
}

// ---------------------------------------------------------------------------
// OpenAir export
// ---------------------------------------------------------------------------

function decimalToDMS(dec: number, isLon: boolean): string {
  const abs = Math.abs(dec);
  const d = Math.floor(abs);
  const mFloat = (abs - d) * 60;
  const m = Math.floor(mFloat);
  const s = Math.round((mFloat - m) * 60);
  const dir = isLon ? (dec >= 0 ? "E" : "W") : (dec >= 0 ? "N" : "S");
  const dPad = isLon ? String(d).padStart(3, "0") : String(d).padStart(2, "0");
  return `${dPad}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")} ${dir}`;
}

function categoryToOpenAirClass(cat: AirspaceCategory): string {
  switch (cat) {
    case "B": return "B";
    case "C": return "C";
    case "D": return "D";
    case "E": return "E";
    case "P": return "P";
    case "R": return "R";
    case "W": return "W";
    case "A": return "R"; // Alert → use R in OpenAir
    case "MOA": return "Q"; // MOA → Danger in OpenAir
    case "TFR": return "R";
    case "MODE-C": return "E";
  }
}

function formatAltitude(val: number | null, uom: string): string {
  if (val == null || val === 0) return "SFC";
  if (uom === "FL") return `FL${val}`;
  return `${val}${uom}`;
}

export function toOpenAir(features: GeoJSONFeature[]): string {
  const lines: string[] = [];

  for (const f of features) {
    const p = f.properties;
    lines.push(`AC ${categoryToOpenAirClass(p.category)}`);
    lines.push(`AN ${p.name}`);
    lines.push(`AH ${formatAltitude(p.upperVal, p.upperUom)}`);
    lines.push(`AL ${formatAltitude(p.lowerVal, p.lowerUom)}`);

    const coords = f.geometry.type === "Polygon"
      ? f.geometry.coordinates[0]
      : f.geometry.coordinates[0]?.[0] ?? [];

    for (const [lon, lat] of coords) {
      lines.push(`DP ${decimalToDMS(lat, false)} ${decimalToDMS(lon, true)}`);
    }

    lines.push("");
  }

  return lines.join("\n");
}

export function downloadOpenAir(features: GeoJSONFeature[], filename = "airspace.txt"): void {
  const text = toOpenAir(features);
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
