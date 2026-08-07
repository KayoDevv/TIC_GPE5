import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { useTheme } from "~/composables/useTheme";

vi.stubGlobal("useState", <T>(_key: string, init: () => T) => ref(init()));
vi.stubGlobal("computed", computed);

describe("useTheme", () => {
  it("starts in light mode", () => {
    const { mode, themeClass } = useTheme();
    expect(mode.value).toBe("light");
    expect(themeClass.value).toBe("theme-light");
  });

  it("switches to dark on toggle", () => {
    const { mode, themeClass, toggle } = useTheme();
    toggle();
    expect(mode.value).toBe("dark");
    expect(themeClass.value).toBe("theme-dark");
  });

  it("returns to light on a second toggle", () => {
    const { mode, toggle } = useTheme();
    toggle();
    toggle();
    expect(mode.value).toBe("light");
  });
});