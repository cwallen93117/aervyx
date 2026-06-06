export type ScorePenaltyRecord = {
  id?: number | null;
  penalty_type: "percentage" | "fixed";
  value: number;
  reason: string;
  position: number;
  applied_by?: string | null;
  applied_at?: string | null;
};

export type ScorePenaltyCalculationLine = {
  kind: string;
  label: string;
  amount_points: number;
  running_score_points?: number | null;
  detail?: string | null;
};

export type ScorePenaltyCalculation = {
  raw_score_points: number;
  final_score_points: number;
  manual_penalty_points: number;
  engine_penalty_points: number;
  total_display_penalty_points: number;
  lines: ScorePenaltyCalculationLine[];
};

export type PenaltyResultLike = {
  raw_score_points?: number | null;
  score_points: number;
  details_json?: Record<string, unknown> | null;
  penalty_summary?: string | null;
  penalty_calculation?: ScorePenaltyCalculation | null;
};

function safeNumber(value: unknown): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function gapAwardedTotal(result: PenaltyResultLike): number {
  const gap = result.details_json?.gap;
  if (!gap || typeof gap !== "object") return 0;
  const awarded = (gap as { awarded_points?: Record<string, unknown> }).awarded_points;
  if (!awarded || typeof awarded !== "object") return 0;
  const componentTotal = ["distance", "speed", "leading", "arrival", "departure"].reduce((sum, key) => sum + safeNumber(awarded[key]), 0);
  return Math.max(safeNumber(awarded.total), componentTotal);
}

export function formatPenaltyPointsValue(value: number | null | undefined): string {
  const safe = Number(value ?? 0);
  if (!Number.isFinite(safe) || safe <= 0.05) return "-";
  return `-${safe.toFixed(1)}`;
}

export function penaltyDisplayPoints(result: PenaltyResultLike): number {
  const calculated = Number(result.penalty_calculation?.total_display_penalty_points ?? NaN);
  if (Number.isFinite(calculated) && calculated > 0.05) return calculated;
  const rawScore = Math.max(Number(result.raw_score_points ?? result.score_points ?? 0), gapAwardedTotal(result));
  const finalScore = Number(result.score_points ?? 0);
  const derived = rawScore - finalScore;
  return Number.isFinite(derived) && derived > 0.05 ? derived : 0;
}

export function formatPenaltyPoints(result: PenaltyResultLike): string {
  return formatPenaltyPointsValue(penaltyDisplayPoints(result));
}

export function prePenaltyTotalPoints(result: PenaltyResultLike): number {
  const calculation = result.penalty_calculation;
  if (calculation) {
    const finalScore = Number(calculation.final_score_points ?? result.score_points ?? 0);
    const penalties = Number(calculation.total_display_penalty_points ?? 0);
    if (Number.isFinite(finalScore) && Number.isFinite(penalties)) return finalScore + penalties;
  }
  const rawScore = Math.max(Number(result.raw_score_points ?? result.score_points ?? 0), gapAwardedTotal(result));
  return Number.isFinite(rawScore) ? rawScore : 0;
}

export function hasPenaltyDetails(result: PenaltyResultLike): boolean {
  return Boolean(result.penalty_calculation?.lines?.length) || penaltyDisplayPoints(result) > 0.05;
}

export function formatScorePoints(value: number | null | undefined): string {
  const safe = Number(value ?? 0);
  return Number.isFinite(safe) ? safe.toFixed(1) : "-";
}

function formatPenaltyTime(value: unknown, timezone?: string | null): string | null {
  if (!value) return null;
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return null;
  try {
    return new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
      timeZone: timezone || undefined,
      timeZoneName: "short",
    }).format(date);
  } catch {
    return new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
      timeZoneName: "short",
    }).format(date);
  }
}

function formatPenaltyDuration(seconds: unknown): string | null {
  const safe = Math.max(Math.round(safeNumber(seconds)), 0);
  if (!safe) return null;
  const minutes = Math.floor(safe / 60);
  const remainder = safe % 60;
  if (minutes && remainder) return `${minutes}m ${remainder}s`;
  if (minutes) return `${minutes}m`;
  return `${remainder}s`;
}

export function derivedPenaltyCalculation(result: PenaltyResultLike, timezone?: string | null): ScorePenaltyCalculation | null {
  if (result.penalty_calculation?.lines?.length) return result.penalty_calculation;
  const penaltyPoints = penaltyDisplayPoints(result);
  if (penaltyPoints <= 0.05) return null;
  const finalScore = safeNumber(result.score_points);
  const prePenaltyScore = prePenaltyTotalPoints(result);
  const startTiming = result.details_json?.start_timing;
  const start = startTiming && typeof startTiming === "object" ? startTiming as Record<string, unknown> : null;
  const detailParts: string[] = [];
  if (start) {
    const actualStart = formatPenaltyTime(start.actual_start_crossing_at ?? start.actual_start_exit_after_at, timezone);
    const gateTime = formatPenaltyTime(start.start_gate_time, timezone);
    const gateIndex = start.start_gate_index;
    if (actualStart && gateIndex && gateTime) {
      detailParts.push(`Started at ${actualStart}, before start gate ${gateIndex} at ${gateTime}.`);
    } else if (actualStart) {
      detailParts.push(`Started at ${actualStart}.`);
    }
    const early = formatPenaltyDuration(start.jump_the_gun_seconds);
    if (early) detailParts.push(`Early by ${early}.`);
    const factor = (result.details_json?.gap as { formula?: Record<string, unknown> } | undefined)?.formula?.jump_the_gun_factor;
    if (safeNumber(factor) > 0) detailParts.push(`Charged ${safeNumber(factor).toFixed(1).replace(/\.0$/, "")} points per second.`);
  }
  return {
    raw_score_points: prePenaltyScore,
    final_score_points: finalScore,
    manual_penalty_points: 0,
    engine_penalty_points: penaltyPoints,
    total_display_penalty_points: penaltyPoints,
    lines: [
      {
        kind: "engine",
        label: start ? "Early start penalty" : "Scoring penalty",
        amount_points: penaltyPoints,
        running_score_points: finalScore,
        detail: detailParts.length ? detailParts.join(" ") : "Penalty reflected by the scored total.",
      },
    ],
  };
}
