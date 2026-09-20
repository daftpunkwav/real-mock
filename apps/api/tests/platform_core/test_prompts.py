"""Output sanitization for agent text: emoji/kaomoji stripping must not eat content.

Conventions: pure string assertions — the strip helpers run on every streamed
chunk, so a false positive silently deletes real characters.
"""

from __future__ import annotations

from realmock.platform.core.prompts import strip_emojis

# CJK prose uses an unspaced colon before Latin terms, which is exactly the
# shape of a ":D" / ":P" face; "XD" also appears inside words.
_KEEP = (
    "面试重点：Python 的 GIL",
    "详见：Docker 文档",
    "他说：Pandas 很好用",
    "调试器：Xdebug 配置",
    "提示：(见附录)",
    "成本：Django 偏高",
)

_STRIP = (
    ("今天很开心 :)", "今天很开心 "),
    ("状态不错 :D", "状态不错 "),
    ("有点失落 :(", "有点失落 "),
    ("这个答案很棒 ;)", "这个答案很棒 "),
    ("哈哈 XD 太好了", "哈哈 太好了"),
)


def test_strip_emojis_keeps_colon_prefixed_latin_terms() -> None:
    for text in _KEEP:
        assert strip_emojis(text) == text


def test_strip_emojis_removes_face_emoticons() -> None:
    for text, expected in _STRIP:
        assert strip_emojis(text) == expected


def test_strip_emojis_removes_pictographs() -> None:
    assert "😀" not in strip_emojis("很好 😀")
