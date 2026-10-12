"use client";

import { useCallback, useRef, useState } from "react";
import { ChatView, type Message } from "@/components/ChatView";
import { HITLPanel } from "@/components/HITLPanel";
import { useThreadStream } from "@/hooks/useThreadStream";
import { createThread } from "@/lib/api";

function generateId() {
  return Math.random().toString(36).slice(2);
}

export default function ChatPage() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const assistantIdRef = useRef<string | null>(null);

  const { state, sendMessage, resume } = useThreadStream(threadId);

  const streamCallbacks = {
    onToken: useCallback((delta: string) => {
      setMessages((msgs) => {
        const last = msgs[msgs.length - 1];
        if (!last || last.role !== "assistant" || !last.streaming) {
          const id = assistantIdRef.current ?? generateId();
          assistantIdRef.current = id;
          return [
            ...msgs,
            { id, role: "assistant" as const, content: delta, streaming: true },
          ];
        }
        return msgs.map((m) =>
          m.id === last.id ? { ...m, content: m.content + delta } : m
        );
      });
    }, []),

    onStep: useCallback(() => {}, []),

    onDone: useCallback(() => {
      setMessages((msgs) =>
        msgs.map((m) => (m.streaming ? { ...m, streaming: false } : m))
      );
      assistantIdRef.current = null;
      setIsLoading(false);
    }, []),

    onError: useCallback((message: string) => {
      setMessages((msgs) => [
        ...msgs,
        { id: generateId(), role: "assistant", content: `Error: ${message}` },
      ]);
      assistantIdRef.current = null;
      setIsLoading(false);
    }, []),
  };

  async function ensureThread(): Promise<string> {
    if (threadId) return threadId;
    const id = await createThread();
    setThreadId(id);
    return id;
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || isLoading) return;

    setInput("");
    setIsLoading(true);
    setMessages((msgs) => [
      ...msgs,
      { id: generateId(), role: "user", content: text },
    ]);

    await ensureThread();
    await sendMessage(text, streamCallbacks);
  }

  async function handleApprove() {
    setIsLoading(true);
    await resume({ action: "approve" }, streamCallbacks);
  }

  async function handleEdit(plan: Record<string, unknown>[]) {
    setIsLoading(true);
    await resume({ action: "edit", plan }, streamCallbacks);
  }

  async function handleReject(reason: string) {
    setIsLoading(true);
    await resume({ action: "reject", reason: reason || undefined }, streamCallbacks);
  }

  const isInterrupted = state.status === "interrupted" && state.interrupt !== null;

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="flex items-center border-b border-gray-200 bg-white px-6 py-3 shadow-sm">
        <h1 className="text-base font-semibold text-gray-800">Multi-Agent Chatbot</h1>
        {threadId && (
          <span className="ml-3 rounded bg-gray-100 px-2 py-0.5 font-mono text-xs text-gray-400">
            {threadId.slice(0, 8)}
          </span>
        )}
        {state.status === "streaming" && (
          <span className="ml-auto text-xs text-blue-500">Thinking…</span>
        )}
      </header>

      {/* Message area */}
      <ChatView
        messages={messages}
        artifacts={state.artifacts}
        progress={state.progress}
        activeNodes={state.activeNodes}
      />

      {/* HITL panel */}
      {isInterrupted && (
        <div className="border-t border-amber-200 bg-amber-50 px-4 pb-2">
          <HITLPanel
            interrupt={state.interrupt!}
            onApprove={handleApprove}
            onEdit={handleEdit}
            onReject={handleReject}
          />
        </div>
      )}

      {/* Error banner */}
      {state.status === "error" && state.error && (
        <div className="border-t border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {state.error}
        </div>
      )}

      {/* Input */}
      <div className="border-t border-gray-200 bg-white px-4 py-3">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void handleSend();
          }}
        >
          <input
            className="flex-1 rounded-full border border-gray-300 px-4 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 disabled:opacity-50"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={isInterrupted ? "Waiting for approval…" : "Type a message…"}
            disabled={isLoading || isInterrupted}
          />
          <button
            type="submit"
            disabled={isLoading || isInterrupted || !input.trim()}
            className="rounded-full bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
