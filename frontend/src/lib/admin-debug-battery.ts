export type DebugBatterySummaryInput = {
  phoneBatteryLevel?: number | null;
  trackerBatteryLevel?: number | null;
};

export type DebugBatterySummaryItem = {
  label: "Phone" | "Tracker";
  level: number;
};

export function adminDebugBatterySummary({
  phoneBatteryLevel,
  trackerBatteryLevel,
}: DebugBatterySummaryInput): DebugBatterySummaryItem[] {
  const items: DebugBatterySummaryItem[] = [];
  if (phoneBatteryLevel != null) {
    items.push({ label: "Phone", level: phoneBatteryLevel });
  }
  if (trackerBatteryLevel != null) {
    items.push({ label: "Tracker", level: trackerBatteryLevel });
  }
  return items;
}
