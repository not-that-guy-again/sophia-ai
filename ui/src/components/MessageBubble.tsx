import { useState } from "react";
import clsx from "clsx";
import type { ChatMessage } from "../types";
import RiskBadge from "./RiskBadge";
import EvalPanel from "./EvalPanel";
import ConsequenceTree from "./ConsequenceTree";
import ConfirmBar from "./ConfirmBar";

interface Props {
  message: ChatMessage;
  onApprove?: () => void;
  onDecline?: () => void;
}

export default function MessageBubble({ message, onApprove, onDecline }: Props) {
  const [trailOpen, setTrailOpen] = useState(false);
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-br-md bg-blue-600 px-4 py-2.5 text-sm text-white">
          {message.content}
        </div>
      </div>
    );
  }

  const trace = message.trace;

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-2">
        {/* Response + tier badge */}
        <div className="rounded-2xl rounded-bl-md bg-gray-800 px-4 py-3 text-sm text-gray-100">
          <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>

          {message.tier && (
            <div className="mt-2 flex items-center gap-2">
              <RiskBadge tier={message.tier} />
            </div>
          )}
        </div>

        {/* YELLOW confirmation bar */}
        {message.tier === "YELLOW" &&
          message.confirmationStatus &&
          onApprove &&
          onDecline && (
            <ConfirmBar
              status={message.confirmationStatus}
              onApprove={onApprove}
              onDecline={onDecline}
            />
          )}

        {/* ORANGE/RED explanation */}
        {message.tier === "ORANGE" && trace?.risk && (
          <div className="rounded-lg border border-orange-500/30 bg-orange-500/10 px-3 py-2 text-xs text-orange-300">
            <span className="font-medium">Escalated:</span>{" "}
            {trace.risk.explanation}
          </div>
        )}
        {message.tier === "RED" && trace?.risk && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            <span className="font-medium">Refused:</span>{" "}
            {trace.risk.explanation}
          </div>
        )}

        {/* Decision trail toggle */}
        {trace && (
          <button
            onClick={() => setTrailOpen(!trailOpen)}
            className="text-[11px] text-gray-500 hover:text-gray-300 transition-colors"
          >
            {trailOpen ? "Hide" : "Show"} decision trail
          </button>
        )}

        {/* Expanded decision trail */}
        {trailOpen && trace && (
          <div className="space-y-4 rounded-xl border border-gray-700/50 bg-gray-900/50 p-4">
            {/* Intent */}
            {trace.intent && (
              <div className="space-y-1">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Intent
                </h4>
                <div className="text-xs text-gray-300">
                  <span className="font-medium">{trace.intent.action_requested}</span>
                  {trace.intent.target && (
                    <span className="text-gray-500"> → {trace.intent.target}</span>
                  )}
                </div>
              </div>
            )}

            {/* Proposals */}
            {trace.proposals.length > 0 && (
              <div className="space-y-1.5">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Proposed Actions
                </h4>
                {trace.proposals.map((c, i) => (
                  <div
                    key={i}
                    className="rounded-lg bg-gray-800/50 p-2.5 text-xs"
                  >
                    <span className="font-mono font-medium text-gray-200">
                      {c.tool_name}
                    </span>
                    <p className="mt-1 text-gray-400">{c.reasoning}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Consequence trees */}
            <ConsequenceTree trees={trace.trees} />

            {/* Evaluator panel */}
            <EvalPanel evaluations={trace.evaluations} />

            {/* Risk classification details */}
            {trace.risk && (
              <div className="space-y-1.5">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Risk Classification
                </h4>
                <div className="rounded-lg bg-gray-800/50 p-3 text-xs space-y-2">
                  <div className="flex items-center gap-2">
                    <RiskBadge tier={trace.risk.tier} />
                    <span className="font-mono text-gray-400">
                      weighted: {trace.risk.weighted_score.toFixed(3)}
                    </span>
                  </div>
                  {trace.risk.override_reason && (
                    <p className="text-yellow-400">
                      Override: {trace.risk.override_reason}
                    </p>
                  )}
                  <p className="text-gray-400">{trace.risk.explanation}</p>
                </div>
              </div>
            )}

            {/* Execution */}
            {trace.execution && (
              <div className="space-y-1">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Execution
                </h4>
                <div className="rounded-lg bg-gray-800/50 p-2.5 text-xs">
                  <span className="font-mono font-medium text-gray-200">
                    {trace.execution.action_taken.tool_name}
                  </span>
                  <span
                    className={clsx("ml-2", {
                      "text-green-400": trace.execution.tool_result.success,
                      "text-red-400": !trace.execution.tool_result.success,
                    })}
                  >
                    {trace.execution.tool_result.success ? "success" : "failed"}
                  </span>
                  <p className="mt-1 text-gray-400">
                    {trace.execution.tool_result.message}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
