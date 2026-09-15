"""Settings stage-test regressions: packaged STT fixture and Chinese normalization."""

from __future__ import annotations

from pathlib import Path

from realmock.domains.settings.services.stage_tests import _normalize_zh, load_fixture


def test_stt_fixture_packaged_locally():
    wav, expected = load_fixture()
    assert len(wav) > 1000
    assert wav[:4] == b"RIFF"
    # Packaged fixture carries the Chinese expectation; the English string is
    # only the missing-file fallback in load_fixture.
    assert expected
    fixture_dir = (
        Path(__file__).resolve().parents[2] / "src" / "realmock" / "platform" / "data" / "stt_fixtures"
    )
    assert (fixture_dir / "audio_zh_growth.wav").is_file()
    assert (fixture_dir / "expected.json").is_file()


def test_normalize_match():
    # _normalize_zh is a mechanical lower + strip-non-word normalization,
    # not a semantic translator: pin the actual contract.
    assert _normalize_zh("Up 50% year over year.") == "up50yearoveryear"
    assert _normalize_zh("  Hello, World! ") == "helloworld"
    assert _normalize_zh("") == ""
