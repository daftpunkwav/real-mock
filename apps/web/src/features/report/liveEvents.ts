/** Live report-generation progress: pure event reducer + event type. */

export type ReportLiveEvent = {
  type: string;
  stage?: string;
  batch?: string;
  name?: string;
  status?: string;
  result?: string;
  content?: string;
};

export type ReportLiveState = {
  events: ReportLiveEvent[];
};

/** Keep the last 40 events (no coalescing). */
export const REPORT_LIVE_MAX_EVENTS = 40;

export function applyReportLiveEvent(
  state: ReportLiveState,
  event: ReportLiveEvent,
): ReportLiveState {
  if (event.type !== "stage" && event.type !== "tool_step" && event.type !== "thinking") {
    return state;
  }
  const events = [...state.events, event].slice(-REPORT_LIVE_MAX_EVENTS);
  return { events };
}

export function emptyReportLiveState(): ReportLiveState {
  return { events: [] };
}
