/** Interview feature barrel: room UI, WS hooks, and shared pure helpers. */

export { ChatBubble } from "./components/ChatBubble";
export { VideoPanel, type VideoPanelHandle } from "./components/VideoPanel";
export { InterviewRoomView } from "./components/InterviewRoomView";
export { useInterviewWS } from "./hooks/room/useInterviewWS";
export { useInterviewRoomBootstrap, useInterviewRoom } from "./hooks/room";
export { isLikelyEchoOfAssistant, normalizeEchoText } from "./echo";
export { toVisibleChatMessages } from "./messages";
export { buildNextRoundIndex, selectEligibleProcesses, type EligibleProcess } from "./processes";
