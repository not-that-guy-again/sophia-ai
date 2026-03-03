import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import type { HatActive, HatSummary } from "../types";

const API_BASE = "/api";

interface Props {
  onHatChange?: (hat: HatActive) => void;
}

export default function HatSelector({ onHatChange }: Props) {
  const [hats, setHats] = useState<HatSummary[]>([]);
  const [active, setActive] = useState<HatActive | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  // Load available hats and active hat
  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/hats`).then((r) => r.json()),
      fetch(`${API_BASE}/hats/active`)
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ]).then(([hatList, activeHat]) => {
      setHats(hatList);
      setActive(activeHat);
    });
  }, []);

  const equipHat = useCallback(
    async (name: string) => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/hats/${name}/equip`, {
          method: "POST",
        });
        if (res.ok) {
          const hat: HatActive = await res.json();
          setActive(hat);
          onHatChange?.(hat);
        }
      } finally {
        setLoading(false);
        setOpen(false);
      }
    },
    [onHatChange],
  );

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={clsx(
          "flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm",
          "hover:border-gray-600 transition-colors",
        )}
      >
        <span className="text-lg">🎩</span>
        <span className="text-gray-200">
          {active?.display_name ?? "No hat"}
        </span>
        <span className="text-gray-500 text-xs">
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded-xl border border-gray-700 bg-gray-900 shadow-xl">
          {hats.map((hat) => {
            const isActive = active?.name === hat.name;
            return (
              <button
                key={hat.name}
                onClick={() => !isActive && equipHat(hat.name)}
                disabled={isActive || loading}
                className={clsx(
                  "block w-full px-4 py-3 text-left transition-colors",
                  "first:rounded-t-xl last:rounded-b-xl",
                  isActive
                    ? "bg-blue-600/10 border-l-2 border-blue-500"
                    : "hover:bg-gray-800",
                  "disabled:opacity-60",
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-200">
                    {hat.display_name}
                  </span>
                  {isActive && (
                    <span className="text-[10px] font-medium text-blue-400 uppercase tracking-wider">
                      Active
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-gray-500 line-clamp-2">
                  {hat.description}
                </p>
                <p className="mt-1 text-[10px] text-gray-600">
                  {hat.tools.length} tools · v{hat.version}
                </p>
              </button>
            );
          })}
          {hats.length === 0 && (
            <div className="px-4 py-3 text-xs text-gray-500">
              No hats available
            </div>
          )}
        </div>
      )}
    </div>
  );
}
