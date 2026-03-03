import clsx from "clsx";
import type { RiskTier } from "../types";

const tierStyles: Record<RiskTier, string> = {
  GREEN: "bg-green-600/20 text-green-400 border-green-500/40",
  YELLOW: "bg-yellow-600/20 text-yellow-400 border-yellow-500/40",
  ORANGE: "bg-orange-600/20 text-orange-400 border-orange-500/40",
  RED: "bg-red-600/20 text-red-400 border-red-500/40",
};

const tierLabels: Record<RiskTier, string> = {
  GREEN: "Execute",
  YELLOW: "Confirm",
  ORANGE: "Escalate",
  RED: "Refuse",
};

interface Props {
  tier: RiskTier;
  showLabel?: boolean;
  className?: string;
}

export default function RiskBadge({ tier, showLabel = true, className }: Props) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        tierStyles[tier],
        className,
      )}
    >
      <span
        className={clsx("inline-block h-1.5 w-1.5 rounded-full", {
          "bg-green-400": tier === "GREEN",
          "bg-yellow-400": tier === "YELLOW",
          "bg-orange-400": tier === "ORANGE",
          "bg-red-400": tier === "RED",
        })}
      />
      {tier}
      {showLabel && (
        <span className="font-normal opacity-75">
          — {tierLabels[tier]}
        </span>
      )}
    </span>
  );
}
