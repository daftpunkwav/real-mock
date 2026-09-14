"""Voice and outline mixin aggregation."""

from realmock.domains.interview.realtime.control.hint import ReferenceHintMixin
from realmock.domains.interview.realtime.voice.pipeline import VoicePipelineMixin


class MediaStackMixin(VoicePipelineMixin, ReferenceHintMixin):
    """STT/TTS pipeline and reference outline."""


__all__ = ["MediaStackMixin"]
