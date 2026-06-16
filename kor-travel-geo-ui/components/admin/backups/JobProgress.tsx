"use client";

import { useEffect, useState } from "react";
import type { LoadJobStatus } from "@/lib/api";
import { stagePhase, terminalJobState } from "@/lib/backup-workflow";
import {
  estimateEtaSeconds,
  formatEta,
  latestLogLine,
  progressPercent
} from "@/lib/job-progress";
import { type EventSourceFactory, useJobEvents } from "@/lib/use-job-events";

/**
 * Live per-job progress (T-251): subscribes to the job's SSE ``status`` stream and shows
 * stage, a progress bar, percent, ETA, and the latest log line (byte detail). Falls back to
 * the polled ``job`` row when SSE is unavailable; the stream auto-closes on a terminal state.
 */
export function JobProgress({
  job,
  eventSourceFactory,
  onTerminal
}: {
  job: LoadJobStatus;
  eventSourceFactory?: EventSourceFactory;
  onTerminal?: () => void;
}) {
  const live = useJobEvents(job.job_id, {
    enabled: !terminalJobState(job.state),
    eventSourceFactory,
    onTerminal
  });
  const current = live ?? job;
  const isTerminal = terminalJobState(current.state);
  // Tick a clock (off the render path) so the ETA refreshes once a second while running.
  const [nowMs, setNowMs] = useState(0);
  useEffect(() => {
    setNowMs(Date.now());
    if (isTerminal) return;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isTerminal]);

  const pct = progressPercent(current.progress);
  const eta =
    isTerminal || nowMs === 0
      ? null
      : estimateEtaSeconds(current.started_at, current.progress, nowMs);
  const log = latestLogLine(current);

  return (
    <div className="job-progress">
      <div className="progress-label">
        <strong>
          {current.kind} · {current.job_id.slice(0, 8)}
        </strong>
        <span>
          {stagePhase(current.current_stage)} · {pct}% · ETA {formatEta(eta)}
        </span>
      </div>
      <div className="progress-shell">
        <div className="progress-bar" style={{ width: `${pct}%` }} />
      </div>
      {log ? <small className="job-progress-log">{log}</small> : null}
    </div>
  );
}
