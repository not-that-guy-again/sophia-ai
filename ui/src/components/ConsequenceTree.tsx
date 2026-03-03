import { useState } from "react";
import clsx from "clsx";
import type { ConsequenceNode, ConsequenceTree as TreeType } from "../types";

function harmColor(hb: number): string {
  if (hb >= 0.5) return "border-green-500/60 bg-green-500/10";
  if (hb >= 0) return "border-green-500/30 bg-green-500/5";
  if (hb >= -0.3) return "border-yellow-500/40 bg-yellow-500/10";
  if (hb >= -0.6) return "border-orange-500/40 bg-orange-500/10";
  return "border-red-500/50 bg-red-500/10";
}

function TreeNode({ node, depth = 0 }: { node: ConsequenceNode; depth?: number }) {
  const [collapsed, setCollapsed] = useState(depth >= 2);
  const hasChildren = node.children.length > 0;

  return (
    <div className={clsx("relative", depth > 0 && "ml-5 border-l border-gray-700 pl-4")}>
      {/* Connector line */}
      {depth > 0 && (
        <div className="absolute -left-px top-0 h-4 w-4 border-b border-gray-700" />
      )}

      <div
        className={clsx(
          "rounded-lg border p-2.5 text-xs transition-colors",
          harmColor(node.harm_benefit),
          node.is_terminal && "ring-1 ring-gray-600",
        )}
        style={{ opacity: 0.4 + node.probability * 0.6 }}
      >
        <div className="flex items-start justify-between gap-2">
          <p className="text-gray-200 leading-relaxed">{node.description}</p>
          {hasChildren && (
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="shrink-0 text-gray-500 hover:text-gray-300"
            >
              {collapsed ? "+" : "−"}
            </button>
          )}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-2 text-[10px] text-gray-400">
          <span>P: {(node.probability * 100).toFixed(0)}%</span>
          <span
            className={clsx(
              "font-medium",
              node.harm_benefit >= 0 ? "text-green-400" : "text-red-400",
            )}
          >
            H/B: {node.harm_benefit > 0 ? "+" : ""}
            {node.harm_benefit.toFixed(2)}
          </span>
          <span>{node.affected_party}</span>
          {node.is_terminal && (
            <span className="rounded bg-gray-700 px-1 py-px">terminal</span>
          )}
        </div>
      </div>

      {hasChildren && !collapsed && (
        <div className="mt-1 space-y-1">
          {node.children.map((child) => (
            <TreeNode key={child.id} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

interface Props {
  trees: TreeType[];
}

export default function ConsequenceTree({ trees }: Props) {
  if (trees.length === 0) return null;

  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
        Consequence Trees
      </h4>
      {trees.map((tree, i) => (
        <div key={i} className="space-y-1.5">
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <span className="font-mono font-medium text-gray-300">
              {tree.candidate_tool_name}
            </span>
            <span>
              {tree.total_nodes} nodes, depth {tree.max_depth}
            </span>
          </div>
          <div className="space-y-1">
            {tree.root_nodes.map((node) => (
              <TreeNode key={node.id} node={node} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
