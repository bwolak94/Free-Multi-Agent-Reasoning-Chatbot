const BASE = "/api";

export async function createThread(threadId?: string): Promise<string> {
  const res = await fetch(`${BASE}/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId ?? undefined }),
  });
  if (!res.ok) throw new Error(`createThread failed: ${res.status}`);
  const data = (await res.json()) as { id: string };
  return data.id;
}

export async function resumeThread(
  threadId: string,
  payload: {
    action: "approve" | "edit" | "reject";
    plan?: Record<string, unknown>[];
    tool_args?: Record<string, unknown>;
    reason?: string;
  }
): Promise<Response> {
  const res = await fetch(`${BASE}/threads/${threadId}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res;
}

export function streamRun(threadId: string, message: string): Response {
  // Returns a raw Response — caller reads body as ReadableStream
  throw new Error("Use fetch directly; this is a placeholder for typing");
}

export async function fetchRunStream(
  threadId: string,
  message: string
): Promise<Response> {
  return fetch(`${BASE}/threads/${threadId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

export async function fetchResumeStream(
  threadId: string,
  payload: {
    action: "approve" | "edit" | "reject";
    plan?: Record<string, unknown>[];
    tool_args?: Record<string, unknown>;
    reason?: string;
  }
): Promise<Response> {
  return fetch(`${BASE}/threads/${threadId}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
