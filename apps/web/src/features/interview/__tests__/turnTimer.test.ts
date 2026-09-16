import { describe, expect, it } from "vitest";

import { formatTurnCountdown } from "../turnTimer";

describe("formatTurnCountdown", () => {
  it("renders sub-minute remainders in seconds", () => {
    expect(formatTurnCountdown(7)).toBe("7s");
    expect(formatTurnCountdown(59)).toBe("59s");
  });

  it("renders minutes with zero-padded seconds", () => {
    expect(formatTurnCountdown(60)).toBe("1:00");
    expect(formatTurnCountdown(125)).toBe("2:05");
    expect(formatTurnCountdown(300)).toBe("5:00");
  });

  it("clamps negatives to zero", () => {
    expect(formatTurnCountdown(-3)).toBe("0s");
  });
});
