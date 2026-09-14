"use client";

import { useParams } from "next/navigation";
import { InterviewRoomView, useInterviewRoom } from "@/features/interview";

export default function InterviewRoomPage() {
  const params = useParams();
  const sessionId = Number(params.id);
  const room = useInterviewRoom(sessionId);
  return <InterviewRoomView room={room} />;
}
