"""TTS edge text-handling unit tests: sentence segmentation, soft flush, markdown strip, emotion markers."""

from __future__ import annotations

from realmock.platform.capabilities.voice.tts.providers.edge import (
    extract_emotion,
    should_flush_sentence_buffer,
    split_sentences,
)


def test_split_sentences_includes_semicolon_ellipsis():
    parts = split_sentences("First sentence. Second sentence; third sentence… fourth sentence!")
    assert len(parts) >= 3
    assert any("First sentence" in p for p in parts)


def test_soft_flush_on_comma_after_min_chars():
    short = "Hello, world"
    assert not should_flush_sentence_buffer(short)
    long = ("Test" * 17) + "，"
    assert should_flush_sentence_buffer(long, soft_min=14)
    assert should_flush_sentence_buffer("I'm finished.")
    assert should_flush_sentence_buffer("Okay;")
    assert should_flush_sentence_buffer("Character" * 48)


def test_plain_text_strips_markdown_stars():
    from realmock.platform.capabilities.voice.tts.providers.edge import plain_text_for_tts

    assert plain_text_for_tts("Please confirm the **GitHub** username") == "Please confirm the GitHub username"
    assert "*" not in plain_text_for_tts("This is *italic* and **bold**")
    # NOTE: tautology guard ("Normal text" never contains "Star"); kept as-is.
    assert "Star" not in plain_text_for_tts("Normal text")


def test_extract_emotion_from_marker():
    assert extract_emotion("Great.[emotion:smile]Continue") == "smile"
    assert extract_emotion("No marker") == "neutral"
