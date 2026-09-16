/** Lightweight syntax highlighter for the coding whiteboard (zero-dependency).
 *
 * Emits escaped HTML with `tok-*` span classes; the color palette lives in
 * globals.css (`--ed-*` tokens, light + dark). Supported: Python 3 and
 * JavaScript — enough for interview whiteboard snippets, not a full grammar.
 */

export type CodeLanguage = "python" | "javascript";

interface TokenRule {
  cls: string;
  /** Sticky regex; matched only at the scan position. */
  re: RegExp;
}

const PY_RULES: TokenRule[] = [
  { cls: "tok-com", re: /#[^\n]*/y },
  { cls: "tok-str", re: /[rbufRBUF]{0,2}("""[\s\S]*?"""|'''[\s\S]*?''')/y },
  { cls: "tok-str", re: /[rbufRBUF]{0,2}"(?:\\.|[^"\\\n])*"/y },
  { cls: "tok-str", re: /[rbufRBUF]{0,2}'(?:\\.|[^'\\\n])*'/y },
  { cls: "tok-num", re: /\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?/y },
];

const JS_RULES: TokenRule[] = [
  { cls: "tok-com", re: /\/\/[^\n]*/y },
  { cls: "tok-com", re: /\/\*[\s\S]*?\*\//y },
  { cls: "tok-str", re: /`(?:\\.|[^`\\])*`/y },
  { cls: "tok-str", re: /"(?:\\.|[^"\\\n])*"/y },
  { cls: "tok-str", re: /'(?:\\.|[^'\\\n])*'/y },
  { cls: "tok-num", re: /\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?/y },
];

const PY_KEYWORDS = new Set(
  ("def class return if elif else for while in not and or import from as with try except " +
    "finally raise lambda pass break continue global nonlocal assert yield del is None True " +
    "False async await match case")
    .split(" "),
);

const PY_BUILTINS = new Set(
  ("print len range str int float list dict set tuple enumerate zip map filter super self " +
    "isinstance type open abs min max sum sorted any all repr hash id input round")
    .split(" "),
);

const JS_KEYWORDS = new Set(
  ("function const let var return if else for while in of new class extends import export " +
    "from async await try catch finally throw typeof instanceof this null true false undefined " +
    "break continue switch case default do delete void yield static get set")
    .split(" "),
);

const JS_BUILTINS = new Set(
  "console Math JSON Object Array String Number Boolean Promise Map Set Date RegExp Error".split(" "),
);

const IDENT_RE = /[A-Za-z_$][\w$]*/y;

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function span(cls: string, text: string): string {
  return `<span class="${cls}">${escapeHtml(text)}</span>`;
}

function tokenize(code: string, rules: TokenRule[], keywords: Set<string>, builtins: Set<string>): string {
  let out = "";
  let plain = "";
  let pos = 0;
  /** Previous identifier/keyword word — `def`/`class`/`function` color the name that follows. */
  let prevWord = "";

  const flushPlain = () => {
    if (plain) {
      out += escapeHtml(plain);
      plain = "";
    }
  };

  while (pos < code.length) {
    let matched = false;
    for (const rule of rules) {
      rule.re.lastIndex = pos;
      const m = rule.re.exec(code);
      if (m && m.index === pos && m[0].length > 0) {
        flushPlain();
        out += span(rule.cls, m[0]);
        pos += m[0].length;
        prevWord = "";
        matched = true;
        break;
      }
    }
    if (matched) continue;

    IDENT_RE.lastIndex = pos;
    const ident = IDENT_RE.exec(code);
    if (ident && ident.index === pos) {
      flushPlain();
      const word = ident[0];
      if (prevWord === "def" || prevWord === "class" || prevWord === "function") {
        out += span("tok-fn", word);
      } else if (keywords.has(word)) {
        out += span("tok-kw", word);
      } else if (builtins.has(word)) {
        out += span("tok-builtin", word);
      } else {
        out += escapeHtml(word);
      }
      pos += word.length;
      prevWord = word;
      continue;
    }

    // Numbers are covered by rules above; everything else batches as plain text.
    plain += code[pos];
    pos += 1;
  }
  flushPlain();
  return out;
}

/** Highlight `code` into token-classed HTML (already HTML-escaped). */
export function highlightCode(code: string, language: CodeLanguage): string {
  if (language === "python") {
    return tokenize(code, PY_RULES, PY_KEYWORDS, PY_BUILTINS);
  }
  return tokenize(code, JS_RULES, JS_KEYWORDS, JS_BUILTINS);
}
