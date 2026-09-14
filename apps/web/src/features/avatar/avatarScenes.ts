/** CSS portrait backgrounds; separate from AvatarStage's stage-level scene table. */

export const SCENES: Record<string, string> = {
  meeting_room: "/scenes/meeting_room.svg",
  glass_office: "/scenes/glass_office.svg",
  online_interview: "/scenes/online_interview.svg",
  boardroom: "/scenes/boardroom.svg",
  startup_loft: "/scenes/startup_loft.svg",
  library_corner: "/scenes/library_corner.svg",
};

export const SCENE_FALLBACK: Record<string, string> = {
  meeting_room: "linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #1a2f4a 100%)",
  glass_office: "linear-gradient(135deg, #2c3e50 0%, #4a6741 100%)",
  online_interview: "linear-gradient(135deg, #0f172a 0%, #334155 100%)",
  boardroom: "linear-gradient(135deg, #1c1917 0%, #57534e 100%)",
  startup_loft: "linear-gradient(135deg, #292524 0%, #78716c 100%)",
  library_corner: "linear-gradient(135deg, #1e1b4b 0%, #4338ca 100%)",
};
