import clsx from "clsx";
import type { AuditEntry } from "../types";
import RiskBadge from "./RiskBadge";
import EvalPanel from "./EvalPanel";
import ConsequenceTree from "./ConsequenceTree";
import { useState } from "react";

interface Props {
  open: boolean;
  entries: AuditEntry[];
  onClose: () => void;
  onExport: () => void;
}

function AuditEntryCard({ entry }: { entry: AuditEntry }) {
  const [expanded, setExpanded] = useState(false);
  const time = new Date(entry.timestamp).toLocaleTimeString();

  return (
    <div className="border-b border-gray-800 last:border-b-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-gray-800/30 transition-colors"
      >
        <span className="shrink-0 text-[10px] text-gray-600 mt-0.5">
          {time}
        </span>
        <div className="flex-1 min-w-0">
          <p className="truncate text-xs text-gray-300">{entry.userMessage}</p>
          <p className="truncate text-[11px] text-gray-500 mt-0.5">
            {entry.response}
          </p>
        </div>
        {entry.tier && <RiskBadge tier={entry.tier} showLabel={false} />}
      </button>

      {expanded && (
        <div className="space-y-3 px-4 pb-4">
          {/* Intent */}
          {entry.trace.intent && (
            <div className="text-xs text-gray-400">
              <span className="text-gray-500">Action:</span>{" "}
              {entry.trace.intent.action_requested}
              {entry.trace.intent.target && ` → ${entry.trace.intent.target}`}
            </div>
          )}

          {/* Proposals */}
          {entry.trace.proposals.length > 0 && (
            <div className="text-xs text-gray-400">
              <span className="text-gray-500">Proposed:</span>{" "}
              {entry.trace.proposals.map((p) => p.tool_name).join(", ")}
            </div>
          )}

          {/* Consequence trees */}
          <ConsequenceTree trees={entry.trace.trees} />

          {/* Eval panel */}
          <EvalPanel evaluations={entry.trace.evaluations} />

          {/* Risk */}
          {entry.trace.risk && (
            <div className="rounded-lg bg-gray-800/50 p-2.5 text-xs">
              <div className="flex items-center gap-2">
                <RiskBadge tier={entry.trace.risk.tier} />
                <span className="text-gray-500 font-mono">
                  score: {entry.trace.risk.weighted_score.toFixed(3)}
                </span>
              </div>
              {entry.trace.risk.override_reason && (
                <p className="mt-1 text-yellow-400">
                  Override: {entry.trace.risk.override_reason}
                </p>
              )}
              <p className="mt-1 text-gray-400">{entry.trace.risk.explanation}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function AuditDrawer({ open, entries, onClose, onExport }: Props) {
  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/40"
          onClick={onClose}
        />
      )}

      {/* Drawer */}
      <div
        className={clsx(
          "fixed right-0 top-0 z-50 flex h-full w-96 flex-col bg-gray-900 border-l border-gray-800 shadow-2xl transition-transform duration-200",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-gray-200">
            Audit Trail
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={onExport}
              disabled={entries.length === 0}
              className="rounded-md bg-gray-800 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-700 transition-colors disabled:opacity-40"
            >
              Export JSON
            </button>
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-300 transition-colors text-lg"
            >
              ×
            </button>
          </div>
        </div>

        {/* Entries */}
        <div className="flex-1 overflow-y-auto">
          {entries.length === 0 ? (
            <div className="flex h-full items-center justify-center text-xs text-gray-600">
              No decisions yet
            </div>
          ) : (
            entries.map((entry) => (
              <AuditEntryCard key={entry.id} entry={entry} />
            ))
          )}
        </div>

        <div className="border-t border-gray-800 px-4 py-2 text-[10px] text-gray-600">
          {entries.length} decision{entries.length !== 1 ? "s" : ""} this session
        </div>
      </div>
    </>
  );
}
