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
  penalty_summary?: string | null;
  penalty_calculation?: ScorePenaltyCalculation | null;
};

export function formatPenaltyPointsValue(value: number | null | undefined): string {
  const safe = Number(value ?? 0);
  if (!Number.isFinite(safe) || safe <= 0.05) return "-";
  return `-${safe.toFixed(1)}`;
}

export function penaltyDisplayPoints(result: PenaltyResultLike): number {
  const calculated = Number(result.penalty_calculation?.total_display_penalty_points ?? NaN);
  if (Number.isFinite(calculated) && calculated > 0.05) return calculated;
  const rawScore = Number(result.raw_score_points ?? result.score_points ?? 0);
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
  const rawScore = Number(result.raw_score_points ?? result.score_points ?? 0);
  return Number.isFinite(rawScore) ? rawScore : 0;
}

export function hasPenaltyDetails(result: PenaltyResultLike): boolean {
  return Boolean(result.penalty_calculation?.lines?.length) || penaltyDisplayPoints(result) > 0.05;
}

export function formatScorePoints(value: number | null | undefined): string {
  const safe = Number(value ?? 0);
  return Number.isFinite(safe) ? safe.toFixed(1) : "-";
}
