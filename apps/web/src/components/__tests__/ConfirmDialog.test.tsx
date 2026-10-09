// @vitest-environment jsdom
/**
 * @file ConfirmDialog.test.tsx
 * @description The acknowledgement mode: confirm stays locked until the
 * checkbox is ticked, resets on reopen, and ordinary dialogs are unaffected.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";

import { LocaleProvider } from "@/i18n/LocaleProvider";
import { ConfirmDialog } from "../ConfirmDialog";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const renderDialog = (over: Partial<Parameters<typeof ConfirmDialog>[0]> = {}) => {
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
};

const confirmButton = () => screen.getByRole("button", { name: "Wipe it" }) as HTMLButtonElement;

describe("ConfirmDialog", () => {
  it.each(["close", "unmount", "remove trigger"])(
    "restores the opening focus target safely on %s",
    (action) => {
      const props = {
        title: "Wipe",
        message: "Everything goes",
        cancelLabel: "Cancel",
        onConfirm: vi.fn(),
        onCancel: vi.fn(),
      };
      const dialog = (open: boolean, busy = false) => (
        <StrictMode>
          <LocaleProvider>
            <ConfirmDialog {...props} open={open} busy={busy} onCancel={() => props.onCancel()} />
          </LocaleProvider>
        </StrictMode>
      );
      const { rerender, unmount } = render(dialog(false));
      const triggerView = render(<button type="button">Open wipe</button>);
      const trigger = triggerView.getByRole("button", {
        name: "Open wipe",
      });
      trigger.focus();
      const focus = vi.spyOn(trigger, "focus");

      rerender(dialog(true));
      expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel" }));
      // Busy and callback changes must not replace the original focus target.
      rerender(dialog(true, true));
      rerender(dialog(true));
      expect(focus).not.toHaveBeenCalled();

      if (action === "remove trigger") triggerView.container.remove();
      if (action === "unmount") unmount();
      else rerender(dialog(false));

      if (action === "remove trigger") {
        expect(focus).not.toHaveBeenCalled();
      } else {
        expect(document.activeElement).toBe(trigger);
        expect(focus).toHaveBeenCalledExactlyOnceWith({ preventScroll: true });
      }
    },
  );

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
