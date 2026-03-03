import { useEffect, useRef, useState, type FormEvent } from "react";
import clsx from "clsx";
import type { ChatMessage, PipelineTrace } from "../types";
import MessageBubble from "./MessageBubble";

const STAGE_LABELS: Record<string, string> = {
  sending: "Sending message...",
  intent_parsed: "Intent parsed",
  proposals_generated: "Proposals generated",
  consequences_analyzed: "Analyzing consequences",
  risk_classified: "Risk classified",
  action_executed: "Executing action",
};

function stageLabel(stage: string | null): string {
  if (!stage) return "";
  if (stage.startsWith("evaluator_complete:")) {
    const name = stage.split(":")[1];
    const labels: Record<string, string> = {
      self_interest: "Self-Interest",
      tribal: "Tribal Harm",
      domain: "Domain Rules",
      authority: "Authority",
    };
    return `Evaluator complete: ${labels[name] ?? name}`;
  }
  return STAGE_LABELS[stage] ?? stage;
}

interface Props {
  messages: ChatMessage[];
  isProcessing: boolean;
  currentStage: string | null;
  currentTrace: PipelineTrace;
  onSend: (text: string) => void;
  onUpdateMessage: (id: string, patch: Partial<ChatMessage>) => void;
}

export default function ChatWindow({
  messages,
  isProcessing,
  currentStage,
  onSend,
  onUpdateMessage,
}: Props) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages or stage changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentStage]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || isProcessing) return;
    setInput("");
    onSend(text);
  }

  return (
    <div className="flex h-full flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center text-gray-600">
              <p className="text-lg font-medium">Sophia</p>
              <p className="text-sm mt-1">Consequence-aware AI agent</p>
              <p className="text-xs mt-2">Send a message to begin</p>
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onApprove={() =>
              onUpdateMessage(msg.id, { confirmationStatus: "approved" })
            }
            onDecline={() =>
              onUpdateMessage(msg.id, { confirmationStatus: "declined" })
            }
          />
        ))}

        {/* Live processing indicator */}
        {isProcessing && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md bg-gray-800/60 px-4 py-3">
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <span className="inline-flex gap-0.5">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:0ms]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:150ms]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:300ms]" />
                </span>
                <span>{stageLabel(currentStage)}</span>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="border-t border-gray-800 px-4 py-3"
      >
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Send a message..."
            disabled={isProcessing}
            className={clsx(
              "flex-1 rounded-xl border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-gray-100",
              "placeholder:text-gray-600 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500",
              "disabled:opacity-50",
            )}
          />
          <button
            type="submit"
            disabled={isProcessing || !input.trim()}
            className={clsx(
              "rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white",
              "hover:bg-blue-500 transition-colors",
              "disabled:opacity-40 disabled:cursor-not-allowed",
            )}
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
