"use client";

import type { ProgressEvent } from "@/types/events";

interface Props {
  progress: ProgressEvent;
}

export function ProgressBar({ progress }: Props) {
  return (
    <div className="my-2 rounded bg-gray-100 p-3">
      <div className="mb-1 flex items-center justify-between text-xs text-gray-600">
        <span>{progress.message}</span>
        <span>{progress.percent}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
        <div
          className="h-2 rounded-full bg-blue-500 transition-all duration-300"
          style={{ width: `${progress.percent}%` }}
        />
      </div>
    </div>
  );
}
