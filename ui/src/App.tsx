import { useEffect, useRef, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useAuditLog } from "./hooks/useAuditLog";
import ChatWindow from "./components/ChatWindow";
import HatSelector from "./components/HatSelector";
import AuditDrawer from "./components/AuditDrawer";

const WS_URL =
  import.meta.env.DEV
    ? `ws://${window.location.hostname}:8000/ws/chat`
    : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/chat`;

export default function App() {
  const {
    messages,
    isConnected,
    isProcessing,
    currentTrace,
    currentStage,
    sendMessage,
    updateMessage,
  } = useWebSocket(WS_URL);

  const { entries, addEntry, exportJSON } = useAuditLog();
  const [auditOpen, setAuditOpen] = useState(false);

  // Track message count to detect new assistant messages for audit
  const prevCount = useRef(messages.length);
  useEffect(() => {
    if (messages.length > prevCount.current) {
      const newest = messages[messages.length - 1];
      if (newest.role === "assistant" && newest.trace) {
        // Find the user message that preceded it
        for (let i = messages.length - 2; i >= 0; i--) {
          if (messages[i].role === "user") {
            addEntry(messages[i], newest);
            break;
          }
        }
      }
    }
    prevCount.current = messages.length;
  }, [messages, addEntry]);

  return (
    <div className="flex h-screen flex-col bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-gray-800 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold tracking-tight">Sophia</h1>
          <div className="flex items-center gap-1.5">
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                isConnected ? "bg-green-500" : "bg-red-500"
              }`}
            />
            <span className="text-[11px] text-gray-500">
              {isConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <HatSelector />
          <button
            onClick={() => setAuditOpen(true)}
            className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-300 hover:border-gray-600 transition-colors"
          >
            Audit Trail
            {entries.length > 0 && (
              <span className="ml-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-gray-700 px-1 text-[10px] text-gray-400">
                {entries.length}
              </span>
            )}
          </button>
        </div>
      </header>

      {/* Chat */}
      <main className="flex-1 overflow-hidden">
        <ChatWindow
          messages={messages}
          isProcessing={isProcessing}
          currentStage={currentStage}
          currentTrace={currentTrace}
          onSend={sendMessage}
          onUpdateMessage={updateMessage}
        />
      </main>

      {/* Audit drawer */}
      <AuditDrawer
        open={auditOpen}
        entries={entries}
        onClose={() => setAuditOpen(false)}
        onExport={exportJSON}
      />
    </div>
  );
}
