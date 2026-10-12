"use client";

import { useCallback, useRef, useState } from "react";
import { fetchResumeStream, fetchRunStream } from "@/lib/api";
import type {
  ArtifactEvent,
  DoneEvent,
  ErrorEvent,
  InterruptEvent,
  ProgressEvent,
  SSEEvent,
  StepEvent,
} from "@/types/events";

export type StreamStatus = "idle" | "streaming" | "interrupted" | "done" | "error";

export interface StreamState {
  status: StreamStatus;
  streamingDelta: string;
  activeNodes: Set<string>;
  interrupt: InterruptEvent | null;
  artifacts: ArtifactEvent[];
  progress: Record<string, ProgressEvent>;
  error: string | null;
}

const INITIAL: StreamState = {
  status: "idle",
  streamingDelta: "",
  activeNodes: new Set(),
  interrupt: null,
  artifacts: [],
  progress: {},
  error: null,
};

type OnToken = (delta: string) => void;
type OnStep = (event: StepEvent) => void;
type OnDone = (event: DoneEvent) => void;
type OnError = (message: string) => void;

export function useThreadStream(threadId: string | null) {
  const [state, setState] = useState<StreamState>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  const resetStream = useCallback(() => {
    setState((s) => ({
      ...s,
      status: "streaming",
      streamingDelta: "",
      interrupt: null,
      error: null,
    }));
  }, []);

  const readStream = useCallback(
    async (
      response: Response,
      callbacks: {
        onToken: OnToken;
        onStep: OnStep;
        onDone: OnDone;
        onError: OnError;
      }
    ) => {
      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data:")) continue;
            const raw = line.slice(5).trim();
            if (!raw) continue;

            let event: SSEEvent;
            try {
              event = JSON.parse(raw) as SSEEvent;
            } catch {
              continue;
            }

            switch (event.type) {
              case "token":
                callbacks.onToken(event.delta);
                setState((s) => ({ ...s, streamingDelta: s.streamingDelta + event.delta }));
                break;

              case "step":
                callbacks.onStep(event);
                setState((s) => {
                  const nodes = new Set(s.activeNodes);
                  if (event.status === "started") nodes.add(event.node);
                  else nodes.delete(event.node);
                  return { ...s, activeNodes: nodes };
                });
                break;

              case "interrupt":
                setState((s) => ({ ...s, status: "interrupted", interrupt: event }));
                break;

              case "artifact":
                setState((s) => ({ ...s, artifacts: [...s.artifacts, event] }));
                break;

              case "progress":
                setState((s) => ({
                  ...s,
                  progress: { ...s.progress, [event.job_id]: event },
                }));
                break;

              case "done":
                setState((s) => ({ ...s, status: "done", streamingDelta: "" }));
                callbacks.onDone(event);
                break;

              case "error":
                setState((s) => ({ ...s, status: "error", error: event.message }));
                callbacks.onError(event.message);
                break;
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    },
    []
  );

  const sendMessage = useCallback(
    async (
      message: string,
      callbacks: { onToken: OnToken; onStep: OnStep; onDone: OnDone; onError: OnError }
    ) => {
      if (!threadId) return;

      abortRef.current?.abort();
      abortRef.current = new AbortController();

      resetStream();

      try {
        const res = await fetchRunStream(threadId, message);
        if (!res.ok) throw new Error(`Run failed: ${res.status}`);
        await readStream(res, callbacks);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setState((s) => ({ ...s, status: "error", error: msg }));
        callbacks.onError(msg);
      }
    },
    [threadId, resetStream, readStream]
  );

  const resume = useCallback(
    async (
      payload: {
        action: "approve" | "edit" | "reject";
        plan?: Record<string, unknown>[];
        tool_args?: Record<string, unknown>;
        reason?: string;
      },
      callbacks: { onToken: OnToken; onStep: OnStep; onDone: OnDone; onError: OnError }
    ) => {
      if (!threadId) return;

      resetStream();

      try {
        const res = await fetchResumeStream(threadId, payload);
        if (!res.ok) throw new Error(`Resume failed: ${res.status}`);
        await readStream(res, callbacks);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setState((s) => ({ ...s, status: "error", error: msg }));
        callbacks.onError(msg);
      }
    },
    [threadId, resetStream, readStream]
  );

  return { state, sendMessage, resume };
}
