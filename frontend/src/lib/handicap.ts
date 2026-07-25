export const HANDICAP_CLASSES = [
  { value: "modern_topless", label: "Modern Topless" },
  { value: "high_performance_kingpost", label: "High Performance Kingpost" },
  { value: "intermediate_kingpost", label: "Intermediate Kingpost" },
  { value: "single_surface", label: "Single Surface" },
] as const;

export type PilotClass = (typeof HANDICAP_CLASSES)[number]["value"];
export type HandicapMultipliers = Record<PilotClass, number>;

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
  return `${adjustment > 0 ? "+" : ""}${adjustment.toFixed(1)}`;
}
