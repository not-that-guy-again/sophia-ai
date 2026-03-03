import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ChatMessage,
  PipelineTrace,
  RiskTier,
  WsEvent,
} from "../types";

function emptyTrace(): PipelineTrace {
  return {
    intent: null,
    proposals: [],
    trees: [],
    evaluations: [],
    risk: null,
    execution: null,
  };
}

let nextId = 1;
function genId() {
  return `msg-${nextId++}`;
}

export interface UseSophiaSocket {
  messages: ChatMessage[];
  isConnected: boolean;
  isProcessing: boolean;
  currentTrace: PipelineTrace;
  currentStage: string | null;
  sendMessage: (text: string) => void;
  updateMessage: (id: string, patch: Partial<ChatMessage>) => void;
}

export function useWebSocket(url: string): UseSophiaSocket {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentTrace, setCurrentTrace] = useState<PipelineTrace>(emptyTrace);
  const [currentStage, setCurrentStage] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const traceRef = useRef<PipelineTrace>(emptyTrace());
  const pendingUserMsg = useRef<string>("");
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
      // Auto-reconnect after 2s
      reconnectTimer.current = setTimeout(connect, 2000);
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onmessage = (evt) => {
      const event: WsEvent = JSON.parse(evt.data);
      handleEvent(event);
    };
  }, [url]);

  // Cleanup on unmount
  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  function handleEvent(event: WsEvent) {
    const trace = traceRef.current;

    switch (event.event) {
      case "hat_equipped":
        // Informational only on connect
        break;

      case "preflight_ack": {
        const ackMsg: ChatMessage = {
          id: genId(),
          role: "assistant",
          content: event.data.message,
          trace: null,
          tier: null,
          timestamp: Date.now(),
          isAck: true,
        };
        setMessages((prev) => [...prev, ackMsg]);
        break;
      }

      case "intent_parsed":
        trace.intent = event.data;
        setCurrentStage("intent_parsed");
        break;

      case "proposals_generated":
        trace.proposals = event.data.candidates;
        setCurrentStage("proposals_generated");
        break;

      case "consequences_analyzed":
        trace.trees = event.data.trees;
        setCurrentStage("consequences_analyzed");
        break;

      case "evaluator_complete":
        trace.evaluations = [...trace.evaluations, event.data];
        setCurrentStage(
          `evaluator_complete:${event.data.evaluator_name}`,
        );
        break;

      case "risk_classified":
        trace.risk = event.data;
        setCurrentStage("risk_classified");
        break;

      case "action_executed":
        trace.execution = event.data;
        setCurrentStage("action_executed");
        break;

      case "response_ready": {
        const tier = (trace.risk?.tier ?? trace.execution?.risk_tier ?? null) as RiskTier | null;
        const assistantMsg: ChatMessage = {
          id: genId(),
          role: "assistant",
          content: event.data.response,
          trace: { ...trace },
          tier,
          timestamp: Date.now(),
          confirmationStatus: tier === "YELLOW" ? "pending" : undefined,
        };
        setMessages((prev) => {
          const withoutAck = prev.filter((m) => !m.isAck);
          return [...withoutAck, assistantMsg];
        });
        // Reset for next round
        traceRef.current = emptyTrace();
        setCurrentTrace(emptyTrace());
        setCurrentStage(null);
        setIsProcessing(false);
        return;
      }

      case "error":
        setMessages((prev) => [
          ...prev,
          {
            id: genId(),
            role: "assistant",
            content: `Error: ${event.data.message}`,
            trace: null,
            tier: null,
            timestamp: Date.now(),
          },
        ]);
        traceRef.current = emptyTrace();
        setCurrentTrace(emptyTrace());
        setCurrentStage(null);
        setIsProcessing(false);
        return;
    }

    // Publish intermediate trace for live updates
    setCurrentTrace({ ...trace });
  }

  const sendMessage = useCallback((text: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    pendingUserMsg.current = text;
    traceRef.current = emptyTrace();
    setCurrentTrace(emptyTrace());
    setIsProcessing(true);
    setCurrentStage("sending");

    // Add user message
    setMessages((prev) => [
      ...prev,
      {
        id: genId(),
        role: "user",
        content: text,
        trace: null,
        tier: null,
        timestamp: Date.now(),
      },
    ]);

    wsRef.current.send(JSON.stringify({ message: text }));
  }, []);

  const updateMessage = useCallback(
    (id: string, patch: Partial<ChatMessage>) => {
      setMessages((prev) =>
        prev.map((m) => (m.id === id ? { ...m, ...patch } : m)),
      );
    },
    [],
  );

  return {
    messages,
    isConnected,
    isProcessing,
    currentTrace,
    currentStage,
    sendMessage,
    updateMessage,
  };
}
