import { useState } from "react";
import clsx from "clsx";
import type { EvaluatorResult } from "../types";

const evalLabels: Record<string, string> = {
  self_interest: "Self-Interest",
  tribal: "Tribal Harm",
  domain: "Domain Rules",
  authority: "Authority",
};

function scoreColor(score: number): string {
  if (score >= 0.3) return "bg-green-500";
  if (score >= 0) return "bg-green-500/60";
  if (score >= -0.3) return "bg-yellow-500";
  if (score >= -0.6) return "bg-orange-500";
  return "bg-red-500";
}

interface EvalBarProps {
  result: EvaluatorResult;
}

function EvalBar({ result }: EvalBarProps) {
  const [expanded, setExpanded] = useState(false);
  const label = evalLabels[result.evaluator_name] ?? result.evaluator_name;

  // Score maps from -1..+1 to 0%..100% for the bar
  const pct = ((result.score + 1) / 2) * 100;

  return (
    <div className="space-y-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-3 text-left"
      >
        <span className="w-28 shrink-0 text-xs font-medium text-gray-300">
          {label}
        </span>
        {/* Score bar: centered at 50% (score=0) */}
        <div className="relative h-2 flex-1 rounded-full bg-gray-700">
          {/* Center tick */}
          <div className="absolute left-1/2 top-0 h-full w-px bg-gray-500" />
          {/* Score fill */}
          <div
            className={clsx("absolute top-0 h-full rounded-full transition-all", scoreColor(result.score))}
            style={
              result.score >= 0
                ? { left: "50%", width: `${pct - 50}%` }
                : { left: `${pct}%`, width: `${50 - pct}%` }
            }
          />
        </div>
        <span className="w-12 shrink-0 text-right text-xs font-mono text-gray-400">
          {result.score > 0 ? "+" : ""}
          {result.score.toFixed(2)}
        </span>
        <span className="text-gray-500 text-xs">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {expanded && (
        <div className="ml-28 space-y-2 rounded-lg bg-gray-800/50 p-3 text-xs text-gray-300">
          <div>
            <span className="text-gray-500">Confidence:</span>{" "}
            {(result.confidence * 100).toFixed(0)}%
          </div>
          {result.flags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {result.flags.map((flag) => (
                <span
                  key={flag}
                  className={clsx(
                    "rounded px-1.5 py-0.5 text-[10px] font-medium",
                    flag === "catastrophic_harm"
                      ? "bg-red-600/30 text-red-300"
                      : "bg-gray-700 text-gray-400",
                  )}
                >
                  {flag}
                </span>
              ))}
            </div>
          )}
          {result.reasoning && (
            <p className="text-gray-400 leading-relaxed">{result.reasoning}</p>
          )}
          {result.key_concerns.length > 0 && (
            <ul className="list-disc pl-4 space-y-0.5 text-gray-400">
              {result.key_concerns.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

interface Props {
  evaluations: EvaluatorResult[];
}

export default function EvalPanel({ evaluations }: Props) {
  if (evaluations.length === 0) return null;

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
        Evaluation Panel
      </h4>
      <div className="space-y-2">
        {evaluations.map((e) => (
          <EvalBar key={e.evaluator_name} result={e} />
        ))}
      </div>
    </div>
  );
}
