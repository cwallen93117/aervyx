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
export const CLASS_AIRSPACE_CATEGORIES: AirspaceCategory[] = ["B", "C", "D"];
export const SPECIAL_USE_AIRSPACE_CATEGORIES: AirspaceCategory[] = ["P", "R", "W", "A", "MOA"];
export const TFR_AIRSPACE_CATEGORIES: AirspaceCategory[] = ["TFR"];
export const DEFAULT_AIRSPACE_CATEGORIES: AirspaceCategory[] = [
  ...CLASS_AIRSPACE_CATEGORIES,
  ...SPECIAL_USE_AIRSPACE_CATEGORIES,
  ...TFR_AIRSPACE_CATEGORIES,
];

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
  notamId?: string | null;
  effectiveStart?: string | null;
  effectiveEnd?: string | null;
  noticeTime?: string | null;
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

/** Fetch all airspace (class + SUA) in a single request */
export async function fetchAllAirspace(bounds: BoundsBox, signal?: AbortSignal): Promise<GeoJSONFC> {
  return fetchFromBackend(bounds, "B,C,D,P,R,W,A,MOA", signal);
}

export async function fetchAirspaceCategories(
  bounds: BoundsBox,
  categories: AirspaceCategory[],
  signal?: AbortSignal,
): Promise<GeoJSONFC> {
  const selected = normalizeAirspaceCategories(categories);
  if (!selected.length) return { type: "FeatureCollection", features: [] };
  return fetchFromBackend(bounds, selected.join(","), signal);
}

export function normalizeAirspaceCategories(value: unknown): AirspaceCategory[] {
  if (!Array.isArray(value)) return [...DEFAULT_AIRSPACE_CATEGORIES];
  const allowed = new Set(DEFAULT_AIRSPACE_CATEGORIES);
  const normalized: AirspaceCategory[] = [];
  for (const item of value) {
    if (typeof item !== "string") continue;
    const candidate = item.trim().toUpperCase() as AirspaceCategory;
    if (allowed.has(candidate) && !normalized.includes(candidate)) {
      normalized.push(candidate);
    }
  }
  return normalized;
}

// ---------------------------------------------------------------------------
// OpenAir export — follows Naviter OpenAir 2.1 spec
// https://github.com/naviter/seeyou_file_formats/blob/main/OpenAir_File_Format_Support.md
// ---------------------------------------------------------------------------

/** Convert decimal degrees to DMS string: DD:MM:SS N/S or DDD:MM:SS E/W */
function decimalToDMS(dec: number, isLon: boolean): string {
  const abs = Math.abs(dec);
  const d = Math.floor(abs);
  const mFloat = (abs - d) * 60;
  const m = Math.floor(mFloat);
  const s = Math.round((mFloat - m) * 60);
  const dir = isLon ? (dec >= 0 ? "E" : "W") : (dec >= 0 ? "N" : "S");
  const dPad = isLon ? String(d).padStart(3, "0") : String(d).padStart(2, "0");
  return `${dPad}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}${dir}`;
}

function fmtPoint(lat: number, lon: number): string {
  return `${decimalToDMS(lat, false)} ${decimalToDMS(lon, true)}`;
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
    case "A": return "R";
    case "MOA": return "Q";
    case "TFR": return "R";
    case "MODE-C": return "E";
  }
}

/** Format altitude per OpenAir spec */
function formatAltitude(val: number | null, uom: string, isUpper: boolean): string {
  if (isUpper && (val == null || val === 0)) return "UNL";
  if (!isUpper && (val == null || val === 0)) return "GND";
  if (uom === "FL") return `FL${val}`;
  return `${val}ft AMSL`;
}

// --- Circle detection ---

const NM_PER_DEG_LAT = 60; // 1 degree latitude ≈ 60 nm

/** Compute centroid of a ring of [lon, lat] coordinates */
function centroid(ring: number[][]): [number, number] {
  let sumLon = 0, sumLat = 0;
  // Exclude closing point if it duplicates first
  const n = (ring.length > 1 &&
    ring[0][0] === ring[ring.length - 1][0] &&
    ring[0][1] === ring[ring.length - 1][1])
    ? ring.length - 1 : ring.length;
  for (let i = 0; i < n; i++) {
    sumLon += ring[i][0];
    sumLat += ring[i][1];
  }
  return [sumLon / n, sumLat / n];
}

/** Haversine distance between two points in nautical miles */
function distNm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = Math.PI / 180;
  const dLat = (lat2 - lat1) * toRad;
  const dLon = (lon2 - lon1) * toRad;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2;
  return 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)) * 3440.065; // Earth radius in nm
}

/**
 * Detect if a polygon ring is approximately circular.
 * Returns { centerLat, centerLon, radiusNm } or null.
 * Tolerance: all vertices within 5% of the mean radius.
 */
function detectCircle(ring: number[][]): { centerLat: number; centerLon: number; radiusNm: number } | null {
  if (ring.length < 12) return null; // too few points to be a circle
  const [cLon, cLat] = centroid(ring);
  const distances = ring.map(([lon, lat]) => distNm(cLat, cLon, lat, lon));
  const mean = distances.reduce((a, b) => a + b, 0) / distances.length;
  if (mean < 0.5) return null; // too small
  const maxDev = Math.max(...distances.map((d) => Math.abs(d - mean)));
  if (maxDev / mean > 0.05) return null; // not circular enough
  return { centerLat: cLat, centerLon: cLon, radiusNm: Math.round(mean * 100) / 100 };
}

// --- Polygon simplification (Ramer-Douglas-Peucker) ---

function perpDist(pt: number[], lineStart: number[], lineEnd: number[]): number {
  const dx = lineEnd[0] - lineStart[0];
  const dy = lineEnd[1] - lineStart[1];
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(pt[0] - lineStart[0], pt[1] - lineStart[1]);
  const t = Math.max(0, Math.min(1, ((pt[0] - lineStart[0]) * dx + (pt[1] - lineStart[1]) * dy) / lenSq));
  return Math.hypot(pt[0] - (lineStart[0] + t * dx), pt[1] - (lineStart[1] + t * dy));
}

function simplifyRing(ring: number[][], epsilon: number): number[][] {
  if (ring.length <= 4) return ring;
  let maxDist = 0, idx = 0;
  for (let i = 1; i < ring.length - 1; i++) {
    const d = perpDist(ring[i], ring[0], ring[ring.length - 1]);
    if (d > maxDist) { maxDist = d; idx = i; }
  }
  if (maxDist > epsilon) {
    const left = simplifyRing(ring.slice(0, idx + 1), epsilon);
    const right = simplifyRing(ring.slice(idx), epsilon);
    return [...left.slice(0, -1), ...right];
  }
  return [ring[0], ring[ring.length - 1]];
}

// --- Main export ---

export function toOpenAir(features: GeoJSONFeature[]): string {
  const lines: string[] = [];

  for (const f of features) {
    const p = f.properties;
    lines.push(`AC ${categoryToOpenAirClass(p.category)}`);
    lines.push(`AN ${p.name}`);
    lines.push(`AH ${formatAltitude(p.upperVal, p.upperUom, true)}`);
    lines.push(`AL ${formatAltitude(p.lowerVal, p.lowerUom, false)}`);

    const ring = f.geometry.type === "Polygon"
      ? f.geometry.coordinates[0]
      : f.geometry.coordinates[0]?.[0] ?? [];

    // Try circle detection first (common for Class C/D)
    const circle = detectCircle(ring);
    if (circle) {
      lines.push(`V X=${fmtPoint(circle.centerLat, circle.centerLon)}`);
      lines.push(`DC ${circle.radiusNm}`);
    } else {
      // Polygon — simplify to reduce noise, then emit DP points
      // epsilon ~0.001° ≈ ~60m, good tradeoff for airspace boundaries
      const simplified = simplifyRing(ring, 0.001);
      for (const [lon, lat] of simplified) {
        lines.push(`DP ${fmtPoint(lat, lon)}`);
      }
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
