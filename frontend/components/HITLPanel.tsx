"use client";

import { useState } from "react";
import type { InterruptEvent, PlanInterruptData, PlanStep, ToolInterruptData } from "@/types/events";

interface Props {
  interrupt: InterruptEvent;
  onApprove: () => void;
  onEdit: (plan: Record<string, unknown>[]) => void;
  onReject: (reason: string) => void;
}

const AGENT_COLORS: Record<string, string> = {
  research: "bg-blue-100 text-blue-800",
  image: "bg-purple-100 text-purple-800",
  video: "bg-pink-100 text-pink-800",
  tool: "bg-yellow-100 text-yellow-800",
};

function PlanView({
  steps,
  editMode,
  editJson,
  onJsonChange,
}: {
  steps: PlanStep[];
  editMode: boolean;
  editJson: string;
  onJsonChange: (v: string) => void;
}) {
  if (editMode) {
    return (
      <textarea
        className="mt-2 h-48 w-full rounded border border-gray-300 p-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
        value={editJson}
        onChange={(e) => onJsonChange(e.target.value)}
        spellCheck={false}
      />
    );
  }

  return (
    <ol className="mt-2 space-y-1">
      {steps.map((step, i) => (
        <li key={i} className="flex items-start gap-2 rounded bg-gray-50 px-3 py-2 text-sm">
          <span className="mt-0.5 w-5 shrink-0 text-center text-xs text-gray-400">{i + 1}</span>
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${AGENT_COLORS[step.agent] ?? "bg-gray-100 text-gray-700"}`}
          >
            {step.agent}
          </span>
          <span className="text-gray-700">{step.goal}</span>
        </li>
      ))}
    </ol>
  );
}

function ToolView({ data }: { data: ToolInterruptData }) {
  return (
    <div className="mt-2 rounded bg-gray-50 p-3 text-sm">
      <div className="mb-1 font-medium text-gray-700">
        Tool: <code className="rounded bg-gray-200 px-1">{data.tool_name ?? "unknown"}</code>
      </div>
      {data.args && (
        <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-gray-600">
          {JSON.stringify(data.args, null, 2)}
        </pre>
      )}
    </div>
  );
}

export function HITLPanel({ interrupt, onApprove, onEdit, onReject }: Props) {
  const isPlan = interrupt.subject === "plan";
  const planData = interrupt.data as PlanInterruptData;
  const toolData = interrupt.data as ToolInterruptData;

  const steps: PlanStep[] = isPlan ? (planData.steps ?? []) : [];
  const [editMode, setEditMode] = useState(false);
  const [editJson, setEditJson] = useState(() => JSON.stringify(steps, null, 2));
  const [editError, setEditError] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejecting, setRejecting] = useState(false);

  function handleEdit() {
    try {
      const parsed = JSON.parse(editJson) as Record<string, unknown>[];
      setEditError(null);
      onEdit(parsed);
    } catch {
      setEditError("Invalid JSON — fix it before submitting.");
    }
  }

  return (
    <div className="my-3 rounded-lg border border-amber-300 bg-amber-50 p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-semibold text-amber-800">
          {isPlan ? "Review Plan" : "Approve Tool Call"}
        </span>
        <span className="rounded-full bg-amber-200 px-2 py-0.5 text-xs text-amber-900">
          Awaiting approval
        </span>
      </div>

      {isPlan ? (
        <PlanView
          steps={steps}
          editMode={editMode}
          editJson={editJson}
          onJsonChange={(v) => {
            setEditJson(v);
            setEditError(null);
          }}
        />
      ) : (
        <ToolView data={toolData} />
      )}

      {editError && <p className="mt-1 text-xs text-red-600">{editError}</p>}

      {rejecting && (
        <div className="mt-2">
          <input
            type="text"
            className="w-full rounded border border-gray-300 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-300"
            placeholder="Reason for rejection (optional)"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onReject(rejectReason);
              if (e.key === "Escape") setRejecting(false);
            }}
            autoFocus
          />
        </div>
      )}

      <div className="mt-3 flex gap-2">
        {!editMode && !rejecting && (
          <button
            onClick={onApprove}
            className="rounded bg-green-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-green-700"
          >
            Approve
          </button>
        )}

        {isPlan && !rejecting && (
          <button
            onClick={() => setEditMode((v) => !v)}
            className="rounded border border-gray-300 bg-white px-4 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            {editMode ? "Cancel edit" : "Edit"}
          </button>
        )}

        {editMode && (
          <button
            onClick={handleEdit}
            className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
          >
            Submit edit
          </button>
        )}

        {!rejecting && (
          <button
            onClick={() => setRejecting(true)}
            className="rounded border border-red-200 bg-white px-4 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50"
          >
            Reject
          </button>
        )}

        {rejecting && (
          <>
            <button
              onClick={() => onReject(rejectReason)}
              className="rounded bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700"
            >
              Confirm reject
            </button>
            <button
              onClick={() => setRejecting(false)}
              className="rounded border border-gray-300 bg-white px-4 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50"
            >
              Cancel
            </button>
          </>
        )}
      </div>
    </div>
  );
}
