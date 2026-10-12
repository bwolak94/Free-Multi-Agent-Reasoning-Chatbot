export interface TokenEvent {
  type: "token";
  delta: string;
}

export interface StepEvent {
  type: "step";
  node: string;
  status: "started" | "done" | "error";
  step_index?: number | null;
}

export interface InterruptEvent {
  type: "interrupt";
  subject: "plan" | "tool";
  data: PlanInterruptData | ToolInterruptData;
}

export interface PlanInterruptData {
  steps?: PlanStep[];
  [key: string]: unknown;
}

export interface ToolInterruptData {
  tool_name?: string;
  args?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PlanStep {
  agent: string;
  goal: string;
  status: string;
  deps?: number[];
  inputs?: Record<string, unknown>;
}

export interface ArtifactEvent {
  type: "artifact";
  artifact_id: string;
  url: string;
  artifact_type: string;
}

export interface ProgressEvent {
  type: "progress";
  job_id: string;
  percent: number;
  message: string;
}

export interface DoneEvent {
  type: "done";
  thread_id: string;
  run_id: string;
}

export interface ErrorEvent {
  type: "error";
  code: string;
  message: string;
}

export type SSEEvent =
  | TokenEvent
  | StepEvent
  | InterruptEvent
  | ArtifactEvent
  | ProgressEvent
  | DoneEvent
  | ErrorEvent;
