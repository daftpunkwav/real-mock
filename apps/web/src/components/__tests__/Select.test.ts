// @vitest-environment jsdom
/** Custom Select listbox: open / pick / dismiss behavior. */

import { createElement, useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Select } from "../Select";

// Vitest runs without globals, so testing-library auto-cleanup is off:
// unmount between cases to keep role queries isolated.
afterEach(() => cleanup());

const OPTIONS = [
  { value: 0, label: "Off" },
  { value: 60, label: "1 min" },
  { value: 180, label: "3 min" },
];

function setup(initial = 60, onChange = vi.fn()) {
  return {
    onChange,
    ...render(
      createElement(Select, {
        value: initial,
        options: OPTIONS,
        onChange,
        ariaLabel: "Wait",
      }),
    ),
  };
}

describe("Select", () => {
  it("renders the selected option label", () => {
    setup();
    expect(screen.getByRole("combobox").textContent).toContain("1 min");
  });

  it("opens on click and picks an option", () => {
    const onChange = vi.fn();
    setup(60, onChange);
    fireEvent.click(screen.getByRole("combobox"));
    expect(screen.getByRole("listbox")).toBeTruthy();
    fireEvent.click(screen.getByText("3 min"));
    expect(onChange).toHaveBeenCalledWith(180);
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("Escape dismisses without picking", () => {
    const onChange = vi.fn();
    setup(60, onChange);
    fireEvent.click(screen.getByRole("combobox"));
    expect(screen.getByRole("listbox")).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("stays closed when disabled", () => {
    render(
      createElement(Select, {
        value: 60,
        options: OPTIONS,
        onChange: () => {},
        ariaLabel: "Wait",
        disabled: true,
      }),
    );
    fireEvent.click(screen.getByRole("combobox"));
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("reflects a controlled value change", () => {
    function Controlled() {
      const [value, setValue] = useState(0);
      const handleChange = (v: number | string) => {
        if (typeof v === "number") setValue(v);
      };
      return createElement(Select, { value, options: OPTIONS, onChange: handleChange, ariaLabel: "Wait" });
    }
    render(createElement(Controlled));
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText("3 min"));
    expect(screen.getByRole("combobox").textContent).toContain("3 min");
  });
});
