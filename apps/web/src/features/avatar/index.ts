/** Avatar capability layer public entrance: Cross-feature import is only allowed through this, and the internal implementation path is not available to the public. */

export { AvatarStage, prefetchAvatar } from "./AvatarStage";
export type { AvatarStageProps } from "./AvatarStage";
// The interview room publishes the TTS playback level into the avatar's
// meter; the sink is part of the public surface so no feature reaches into
// the avatar internals.
export { publishTTSLevel } from "./levelSink";
