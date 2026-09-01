import { formatScorePoints } from "./scorePenalties";

export const HANDICAP_CLASSES = [
  { value: "modern_topless", label: "Modern Topless" },
  { value: "high_performance_kingpost", label: "High Performance Kingpost" },
  { value: "intermediate_kingpost", label: "Intermediate Kingpost" },
  { value: "single_surface", label: "Single Surface" },
] as const;

export type PilotClass = (typeof HANDICAP_CLASSES)[number]["value"];
export type HandicapMultipliers = Record<PilotClass, number>;
export type HandicapResultLike = {
  raw_score_points?: number | null;
  score_points?: number | null;
  details_json?: Record<string, unknown> | null;
  pilot_class?: string | null;
  handicap_multiplier?: number | null;
  handicap_adjustment_points?: number | null;
};
export type HandicapDetails = {
  pilot_class: string;
  multiplier: number;
  official_score_points: number;
  multiplied_score_points: number;
  normalization_max_score_points: number;
  normalization_target_score_points: number;
  adjusted_score_points: number;
  adjustment_points: number;
};

export const DEFAULT_PILOT_CLASS: PilotClass = "modern_topless";
export const DEFAULT_HANDICAP_MULTIPLIERS: HandicapMultipliers = {
  modern_topless: 1,
  high_performance_kingpost: 1,
  intermediate_kingpost: 1,
  single_surface: 1,
};

export function readHandicapConfig(penaltiesJson: Record<string, unknown> | null | undefined) {
  const handicap = penaltiesJson?.handicap;
  const record = handicap && typeof handicap === "object" ? handicap as Record<string, unknown> : {};
  const rawMultipliers = record.multipliers && typeof record.multipliers === "object"
    ? record.multipliers as Record<string, unknown>
    : {};
  return {
    enabled: record.enabled === true,
    multipliers: Object.fromEntries(
      HANDICAP_CLASSES.map(({ value }) => {
        const configured = Number(rawMultipliers[value]);
        return [value, Number.isFinite(configured) && configured > 0 ? configured : 1];
      }),
    ) as HandicapMultipliers,
  };
}

export function writeHandicapConfig(
  penaltiesJson: Record<string, unknown>,
  enabled: boolean,
  multipliers: HandicapMultipliers,
): Record<string, unknown> {
  return { ...penaltiesJson, handicap: { enabled, multipliers } };
}

export function handicapClassLabel(value: string | null | undefined): string {
  return HANDICAP_CLASSES.find((option) => option.value === value)?.label ?? HANDICAP_CLASSES[0].label;
}

export function formatHandicapAdjustment(value: number | null | undefined): string {
  const adjustment = Number(value ?? 0);
  if (!Number.isFinite(adjustment) || Math.abs(adjustment) < 0.05) return "0.0";
  return `${adjustment > 0 ? "+" : ""}${formatScorePoints(adjustment)}`;
}

function numberOr(value: unknown, fallback: number): number {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function handicapDetails(result: HandicapResultLike): HandicapDetails | null {
  const handicap = result.details_json?.handicap;
  if (!handicap || typeof handicap !== "object") return null;
  const record = handicap as Record<string, unknown>;
  const official = numberOr(record.official_score_points, numberOr(result.raw_score_points, numberOr(result.score_points, 0)));
  const multiplier = numberOr(record.multiplier, numberOr(result.handicap_multiplier, 1));
  const multiplied = numberOr(record.multiplied_score_points, official * multiplier);
  const adjusted = numberOr(record.adjusted_score_points, official + numberOr(record.adjustment_points, numberOr(result.handicap_adjustment_points, 0)));
  return {
    pilot_class: String(record.pilot_class ?? result.pilot_class ?? DEFAULT_PILOT_CLASS),
    multiplier,
    official_score_points: official,
    multiplied_score_points: multiplied,
    normalization_max_score_points: numberOr(record.normalization_max_score_points, multiplied),
    normalization_target_score_points: numberOr(record.normalization_target_score_points, 1000),
    adjusted_score_points: adjusted,
    adjustment_points: numberOr(record.adjustment_points, adjusted - official),
  };
}
