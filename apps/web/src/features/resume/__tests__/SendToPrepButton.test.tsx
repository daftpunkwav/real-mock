// @vitest-environment jsdom
/**
 * @file SendToPrepButton.test.tsx
 * @description The deep-review "send to prep" action must hand the prep coach
 * the templated question and the id of the resume the question belongs to.
 *
 * The button builds the link through the shared `lib/prepDeepLink` contract,
 * so the wiring it adds on top of that contract (the templated question and
 * the resume pairing) is what this pins.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SendToPrepButton } from "../components/SendToPrepButton";

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/i18n", () => ({
  useT: () => (key: string, values?: Record<string, unknown>) =>
    values && "question" in values ? `${key}:${values.question}` : key,
}));

afterEach(() => {
  cleanup();
  router.push.mockReset();
});

/** The search params of the link the button pushed. */
const pushedParams = (): URLSearchParams => {
  const [first] = router.push.mock.calls;
  const target = first?.[0] ?? "";
  expect(target.startsWith("/prep?")).toBe(true);
  return new URLSearchParams(target.slice(target.indexOf("?")));
};

describe("SendToPrepButton", () => {
  it("pushes the templated question with the owning resume id", () => {
    render(<SendToPrepButton question="介绍一下 Agent Loop" resumeId={7} />);

    fireEvent.click(screen.getByRole("button"));

    expect(router.push).toHaveBeenCalledTimes(1);
    const params = pushedParams();
    expect(params.get("resume")).toBe("7");
    expect(params.get("q")).toBe("sendToPrep.template:介绍一下 Agent Loop");
  });

  it("omits the resume id when the analysis is not paired with one", () => {
    render(<SendToPrepButton question="q" resumeId={null} />);

    fireEvent.click(screen.getByRole("button"));

    const params = pushedParams();
    expect(params.has("resume")).toBe(false);
    expect(params.get("q")).toBe("sendToPrep.template:q");
  });
});
