import type { ProfileType } from "../lib/live-tracking-utils";

export type AircraftIconType = "hang_glider" | "paraglider" | "sailplane";

type PilotRoleBadgeProps = {
  profileType?: ProfileType | null;
  aircraftType?: AircraftIconType | null;
  color?: string | null;
  size?: number;
  className?: string;
};

// Matches the ROLE_ICON_SVGS shapes used in TaskMap so the sidebar / table icons
// look identical to the glyphs drawn on the map itself.
// Pilots are rendered per aircraft type (HG / PG / sailplane), drivers use a car
// glyph, stationary nodes use an antenna glyph.
export const AIRCRAFT_ICON_PATHS: Record<AircraftIconType, string> = {
  // Delta / chevron silhouette pointing up
  hang_glider: "M12 4 L22 20 L12 16 L2 20 Z",
  // Arched canopy over a tiny pilot body
  paraglider: "M2 12 Q12 4 22 12 L20 13 Q12 6 4 13 Z M11 15 L13 15 L13 20 L11 20 Z",
  // Straight-wing glider
  sailplane:
    "M2 11 L11 11 L11 3 L13 3 L13 11 L22 11 L22 13 L13 13 L13 18 L16 18 L16 20 L8 20 L8 18 L11 18 L11 13 L2 13 Z",
};

export const DRIVER_ICON_PATH =
  "M5 11l1.5-4.5A2 2 0 018.4 5h7.2a2 2 0 011.9 1.5L19 11h1a1 1 0 011 1v4a1 1 0 01-1 1h-1v1a1 1 0 01-1 1h-1a1 1 0 01-1-1v-1H8v1a1 1 0 01-1 1H6a1 1 0 01-1-1v-1H4a1 1 0 01-1-1v-4a1 1 0 011-1h1zm2 4a1.25 1.25 0 100-2.5 1.25 1.25 0 000 2.5zm10 0a1.25 1.25 0 100-2.5 1.25 1.25 0 000 2.5z";

export const STATIONARY_NODE_ICON_PATH =
  "M12 2l4 6-4 2-4-2 4-6zm-1 8h2v12h-2V10zM5.5 4.2l1.4 1.4a7 7 0 000 9.9l-1.4 1.4a9 9 0 010-12.7zm13 0a9 9 0 010 12.7l-1.4-1.4a7 7 0 000-9.9l1.4-1.4z";

export function PilotRoleBadge({
  profileType,
  aircraftType,
  color,
  size = 14,
  className,
}: PilotRoleBadgeProps) {
  const role: ProfileType = profileType ?? "pilot";
  const fill = color ?? "#2563eb";
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill,
    "aria-hidden": true as const,
    className,
  };

  if (role === "driver") {
    return (
      <svg {...common}>
        <path d={DRIVER_ICON_PATH} />
      </svg>
    );
  }

  if (role === "stationary_node") {
    return (
      <svg {...common}>
        <path d={STATIONARY_NODE_ICON_PATH} />
      </svg>
    );
  }

  // pilot — aircraft-type specific glyph
  const aircraft: AircraftIconType = aircraftType ?? "hang_glider";
  return (
    <svg {...common}>
      <path d={AIRCRAFT_ICON_PATHS[aircraft]} />
    </svg>
  );
}
