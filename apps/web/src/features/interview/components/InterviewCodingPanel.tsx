/**
 * @file InterviewCodingPanel
 * @description Live coding whiteboard and execution sandbox panel for technical interviews.
 *
 * Responsibilities:
 * - Render coding challenge details, constraints, and test suites.
 * - Provide a live code editor with language switching (Python / JavaScript / TypeScript).
 * - Execute code in browser sandbox and display stdout/stderr and test assertions.
 * - Enable candidate submission and review.
 */

"use client";

import React, { useState } from "react";
import { Play, Send, Code, Terminal, CheckCircle2, XCircle, FileText } from "lucide-react";
import { runPython } from "@/lib/code-runner/pythonRunner";
import { runJavascript } from "@/lib/code-runner/javascriptRunner";

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

export function InterviewCodingPanel() {
  const [problem] = useState<CodingProblem>(DEFAULT_CHALLENGE);
  const [code, setCode] = useState<string>(DEFAULT_CHALLENGE.starterCode);
  const [language, setLanguage] = useState<"python" | "javascript">("python");
  const [activeTab, setActiveTab] = useState<"editor" | "description">("editor");
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [consoleOutput, setConsoleOutput] = useState<string>("");
  const [runStatus, setRunStatus] = useState<"idle" | "success" | "error">("idle");
  const [submitted, setSubmitted] = useState<boolean>(false);

  const handleRunCode = async () => {
    setIsRunning(true);
    setRunStatus("idle");
    setConsoleOutput("Executing in local sandbox...\n");

    try {
      if (language === "python") {
        const res = await runPython(code);
        if (res.outcome === "ok") {
          setConsoleOutput(res.stdout || "Execution finished with no output.");
          setRunStatus("success");
        } else {
          setConsoleOutput(`[Error] ${res.message}\n${res.stderr}`);
          setRunStatus("error");
        }
      } else {
        const res = await runJavascript(code);
        if (res.outcome === "ok") {
          setConsoleOutput(res.stdout || "Execution finished with no output.");
          setRunStatus("success");
        } else {
          setConsoleOutput(`[Error] ${res.message}\n${res.stderr}`);
          setRunStatus("error");
        }
      }
    } catch (err: unknown) {
      setConsoleOutput(`Runtime error: ${String(err)}`);
      setRunStatus("error");
    } finally {
      setIsRunning(false);
    }
  };

  const handleSubmit = () => {
    setSubmitted(true);
    setConsoleOutput((prev) => `${prev}\n\n[System]: Solution submitted to Coding Examiner Agent.`);
  };

  return (
    <div className="flex flex-col h-full rounded-lg border border-surface-border bg-surface-card overflow-hidden">
      {/* Top bar: title + tab switch + language select */}
      <div className="flex items-center justify-between border-b border-surface-border bg-surface px-3 py-2 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-ink flex items-center gap-1">
            <Code size={14} className="text-[var(--primary)]" />
            {problem.title}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex rounded border border-surface-border p-0.5 bg-surface-alt">
            <button
              type="button"
              onClick={() => setActiveTab("editor")}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                activeTab === "editor" ? "bg-surface text-ink shadow-sm" : "text-ink-muted hover:text-ink"
              }`}
            >
              Editor
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("description")}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                activeTab === "description" ? "bg-surface text-ink shadow-sm" : "text-ink-muted hover:text-ink"
              }`}
            >
              Problem
            </button>
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

      {/* Main body: Description or Editor */}
      <div className="flex-1 min-h-0 flex flex-col p-2 gap-2 overflow-hidden">
        {activeTab === "description" ? (
          <div className="flex-1 overflow-y-auto p-3 rounded border border-surface-border bg-surface text-xs text-ink whitespace-pre-wrap leading-relaxed">
            <div className="flex items-center gap-1.5 mb-2 font-semibold text-ink">
              <FileText size={14} /> Problem Description
            </div>
            {problem.description}
          </div>
        ) : (
          <div className="flex-1 min-h-0 flex flex-col gap-2">
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              spellCheck={false}
              className="flex-1 w-full rounded border border-surface-border bg-[var(--surface-sunken,#18181b)] p-3 font-mono text-xs text-ink focus:outline-none resize-none leading-relaxed"
              placeholder="# Write your solution here..."
            />
          </div>
        )}

        {/* Console output section */}
        <div className="h-28 rounded border border-surface-border bg-surface-alt p-2 flex flex-col shrink-0 text-xs overflow-hidden">
          <div className="flex items-center justify-between border-b border-surface-border/50 pb-1 mb-1 text-[11px] text-ink-muted">
            <span className="flex items-center gap-1">
              <Terminal size={12} /> Sandbox Console
            </span>
            {runStatus === "success" && (
              <span className="text-[var(--success,#22c55e)] flex items-center gap-1 font-medium">
                <CheckCircle2 size={12} /> Pass
              </span>
            )}
            {runStatus === "error" && (
              <span className="text-[var(--danger,#ef4444)] flex items-center gap-1 font-medium">
                <XCircle size={12} /> Error
              </span>
            )}
          </div>
          <pre className="flex-1 overflow-y-auto font-mono text-[11px] text-ink-muted whitespace-pre-wrap">
            {consoleOutput || "Output will appear here after clicking 'Run Code'..."}
          </pre>
        </div>

        {/* Bottom controls */}
        <div className="flex items-center justify-between pt-1">
          <span className="text-[11px] text-ink-muted">
            {submitted ? "✓ Submitted for assessment" : "Local in-browser sandbox runner"}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRunCode}
              disabled={isRunning}
              className="inline-flex items-center gap-1 rounded bg-surface border border-surface-border px-3 py-1 text-xs font-medium text-ink hover:bg-surface-alt transition-colors disabled:opacity-50"
            >
              <Play size={12} className={isRunning ? "anim-spin" : "text-[var(--primary)]"} />
              {isRunning ? "Running..." : "Run Code"}
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitted || isRunning}
              className="inline-flex items-center gap-1 rounded bg-[var(--primary)] text-[var(--primary-foreground,#fff)] px-3 py-1 text-xs font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              <Send size={12} />
              {submitted ? "Submitted" : "Submit"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
