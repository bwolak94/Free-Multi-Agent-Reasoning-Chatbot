"use client";

import { useEffect, useRef } from "react";
import type { ArtifactEvent, ProgressEvent } from "@/types/events";
import { ProgressBar } from "./ProgressBar";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

interface Props {
  messages: Message[];
  artifacts: ArtifactEvent[];
  progress: Record<string, ProgressEvent>;
  activeNodes: Set<string>;
}

function ArtifactDisplay({ artifact }: { artifact: ArtifactEvent }) {
  if (artifact.artifact_type === "image") {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={artifact.url}
        alt="Generated image"
        className="mt-2 max-w-full rounded-lg shadow"
      />
    );
  }

  if (artifact.artifact_type === "video") {
    return (
      <video controls className="mt-2 max-w-full rounded-lg shadow">
        <source src={artifact.url} type="video/mp4" />
      </video>
    );
  }

  return (
    <a
      href={artifact.url}
      target="_blank"
      rel="noopener noreferrer"
      className="mt-2 block text-sm text-blue-600 underline"
    >
      Artifact: {artifact.artifact_type}
    </a>
  );
}

function NodeBadge({ node }: { node: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-400" />
      {node}
    </span>
  );
}

export function ChatView({ messages, artifacts, progress, activeNodes }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeNodes]);

  const progressList = Object.values(progress);

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              msg.role === "user"
                ? "rounded-br-sm bg-blue-600 text-white"
                : "rounded-bl-sm bg-white text-gray-800 shadow-sm ring-1 ring-gray-100"
            }`}
          >
            <p className="whitespace-pre-wrap">{msg.content}</p>
            {msg.streaming && (
              <span className="mt-1 inline-block h-3 w-0.5 animate-pulse bg-current opacity-70" />
            )}
          </div>
        </div>
      ))}

      {artifacts.map((art) => (
        <div key={art.artifact_id} className="flex justify-start">
          <div className="max-w-[80%]">
            <ArtifactDisplay artifact={art} />
          </div>
        </div>
      ))}

      {progressList.map((p) => (
        <ProgressBar key={p.job_id} progress={p} />
      ))}

      {activeNodes.size > 0 && (
        <div className="flex items-center gap-2">
          {Array.from(activeNodes).map((node) => (
            <NodeBadge key={node} node={node} />
          ))}
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
