import { useCallback, useState } from "react";
import type { AuditEntry, ChatMessage } from "../types";

export function useAuditLog() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);

  const addEntry = useCallback((userMsg: ChatMessage, assistantMsg: ChatMessage) => {
    if (!assistantMsg.trace) return;
    const entry: AuditEntry = {
      id: assistantMsg.id,
      timestamp: assistantMsg.timestamp,
      userMessage: userMsg.content,
      response: assistantMsg.content,
      tier: assistantMsg.tier,
      trace: assistantMsg.trace,
    };
    setEntries((prev) => [...prev, entry]);
  }, []);

  const exportJSON = useCallback(() => {
    const blob = new Blob([JSON.stringify(entries, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sophia-audit-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [entries]);

  return { entries, addEntry, exportJSON };
}
