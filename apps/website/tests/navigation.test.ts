import { describe, expect, it } from "vitest";
import { FOOTER_LINKS, NAV_LINKS } from "~/utils/navigation";

describe("navigation links", () => {
  it("points every nav entry at an in-page anchor", () => {
    for (const link of NAV_LINKS) {
      expect(link.href).toMatch(/^#[a-z-]+$/);
    }
  });

  it("labels every nav entry", () => {
    for (const link of NAV_LINKS) {
      expect(link.label.length).toBeGreaterThan(0);
    }
  });

  it("keeps nav targets unique", () => {
    const targets = NAV_LINKS.map((link) => link.href);
    expect(new Set(targets).size).toBe(targets.length);
  });

  it("derives footer links from the nav without the states section", () => {
    expect(FOOTER_LINKS.length).toBe(NAV_LINKS.length - 1);
    expect(FOOTER_LINKS.some((link) => link.href === "#states")).toBe(false);
  });
});