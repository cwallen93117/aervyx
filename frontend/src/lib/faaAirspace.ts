/**
 * FAA Airspace data fetching from public ArcGIS feature services.
 * Two services: Class_Airspace (B/C/D/E/Mode-C) and Special_Use_Airspace (R/P/W/A/MOA).
 * Plus National_Defense_Airspace_TFR_Areas for defense TFRs.
 * All free, no API key, CORS-enabled.
 */

// ---------------------------------------------------------------------------
// ArcGIS endpoint base URLs
// ---------------------------------------------------------------------------

const CLASS_AIRSPACE_URL =
  "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/Class_Airspace/FeatureServer/0/query";
const SUA_URL =
  "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/Special_Use_Airspace/FeatureServer/0/query";
const NDA_TFR_URL =
  "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/National_Defense_Airspace_TFR_Areas/FeatureServer/0/query";

const PAGE_SIZE = 2000;

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
// Internal: paginated ArcGIS GeoJSON fetch
// ---------------------------------------------------------------------------

interface BoundsBox {
  west: number;
  south: number;
  east: number;
  north: number;
}

async function fetchArcGISPaginated(
  baseUrl: string,
  bounds: BoundsBox | null,
  where: string,
  outFields: string,
  signal?: AbortSignal,
): Promise<GeoJSON.FeatureCollection> {
  const allFeatures: GeoJSON.Feature[] = [];
  let offset = 0;
  let hasMore = true;

  while (hasMore) {
    const params = new URLSearchParams({
      where,
      outFields,
      f: "geojson",
      outSR: "4326",
      resultRecordCount: String(PAGE_SIZE),
      resultOffset: String(offset),
    });

    if (bounds) {
      params.set("geometry", `${bounds.west},${bounds.south},${bounds.east},${bounds.north}`);
      params.set("geometryType", "esriGeometryEnvelope");
      params.set("spatialRel", "esriSpatialRelIntersects");
      params.set("inSR", "4326");
    }

    const resp = await fetch(`${baseUrl}?${params}`, { signal });
    if (!resp.ok) throw new Error(`ArcGIS query failed: ${resp.status}`);
    const data = await resp.json();

    const features = data.features ?? [];
    allFeatures.push(...features);

    if (features.length < PAGE_SIZE) {
      hasMore = false;
    } else {
      offset += PAGE_SIZE;
    }
  }

  return { type: "FeatureCollection", features: allFeatures };
}

// ---------------------------------------------------------------------------
// Normalize raw FAA features into our unified schema
// ---------------------------------------------------------------------------

function normalizeClassAirspace(raw: GeoJSON.FeatureCollection): GeoJSONFeature[] {
  return (raw.features as GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon>[]).map((f) => {
    const p = f.properties ?? {};
    const classVal = (p.CLASS ?? "").toUpperCase();
    const localType = (p.LOCAL_TYPE ?? "").toUpperCase();

    let category: AirspaceCategory = "E";
    if (classVal === "B" || localType === "CLASS_B") category = "B";
    else if (classVal === "C" || localType === "CLASS_C") category = "C";
    else if (classVal === "D" || localType === "CLASS_D") category = "D";
    else if (classVal === "E" || localType.startsWith("CLASS_E")) category = "E";
    else if (localType === "MODE C" || (p.TYPE_CODE ?? "").toUpperCase() === "MODE-C") category = "MODE-C";

    return {
      ...f,
      properties: {
        category,
        name: p.NAME ?? p.IDENT ?? "Unknown",
        ident: p.IDENT ?? undefined,
        upperVal: p.UPPER_VAL != null ? Number(p.UPPER_VAL) : null,
        upperUom: p.UPPER_UOM ?? "FT",
        lowerVal: p.LOWER_VAL != null ? Number(p.LOWER_VAL) : null,
        lowerUom: p.LOWER_UOM ?? "FT",
        upperDesc: p.UPPER_DESC ?? "",
        lowerDesc: p.LOWER_DESC ?? "",
        city: p.CITY ?? undefined,
        state: p.STATE ?? undefined,
        source: "class" as const,
      },
    };
  });
}

function normalizeSUA(raw: GeoJSON.FeatureCollection): GeoJSONFeature[] {
  return (raw.features as GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon>[]).map((f) => {
    const p = f.properties ?? {};
    const typeCode = (p.TYPE_CODE ?? "").toUpperCase();

    let category: AirspaceCategory = "R";
    if (typeCode === "P") category = "P";
    else if (typeCode === "R") category = "R";
    else if (typeCode === "W") category = "W";
    else if (typeCode === "A") category = "A";
    else if (typeCode === "M" || typeCode === "MOA") category = "MOA";

    return {
      ...f,
      properties: {
        category,
        name: p.NAME ?? "Unknown",
        upperVal: p.UPPER_VAL != null ? Number(p.UPPER_VAL) : null,
        upperUom: p.UPPER_UOM ?? "FT",
        lowerVal: p.LOWER_VAL != null ? Number(p.LOWER_VAL) : null,
        lowerUom: p.LOWER_UOM ?? "FT",
        upperDesc: p.UPPER_DESC ?? "",
        lowerDesc: p.LOWER_DESC ?? "",
        city: p.CITY ?? undefined,
        state: p.STATE ?? undefined,
        source: "sua" as const,
      },
    };
  });
}

function normalizeTFR(raw: GeoJSON.FeatureCollection): GeoJSONFeature[] {
  return (raw.features as GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon>[]).map((f) => {
    const p = f.properties ?? {};
    return {
      ...f,
      properties: {
        category: "TFR" as AirspaceCategory,
        name: p.NAME ?? "TFR",
        upperVal: null,
        upperUom: "FT",
        lowerVal: null,
        lowerUom: "FT",
        upperDesc: p.WKHR_RMK ?? "",
        lowerDesc: "",
        city: p.CITY ?? undefined,
        state: p.STATE ?? undefined,
        source: "tfr" as const,
      },
    };
  });
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function fetchClassAirspace(bounds: BoundsBox, signal?: AbortSignal): Promise<GeoJSONFC> {
  const fields = "IDENT,NAME,CLASS,LOCAL_TYPE,TYPE_CODE,UPPER_DESC,LOWER_DESC,UPPER_VAL,UPPER_UOM,LOWER_VAL,LOWER_UOM,CITY,STATE";
  // Skip Mode-C and Class E (too many, low relevance for paragliding/hang gliding)
  const where = "CLASS IN ('B','C','D') OR LOCAL_TYPE IN ('CLASS_B','CLASS_C','CLASS_D')";
  const raw = await fetchArcGISPaginated(CLASS_AIRSPACE_URL, bounds, where, fields, signal);
  return { type: "FeatureCollection", features: normalizeClassAirspace(raw) };
}

export async function fetchSpecialUseAirspace(bounds: BoundsBox, signal?: AbortSignal): Promise<GeoJSONFC> {
  const fields = "NAME,TYPE_CODE,CLASS,UPPER_DESC,LOWER_DESC,UPPER_VAL,UPPER_UOM,LOWER_VAL,LOWER_UOM,CITY,STATE";
  const raw = await fetchArcGISPaginated(SUA_URL, bounds, "1=1", fields, signal);
  return { type: "FeatureCollection", features: normalizeSUA(raw) };
}

export async function fetchTFRs(signal?: AbortSignal): Promise<GeoJSONFC> {
  const raw = await fetchArcGISPaginated(NDA_TFR_URL, null, "1=1", "*", signal);
  return { type: "FeatureCollection", features: normalizeTFR(raw) };
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
