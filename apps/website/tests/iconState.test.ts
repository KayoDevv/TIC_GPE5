import { describe, expect, it } from "vitest";
import { ICON_STATES } from "~/types/icon";
import { stateColor } from "~/utils/iconState";

describe("stateColor", () => {
  it("maps every state to a CSS variable", () => {
    for (const state of ICON_STATES) {
      expect(stateColor(state)).toMatch(/^var\(--[a-z-]+\)$/);
    }
  });

  it("gives each state its own colour", () => {
    const colors = ICON_STATES.map(stateColor);
    expect(new Set(colors).size).toBe(ICON_STATES.length);
  });

  it("maps threat to the danger token", () => {
    expect(stateColor("threat")).toBe("var(--danger)");
  });

  it("maps clear to the safe token", () => {
    expect(stateColor("clear")).toBe("var(--safe)");
  });
});