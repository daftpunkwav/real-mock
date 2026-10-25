"""Credential redaction for log output and user-facing error text.

Four entry points, one job each:

- :func:`redact_api_key` — one **whole value** that may itself be a
  credential (a provider key, an ``Authorization`` header, a PEM block);
- :func:`redact_secrets_in_text` — **free-form text** (an exception
  message) that may carry a credential anywhere inside it;
- :func:`redact_log_value` — one **runtime value** on its way into a log
  line: the whole-value rule, the token-by-token scan for a multi-word
  value, and the masking of the URLs inside it;
- :func:`redact_log_template` — a **format template** (the ``"x=%s"``
  pattern of a log call): the whole-value rule and the URL masking, but no
  token-by-token scan, so the ``%s`` / ``%d`` placeholders and the ordinary
  long words of the message survive. The placeholders are set aside before
  the rule runs, because the rule replaces the value it considers a
  credential with a fixed constant.

Besides the key shapes themselves, a request URL is a place where a credential
travels without looking like a key: a query parameter can carry the secret and
the HTTP client logs the full request URL. The two log entry points mask
those query values, and the credential shapes that travel in a URL path or
fragment.

The provider key prefixes are declared once, in ``_PROVIDER_KEY_PREFIXES``:
the whole-value heuristic and the token-by-token scanner both read that
table, so a new provider format is one entry instead of an edit in two
rules that can drift apart.
"""

from __future__ import annotations

import re

#: Provider key prefixes: the prefix itself, the minimum length of the
#: payload that must follow it, and whether the prefix is matched
#: case-insensitively (the Google prefix is written ``AIza``).
#:
#: The whole-value heuristic and the token-by-token scanner both read this
#: table, so a new provider format is declared once instead of in two rules
#: that can drift apart.
_PROVIDER_KEY_PREFIXES: tuple[tuple[str, int, bool], ...] = (
    ("aiza", 10, True),
    ("sk-ant-", 8, False),
    ("sk-", 8, False),
    ("sk_", 8, False),
)


def _looks_like_api_key(v: str) -> bool:
    """Whether the value starts with a provider key prefix."""
    lowered = v.lower()
    return any(
        lowered.startswith(prefix) if case_insensitive else v.startswith(prefix)
        for prefix, _min_payload, case_insensitive in _PROVIDER_KEY_PREFIXES
    )


def _looks_like_secret(v: str) -> bool:
    """Heuristic: determine whether a string looks like a secret (API Key, token, UUID, etc.).

    Heuristic rules:

    - Length must be ``>= 20`` (typical API Keys are much longer);
    - Must contain both letters and digits (to avoid misclassifying ordinary short phrases);
    - Must not contain spaces (to avoid truncation mistakes).
    """
    if len(v) < 20 or " " in v:
        return False
    has_letter = any(c.isalpha() for c in v)
    has_digit = any(c.isdigit() for c in v)
    return has_letter and has_digit


def _provider_key_pattern(payload_class: str = "A-Za-z0-9_-") -> str:
    """Regex alternatives for the provider key prefixes of the table.

    Each prefix carries its own minimum payload length, so the scanner reads
    the same table the whole-value heuristic reads. The URL scanner widens
    the payload class: a percent-encoded payload character must not end the
    match there.
    """
    alternatives: list[str] = []
    for prefix, min_payload, case_insensitive in _PROVIDER_KEY_PREFIXES:
        escaped = re.escape(prefix)
        if case_insensitive:
            escaped = f"(?i:{escaped})"
        alternatives.append(f"{escaped}[{payload_class}]{{{min_payload},}}")
    return "|".join(alternatives)


# Substring scanner for free-form text (exception messages, observations):
# provider key prefixes, Bearer/Token/Basic schemes, labeled key assignments
# (``api_key=...``), and any standalone run of 20+ key characters
# (letters/digits/hyphen/underscore) delimited by other characters.
# ``basic`` carries its own shorter minimum and the base64 alphabet
# (``+/=``): a Basic payload is base64, the padding and separator characters
# break the standalone-run rule, so the scheme form is the only net that
# catches it; the floor is 4 because valid base64 lengths are multiples of 4,
# so anything shorter encodes nothing. The scheme/assignment forms accept the
# full base64 alphabet too — a standard-base64 payload carries ``+``/``/``
# that would otherwise split the token in half — and the underscore that
# URL-safe tokens use, and tolerate up to two ``=`` padding characters at the
# end. The delimiter alternation ``(?:\s*[:=]\s*|\s+)`` spans the written
# forms ("key: v", "key = v", "bearer v") and an optional opening quote, and
# the short scheme (floor 6) and labeled (floor 4) alternatives catch a
# compact quoted credential ("rejected Bearer abc123", "api_key: abc123"):
# their digit lookahead is what keeps ordinary prose out — the words that
# follow a scheme or label word in prose ("authorization required", "api key
# required", "secret sauce") are pure alphabetic, so they survive.
# Deliberately conservative: the last alternative does NOT require mixed
# alphanumerics, so ordinary long words are masked too — a false positive
# costs a little readability, a false negative leaks a key.
_SUBSTR_KEY_RE = re.compile(
    _provider_key_pattern()
    + r"|(?i:bearer|token|authorization)(?:\s*[:=]\s*|\s+)[\"\']?"
    + r"[A-Za-z0-9_.+/-]{12,}={0,2}"
    + r"|(?i:bearer|token|authorization)(?:\s*[:=]\s*|\s+)[\"\']?"
    + r"(?=[A-Za-z0-9_.+/-]*[0-9])[A-Za-z0-9_.+/-]{6,}={0,2}"
    + r"|(?i:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|secret|password|passwd)"
    + r"(?:\s*[:=]\s*|\s+)[\"\']?"
    + r"(?=[A-Za-z0-9_.+/-]*[0-9])[A-Za-z0-9_.+/-]{4,}={0,2}"
    + r"|(?i:basic)\s+[A-Za-z0-9+/=]{4,}"
    + r"|(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])",
)

# The credential shapes that can travel inside a URL path or fragment. The
# provider key prefixes and the scheme/assignment forms — including the
# labeled keys, a fragment is where OAuth flows park both ``access_token=``
# and ``api_key=`` — with the same base64 alphabet, the underscore, and the
# ``%`` of a percent-encoded payload, and a short assignment floor (1): the
# payload can be very short, while everything else in a path or fragment
# that matters stays diagnosable. The last alternative is the
# standalone-run rule tightened for URLs: a path or fragment can also carry
# an unprefixed token (a signed-path credential), so a 20+ run of key
# characters is masked unless the token-level callback (see
# ``_mask_url_credentials``) clears it as an ordinary identifier. The run
# class carries ``+`` so a standard-base64 token is not split at it; ``/``
# stays out — it is the path separator. The Basic scheme form is not listed:
# path and fragment carry no unencoded spaces, so its whitespace anchor can
# never match there — a Basic payload in a query is masked wholesale by
# ``_mask_query_values``.
_URL_CREDENTIAL_RE = re.compile(
    _provider_key_pattern("A-Za-z0-9_.%+-")
    + r"|(?i:bearer|token|authorization)[:=]\s*[A-Za-z0-9_.%+/-]{1,}={0,2}"
    + r"|(?i:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|secret|password|passwd)"
    + r"[:=]\s*[A-Za-z0-9_.%+/-]{1,}={0,2}"
    + r"|(?<![A-Za-z0-9_.%+-])([A-Za-z0-9_.%+-]{20,})(?![A-Za-z0-9_.%+-])",
)

# A canonical UUID: the one 20+ mixed-alphanumeric run that stays readable in
# a URL path. Resource identifiers are overwhelmingly UUID-shaped, and
# correlating a log line with a record needs the full id; anything else that
# mixes letters and digits at that length is treated as a token.
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def redact_api_key(value: str | None) -> str:
    """Redact one whole value that may itself be a credential.

    Covers all of the following:
    - Provider Keys (OpenAI/Anthropic/Google/StepFun);
    - ``Authorization: Bearer xxxx`` / ``authorization=xxxx`` header forms;
    - PEM private-key blocks (including newlines);
    - tokens heuristically identified as "long enough + mixed alphanumeric + no spaces".

    Ordinary short phrases and log templates (``HTTP/%s ...``) are not misclassified.
    A credential buried inside a sentence is not a whole value: use
    :func:`redact_secrets_in_text` for that.
    """
    if not value:
        return ""
    v = value.strip()
    if len(v) <= 8:
        # Short strings are not desensitized by default to avoid accidentally damaging Chinese phrases/paths/short tokens themselves.
        return v

    # PEM/certificate block: contains newlines, which the heuristic misses
    if "-----BEGIN" in v.upper():
        return "***PEM_REDACTED***"

    # For Authorization / authorization=xxx forms: keep only the scheme, then redact the entire token
    lowered = v.lower()
    if lowered.startswith("authorization"):
        scheme_idx = v.find(":") if ":" in v else v.find("=")
        if scheme_idx >= 0:
            head = v[: scheme_idx + 1]
            return f"{head} ***"
        return "Authorization ***"

    # Explicit Bearer / Token prefix
    for prefix in ("bearer ", "token ", "basic "):
        if lowered.startswith(prefix):
            return f"{prefix[:1].upper()}{prefix[1:]}***"

    if _looks_like_api_key(v):
        return f"{v[:4]}***{v[-4:]}"

    # Heuristic secrets (such as irregular tokens/UUIDs) can only use "first and last 4 characters" desensitization
    if _looks_like_secret(v):
        return f"{v[:4]}***{v[-4:]}"

    return v


# URL-shaped substrings inside free-form text (log lines, exception text).
# The trailing punctuation that usually follows a URL in prose is excluded so
# it stays outside the match and survives the rewrite. The single group lets
# ``re.split`` keep the URL matches, so the surrounding prose is redacted
# separately.
# The closing bracket is NOT a terminator: an IPv6 literal authority
# ("http://[2001:db8::1]:8080/?key=...") contains one mid-URL, and cutting
# there would hand the query to the prose path, whose rules cannot mask a
# short named value. A bracket that trails prose ("page[1]") stays inside
# the match and survives the URL treatment untouched, so nothing is lost —
# and when the matched URL carries no opening bracket at all, the trailing
# prose brackets are split back off before the URL treatment runs.
_URL_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://[^\s\"'<>,;)\}]+)")


# A ``%``-format specifier (as the logging machinery understands it). A
# template may carry one inside a URL — masking it would delete the
# placeholder and break the log call, so such a value is kept as it is.
# The flag and width runs are possessive: both accept ``0`` (as the
# zero-padding flag and as a width digit), and plain greedy runs would hand
# a zero run back and forth across the boundary, retrying every split while
# no conversion character closes the specifier — quadratic on a long zero
# run. A possessive run commits to its longest match, which no later part of
# the pattern can resume, so the recognized specifiers stay the same.
_FORMAT_SPEC_RE = re.compile(
    r"%(?:\([^)]*\))?[-+#0 ]*+[0-9*]*+(?:\.[0-9*]*)?[hlL]?[diouxXeEfFgGcrsa%]"
)


def _mask_query_values(query: str, *, preserve_specifiers: bool) -> str:
    """Replace every query-parameter value with ``***`` (names are kept).

    ``preserve_specifiers`` is the template pipeline's need: a placeholder
    (``?key=%s``) must survive or the substitution balance breaks and the
    log line is lost, so a value carrying a specifier keeps each specifier
    and masks the payload around it. Outside a template a specifier-looking
    sequence is just text — and part of a possible credential — so every
    value is masked whole.
    """
    masked: list[str] = []
    for part in query.split("&"):
        name, sep, value = part.partition("=")
        if not sep:
            masked.append(part)
        elif preserve_specifiers and _FORMAT_SPEC_RE.search(value):
            pieces: list[str] = []
            cursor = 0
            for spec in _FORMAT_SPEC_RE.finditer(value):
                if spec.start() > cursor:
                    pieces.append("***")
                pieces.append(spec.group(0))
                cursor = spec.end()
            if cursor < len(value):
                pieces.append("***")
            masked.append(f"{name}={''.join(pieces)}")
        else:
            masked.append(f"{name}=***")
    return "&".join(masked)


def _mask_url_credentials(text: str) -> str:
    """Mask the credential shapes inside a URL path or fragment.

    A credential does not only travel in the query: a vendor that puts it in
    the path (``/v1/sk-.../chat``), an OAuth fragment (``#access_token=...``)
    or a signed path (``/files/<token>/content``) would otherwise reach the
    log in clear text. The free-text standalone-run rule is deliberately not
    reused as-is: a request path carries opaque identifiers (session ids,
    object keys) that operators need. The standalone run therefore survives
    only when it is not token-shaped: a canonical UUID keeps its full form,
    and a run without both letters and digits (slugs, pure-digit ids) stays
    readable — anything else at that length is masked.
    """

    def _mask(match: re.Match[str]) -> str:
        token = match.group(0)
        if match.group(1) is not None:
            # Standalone run (the only capturing alternative): a canonical
            # UUID stays whole, and the run must mix letters and digits to
            # be treated as a token.
            if _UUID_RE.fullmatch(token) or not (
                any(c.isdigit() for c in token) and any(c.isalpha() for c in token)
            ):
                return token
        return f"{token[:4]}***" if len(token) > 8 else "***"

    return _URL_CREDENTIAL_RE.sub(_mask, text)


def _mask_url(url: str, *, preserve_specifiers: bool = False) -> str:
    """Mask the query values, the userinfo password and the credentials of one URL.

    The fragment is partitioned off first, so it is scanned whether or not a
    query precedes it — a credential parked after ``#`` in a query-less URL
    would otherwise ride along inside the path segment and escape the
    assignment floor. The userinfo username is scanned too: a credential
    supplied as a URL username (``https://sk-...@host/``) is as sensitive as
    one in the password. ``preserve_specifiers`` forwards the template
    pipeline's placeholder need to the query treatment.
    """
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url
    body, hash_, fragment = rest.partition("#")
    head, qmark, query = body.partition("?")
    authority, slash, path = head.partition("/")
    if "@" in authority:
        userinfo, _, host = authority.rpartition("@")
        if ":" in userinfo:
            user, _, _password = userinfo.partition(":")
            userinfo = f"{_mask_url_credentials(user)}:***"
        else:
            userinfo = _mask_url_credentials(userinfo)
        authority = f"{userinfo}@{host}"
    path = _mask_url_credentials(path)
    head = f"{authority}{slash}{path}"
    if hash_:
        fragment = _mask_url_credentials(fragment)
    if not qmark:
        return f"{scheme}://{head}{hash_}{fragment}"
    return (
        f"{scheme}://{head}"
        f"?{_mask_query_values(query, preserve_specifiers=preserve_specifiers)}"
        f"{hash_}{fragment}"
    )


def _redact_fragment(text: str, *, scan_embedded: bool) -> str:
    """Apply the whole-value key heuristic to one fragment, keeping its spacing.

    :func:`redact_api_key` strips its input, so it cannot be applied to a
    fragment of a longer value without eating the surrounding spaces.

    ``scan_embedded`` adds the token-by-token scanner for whatever the
    whole-value rule did not catch — a credential buried in a sentence is
    not a whole value, and neither is a single unrecognized token (a pure
    alphabetic run has no digit for the heuristic). The whitespace of the
    fragment is irrelevant: the scan is keyed on the token shapes, not on
    the prose around them.
    """
    stripped = text.strip()
    if not stripped:
        return text
    masked = redact_api_key(stripped)
    if masked != stripped:
        return text.replace(stripped, masked, 1)
    if not scan_embedded:
        return text
    return _mask_tokens_in_text(text)


def _mask_tokens_in_text(value: str) -> str:
    """Mask credentials token by token; no URL handling, no whole-value step."""
    if not value:
        return ""

    def _mask(m: re.Match[str]) -> str:
        token = m.group(0)
        return f"{token[:4]}***" if len(token) > 8 else "***"

    return _SUBSTR_KEY_RE.sub(_mask, value)


def _trim_trailing_brackets(url: str) -> tuple[str, str]:
    """Split the trailing prose brackets a URL match swallowed.

    ``]`` is a URL character (an IPv6 authority's closing bracket), so the
    match runs over one — but a matched URL with more ``]`` than ``[`` has
    prose brackets at its tail, and keeping them inside the match would mask
    a query placeholder together with the bracket (``"...?key=%s]"`` loses
    the ``%s`` and the log line with it), eat the bracket that closes a
    Markdown link, or swallow a closing bracket after an IPv6 URL whose
    authority brackets already balance.
    """
    surplus = url.count("]") - url.count("[")
    if surplus <= 0:
        return url, ""
    body = url.rstrip("]")
    brackets = url[len(body) :][:surplus]
    return url[: len(url) - len(brackets)], brackets


def _split_url_text(value: str) -> list[str]:
    """Split a text into alternating prose and URL parts, brackets restored.

    Same alternation contract as ``_URL_RE.split`` (even index = prose, odd =
    URL match), with the trailing prose brackets of each URL match prepended
    to the prose part that always follows a match, so the parity of every
    part is preserved.
    """
    parts = _URL_RE.split(value)
    if len(parts) < 3:
        return parts
    out = [parts[0]]
    for index in range(1, len(parts), 2):
        url, brackets = _trim_trailing_brackets(parts[index])
        out.append(url)
        out.append(brackets + parts[index + 1])
    return out


def _scan_free_text(value: str) -> str:
    """Full pipeline for one free-form text: URLs, then fragments.

    URL-shaped substrings get the URL treatment (query values, userinfo
    password, credentials in path/fragment); the surrounding prose goes
    through the whole-value rule first and the token-by-token scan second,
    so a bare header value ("Authorization: Basic dXNlcg==") is caught by
    the former and a credential quoted inside a sentence by the latter.
    """
    parts = _split_url_text(value)
    out: list[str] = []
    for index, part in enumerate(parts):
        # The pattern has one group, so the odd indices are the URL matches.
        out.append(_mask_url(part) if index % 2 else _redact_fragment(part, scan_embedded=True))
    return "".join(out)


def _redact_template_text(text: str) -> str:
    """Redact the text of a template, leaving its placeholders untouched.

    The whole-value rule replaces a fragment it considers a credential with a
    fixed constant. Applied to a template that constant can swallow a
    ``%s``: the argument count and the placeholder count then disagree, the
    logging machinery raises on the substitution and the whole line is lost.
    Splitting the fragment at its format specs keeps the placeholders out of
    the rule's reach.
    """
    parts: list[str] = []
    position = 0
    for match in _FORMAT_SPEC_RE.finditer(text):
        parts.append(text[position : match.start()])
        parts.append(match.group(0))
        position = match.end()
    parts.append(text[position:])
    return "".join(
        part if index % 2 else _redact_fragment(part, scan_embedded=False)
        for index, part in enumerate(parts)
    )


def _split_log_text(value: str) -> list[str]:
    """Split a logged text into alternating plain and URL fragments."""
    return _split_url_text(value)


def redact_log_value(value: str | None) -> str:
    """Redact one runtime value on its way into a log line.

    - Outside URLs, the whole-value key heuristic applies, and a value that
      is several words long is additionally scanned token by token: an
      upstream provider error arrives as a sentence ("Incorrect API key
      provided: sk-..."), and a credential inside it must not survive;
    - Inside a URL, the query values and the userinfo password are masked and
      the URL keeps its shape. A request URL is where a vendor credential
      travels without looking like a key: APIs that authenticate through
      query parameters put the secret there (the Baidu OAuth token endpoint
      carries ``client_secret`` in the query) and the HTTP client logs the
      full request URL. The parameter names are kept so the request stays
      diagnosable.

    Used for log arguments and for rendered exception text.
    """
    if not value:
        return ""
    return _scan_free_text(value)


def redact_log_template(template: str) -> str:
    """Redact a log format template without touching its placeholders.

    A template is the ``"x=%s"`` pattern of a log call: the logging
    machinery substitutes ``record.args`` into it, so the count and order of
    the ``%s`` / ``%d`` placeholders must survive the redaction. The
    token-by-token scan is therefore not applied here — it would rewrite
    ordinary long words of the message text — and a ``%``-placeholder inside
    a URL keeps its shape.
    """
    if not template:
        return ""
    parts = _split_log_text(template)
    out: list[str] = []
    for index, part in enumerate(parts):
        # The pattern has one group, so the odd indices are the URL matches.
        out.append(
            _mask_url(part, preserve_specifiers=True) if index % 2 else _redact_template_text(part)
        )
    return "".join(out)


def redact_secrets_in_text(value: str | None) -> str:
    """Redact secrets embedded inside free-form text (exception messages).

    :func:`redact_api_key` treats its input as one candidate value, so a key
    buried inside a sentence ("request failed: key sk-... rejected") survives
    untouched. This scanner handles the full free-form pipeline: URL-shaped
    substrings get the URL treatment (query values, userinfo password,
    credentials in path/fragment), every other fragment goes through the
    whole-value rule first (a bare "Authorization: Basic ..." header is a
    whole value) and the token-by-token scan second (provider key prefixes,
    Bearer/Token/Basic schemes — a Basic payload is base64, masked including
    short values — and any standalone run of 20+ key characters), keeping
    the surrounding prose readable.
    The standalone-run rule is intentionally broader than the
    mixed-alphanumeric heuristic (no digit required), so ordinary long words
    are masked as well — accepted over-masking in exchange for not missing
    unusual secret shapes.
    """
    if not value:
        return ""
    if "-----BEGIN" in value.upper():
        return "***PEM_REDACTED***"
    return _scan_free_text(value)
