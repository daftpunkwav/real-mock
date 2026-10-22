/** Interview feature barrel: room UI, WS hooks, and shared pure helpers. */

export { ChatBubble } from "./components/ChatBubble";
export { VideoPanel, type VideoPanelHandle } from "./components/VideoPanel";
export { InterviewRoomView } from "./components/InterviewRoomView";
export { useInterviewWS } from "./hooks/room/useInterviewWS";
export { useInterviewRoomBootstrap, useInterviewRoom } from "./hooks/room";
export { isLikelyEchoOfAssistant, normalizeEchoText } from "./echo";
export { toVisibleChatMessages } from "./messages";
// The multi-round helpers live in lib/interviewProcesses so other features can
// use them without pulling in the room UI; they are not re-exported here, so
// the barrel stays the interview feature's own surface.
