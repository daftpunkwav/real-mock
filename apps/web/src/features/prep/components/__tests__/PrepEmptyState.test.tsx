// @vitest-environment jsdom
/** PrepEmptyState: the start action fires without the DOM event tagging along. */

import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/LocaleProvider";
import type { ResumePickerItem } from "@/lib/api/contract";

import { PrepEmptyState } from "../PrepEmptyState";

afterEach(() => cleanup());

const resumes: ResumePickerItem[] = [
  { id: 7, filename: "resume.pdf", is_active: true } as ResumePickerItem,
];

function renderEmpty(onStart: () => void) {
  return render(
    <LocaleProvider>
      <PrepEmptyState
        resumeLoadError=""
        resumes={resumes}
        resumeId={7}
        onResumeChange={() => {}}
        prepError=""
        starting={false}
        onStart={onStart}
      />
    </LocaleProvider>,
  );
}

describe("PrepEmptyState", () => {
  it("invokes onStart without forwarding the click event", () => {
    // Regression: a passed-through MouseEvent used to land in the handler's
    // optional resume-id parameter and blow up JSON.stringify downstream
    // (circular React fiber reference surfaced as the create error).
    const onStart = vi.fn();
    renderEmpty(onStart);
    fireEvent.click(screen.getByRole("button"));
    expect(onStart).toHaveBeenCalledTimes(1);
    expect(onStart).toHaveBeenCalledWith();
  });
});
