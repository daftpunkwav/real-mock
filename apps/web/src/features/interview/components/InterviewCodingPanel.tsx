"use client";

/**
 * @file InterviewCodingPanel.tsx
 * @description Live coding whiteboard and execution sandbox panel for technical interviews.
 *
 * Responsibilities:
 * - Provide Problem / Editor / Sandbox Console as tabs over one shared region.
 * - Provide a syntax-highlighted code editor with language switching (Python / JavaScript).
 * - Execute code in browser sandbox and display stdout/stderr and test assertions.
 * - Enable candidate submission and review.
 *
 * UI chrome is fully localized via the interview catalog (`room.coding.*`);
 * the bundled demo challenge (title/description/starter code) is fixed English
 * sample content, like the code samples it embeds.
 */

import React, { useMemo, useRef, useState } from "react";
import { Play, Send, Code, Terminal, CheckCircle2, XCircle, FileText } from "lucide-react";
import { useT } from "@/i18n";
import { runPython } from "@/lib/code-runner/pythonRunner";
import { runJavascript } from "@/lib/code-runner/javascriptRunner";
import { highlightCode } from "../codeHighlight";

interface CodingTestCase {
  input: string;
  expected: string;
  description?: string;
}

interface CodingProblem {
  id: string;
  title: string;
  description: string;
  language: "python" | "javascript" | "typescript";
  starterCode: string;
  testCases: CodingTestCase[];
}

const DEFAULT_CHALLENGE: CodingProblem = {
  id: "reverse_linked_list",
  title: "Reverse a Singly Linked List",
  description: `Given the head of a singly linked list, reverse the list, and return the reversed list.

### Constraints:
- The number of nodes in the list is in the range \`[0, 5000]\`.
- \`-5000 <= Node.val <= 5000\`

### Example 1:
\`\`\`
Input: head = [1,2,3,4,5]
Output: [5,4,3,2,1]
\`\`\``,
  language: "python",
  starterCode: `class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

def reverse_list(head):
    prev = None
    curr = head
    while curr:
        nxt = curr.next
        curr.next = prev
        prev = curr
        curr = nxt
    return prev

# Test run
print("Reversed successfully!")
`,
  testCases: [
    { input: "[1,2,3,4,5]", expected: "[5,4,3,2,1]", description: "5 elements" },
    { input: "[1,2]", expected: "[2,1]", description: "2 elements" },
  ],
};

type PanelTab = "problem" | "editor" | "console";

type CodingMessageKey =
  | "room.coding.tabProblem"
  | "room.coding.tabEditor"
  | "room.coding.tabConsole";

const PANEL_TABS: ReadonlyArray<{ id: PanelTab; labelKey: CodingMessageKey }> = [
  { id: "problem", labelKey: "room.coding.tabProblem" },
  { id: "editor", labelKey: "room.coding.tabEditor" },
  { id: "console", labelKey: "room.coding.tabConsole" },
];

export function InterviewCodingPanel() {
  const t = useT("interview");
  const [problem] = useState<CodingProblem>(DEFAULT_CHALLENGE);
  const [code, setCode] = useState<string>(DEFAULT_CHALLENGE.starterCode);
  const [language, setLanguage] = useState<"python" | "javascript">("python");
  const [activeTab, setActiveTab] = useState<PanelTab>("editor");
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [consoleOutput, setConsoleOutput] = useState<string>("");
  const [runStatus, setRunStatus] = useState<"idle" | "success" | "error">("idle");
  const [submitted, setSubmitted] = useState<boolean>(false);
  const highlightRef = useRef<HTMLPreElement>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);

  // Highlight once per keystroke; the overlay pre mirrors the textarea exactly
  // (same font/padding, whitespace-pre, wrap off) so glyphs stay aligned.
  const highlighted = useMemo(() => highlightCode(code, language), [code, language]);

  const syncEditorScroll = () => {
    const pre = highlightRef.current;
    const ta = editorRef.current;
    if (pre && ta) {
      pre.scrollTop = ta.scrollTop;
      pre.scrollLeft = ta.scrollLeft;
    }
  };

  const handleRunCode = async () => {
    setIsRunning(true);
    setActiveTab("console");
    setRunStatus("idle");
    setConsoleOutput(`${t("room.coding.executing")}\n`);

    try {
      const runner = language === "python" ? runPython : runJavascript;
      const res = await runner(code).done;
      if (res.status === "ok") {
        setConsoleOutput(res.output || t("room.coding.noOutput"));
        setRunStatus("success");
      } else {
        setConsoleOutput(
          `${t("room.coding.execFailed")} ${res.error ?? ""}\n${res.stderr ?? ""}`,
        );
        setRunStatus("error");
      }
    } catch (err: unknown) {
      setConsoleOutput(t("room.coding.runtimeError", { msg: String(err) }));
      setRunStatus("error");
    } finally {
      setIsRunning(false);
    }
  };

  const handleSubmit = () => {
    setSubmitted(true);
    setActiveTab("console");
    setConsoleOutput((prev) => `${prev}\n\n${t("room.coding.submitNotice")}`);
  };

  return (
    <div className="flex flex-1 min-h-0 flex-col rounded-lg border border-surface-border bg-surface-card overflow-hidden">
      {/* Top bar: title + Problem/Editor/Sandbox Console tabs + language select, one row */}
      <div className="flex items-center justify-between gap-2 border-b border-surface-border bg-surface px-3 py-2 text-xs">
        <span className="font-semibold text-ink flex items-center gap-2 min-w-0">
          <Code size={14} className="text-[var(--primary)] shrink-0" />
          <span className="truncate">{problem.title}</span>
        </span>

        <div className="flex items-center gap-2 shrink-0">
          <div className="flex rounded border border-surface-border p-0.5 bg-surface-alt">
            {PANEL_TABS.map(({ id, labelKey }) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveTab(id)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                  activeTab === id ? "bg-surface text-ink shadow-sm" : "text-ink-muted hover:text-ink"
                }`}
              >
                {t(labelKey)}
              </button>
            ))}
          </div>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value as "python" | "javascript")}
            className="rounded border border-surface-border bg-surface px-2 py-0.5 text-[11px] text-ink focus:outline-none"
          >
            <option value="python">Python 3</option>
            <option value="javascript">JavaScript</option>
          </select>
        </div>
      </div>

      {/* Body: one shared region switched by the header tabs */}
      <div className="flex-1 min-h-0 flex flex-col p-2 overflow-hidden">
        {activeTab === "problem" && (
          <div className="flex-1 min-h-0 overflow-y-auto p-3 rounded border border-surface-border bg-surface text-xs text-ink whitespace-pre-wrap leading-relaxed">
            <div className="flex items-center gap-1.5 mb-2 font-semibold text-ink">
              <FileText size={14} /> {t("room.coding.problemHeading")}
            </div>
            {problem.description}
          </div>
        )}

        {activeTab === "editor" && (
          <div className="relative flex-1 min-h-0 rounded border border-surface-border overflow-hidden bg-[var(--ed-bg)]">
            <pre
              ref={highlightRef}
              aria-hidden
              className="absolute inset-0 overflow-hidden p-3 font-mono text-xs leading-relaxed text-[var(--ed-fg)] whitespace-pre pointer-events-none"
            >
              <code dangerouslySetInnerHTML={{ __html: highlighted }} />
            </pre>
            <textarea
              ref={editorRef}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              onScroll={syncEditorScroll}
              spellCheck={false}
              wrap="off"
              className="absolute inset-0 h-full w-full resize-none border-0 bg-transparent p-3 font-mono text-xs leading-relaxed text-transparent caret-[var(--ed-fg)] placeholder:text-ink-subtle focus:outline-none overflow-auto"
              placeholder={t("room.coding.editorPlaceholder")}
            />
          </div>
        )}

        {activeTab === "console" && (
          <div className="flex-1 min-h-0 rounded border border-surface-border bg-surface-alt p-2 flex flex-col text-xs overflow-hidden">
            <div className="flex items-center justify-between border-b border-surface-border/50 pb-1 mb-1 text-[11px] text-ink-muted shrink-0">
              <span className="flex items-center gap-1">
                <Terminal size={12} /> {t("room.coding.tabConsole")}
              </span>
              {runStatus === "success" && (
                <span className="text-[var(--success,#22c55e)] flex items-center gap-1 font-medium">
                  <CheckCircle2 size={12} /> {t("room.coding.status.pass")}
                </span>
              )}
              {runStatus === "error" && (
                <span className="text-[var(--danger,#ef4444)] flex items-center gap-1 font-medium">
                  <XCircle size={12} /> {t("room.coding.status.error")}
                </span>
              )}
            </div>
            <pre className="flex-1 overflow-y-auto font-mono text-[11px] text-ink-muted whitespace-pre-wrap m-0">
              {consoleOutput || t("room.coding.consolePlaceholder")}
            </pre>
          </div>
        )}
      </div>

      {/* Bottom controls */}
      <div className="flex items-center justify-between pt-1 shrink-0">
        <span className="text-[11px] text-ink-muted">
          {submitted ? t("room.coding.footerSubmitted") : t("room.coding.footerLocal")}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRunCode}
            disabled={isRunning}
            className="inline-flex items-center gap-1 rounded bg-surface border border-surface-border px-3 py-1 text-xs font-medium text-ink hover:bg-surface-alt transition-colors disabled:opacity-50"
          >
            <Play size={12} className={isRunning ? "anim-spin" : "text-[var(--primary)]"} />
            {isRunning ? t("room.coding.running") : t("room.coding.run")}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitted || isRunning}
            className="inline-flex items-center gap-1 rounded bg-[var(--primary)] text-[var(--primary-foreground,#fff)] px-3 py-1 text-xs font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            <Send size={12} />
            {submitted ? t("room.coding.submitted") : t("room.coding.submit")}
          </button>
        </div>
      </div>
    </div>
  );
}
