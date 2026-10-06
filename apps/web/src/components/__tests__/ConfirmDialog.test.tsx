// @vitest-environment jsdom
/**
 * @file ConfirmDialog.test.tsx
 * @description The acknowledgement mode: confirm stays locked until the
 * checkbox is ticked, resets on reopen, and ordinary dialogs are unaffected.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/LocaleProvider";
import { ConfirmDialog } from "../ConfirmDialog";

afterEach(cleanup);

function renderDialog(over: Partial<Parameters<typeof ConfirmDialog>[0]> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const props: Parameters<typeof ConfirmDialog>[0] = {
    open: true,
    title: "Wipe",
    message: "Everything goes",
    confirmLabel: "Wipe it",
    onConfirm,
    onCancel,
    ...over,
  };
  render(
    <LocaleProvider>
      <ConfirmDialog {...props} />
    </LocaleProvider>,
  );
  return { onConfirm, onCancel };
}

function confirmButton() {
  return screen.getByRole("button", { name: "Wipe it" }) as HTMLButtonElement;
}

describe("ConfirmDialog", () => {
  it("confirms immediately without the acknowledgement mode", () => {
    const { onConfirm } = renderDialog();
    expect(confirmButton().disabled).toBe(false);
    fireEvent.click(confirmButton());
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("locks confirm until the acknowledgement checkbox is ticked", () => {
    const { onConfirm } = renderDialog({
      requireAcknowledgement: true,
      acknowledgementLabel: "I understand",
    });
    expect(confirmButton().disabled).toBe(true);
    fireEvent.click(confirmButton());
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("I understand"));
    expect(confirmButton().disabled).toBe(false);
    fireEvent.click(confirmButton());
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("resets the checkbox when the dialog reopens", () => {
    const base = {
      title: "Wipe",
      message: "m",
      confirmLabel: "Wipe it",
      requireAcknowledgement: true,
      acknowledgementLabel: "I understand",
      onConfirm: vi.fn(),
      onCancel: vi.fn(),
    };
    const { rerender } = render(
      <LocaleProvider>
        <ConfirmDialog open {...base} />
      </LocaleProvider>,
    );
    fireEvent.click(screen.getByLabelText("I understand"));
    rerender(
      <LocaleProvider>
        <ConfirmDialog open={false} {...base} />
      </LocaleProvider>,
    );
    rerender(
      <LocaleProvider>
        <ConfirmDialog open {...base} />
      </LocaleProvider>,
    );
    expect((confirmButton() as HTMLButtonElement).disabled).toBe(true);
  });
});
