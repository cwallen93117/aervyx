import type { ProfileType } from "../lib/live-tracking-utils";

type PilotRoleBadgeProps = {
  profileType?: ProfileType | null;
  color?: string | null;
  size?: number;
  className?: string;
};

// Matches the ROLE_ICON_SVGS shapes used in TaskMap so the sidebar / table icons
// look identical to the glyphs drawn on the map itself.
export function PilotRoleBadge({ profileType, color, size = 14, className }: PilotRoleBadgeProps) {
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
        <path d="M5 11l1.5-4.5A2 2 0 018.4 5h7.2a2 2 0 011.9 1.5L19 11h1a1 1 0 011 1v4a1 1 0 01-1 1h-1v1a1 1 0 01-1 1h-1a1 1 0 01-1-1v-1H8v1a1 1 0 01-1 1H6a1 1 0 01-1-1v-1H4a1 1 0 01-1-1v-4a1 1 0 011-1h1zm2 4a1.25 1.25 0 100-2.5 1.25 1.25 0 000 2.5zm10 0a1.25 1.25 0 100-2.5 1.25 1.25 0 000 2.5z" />
      </svg>
    );
  }

  if (role === "stationary_node") {
    return (
      <svg {...common}>
        <path d="M12 2l4 6-4 2-4-2 4-6zm-1 8h2v12h-2V10zM5.5 4.2l1.4 1.4a7 7 0 000 9.9l-1.4 1.4a9 9 0 010-12.7zm13 0a9 9 0 010 12.7l-1.4-1.4a7 7 0 000-9.9l1.4-1.4z" />
      </svg>
    );
  }

  // pilot (default)
  return (
    <svg {...common}>
      <path d="M12 2l2 8h8l-6 4.5 2.5 7.5-6.5-5-6.5 5L8 14.5 2 10h8z" />
    </svg>
  );
}
