import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, onMounted, onUnmounted, ref } from "vue";
import type { ComputedRef } from "vue";
import type { IconState } from "~/types/icon";
import { useIconCycle } from "~/composables/useIconCycle";

vi.stubGlobal("ref", ref);
vi.stubGlobal("computed", computed);
vi.stubGlobal("onMounted", onMounted);
vi.stubGlobal("onUnmounted", onUnmounted);

const INTERVAL = 2400;
const EXPECTED_SEQUENCE: IconState[] = [
  "rest",
  "scan",
  "suspect",
  "clear",
  "rest",
  "scan",
  "threat",
];

function mountCycle() {
  const captured = { state: null as ComputedRef<IconState> | null };
  const wrapper = mount(
    defineComponent({
      setup() {
        captured.state = useIconCycle(INTERVAL);
        return () => null;
      },
    }),
  );
  return { wrapper, state: captured.state as ComputedRef<IconState> };
}

describe("useIconCycle", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts at rest", () => {
    const { state, wrapper } = mountCycle();
    expect(state.value).toBe("rest");
    wrapper.unmount();
  });

  it("walks the full grammar of states in order", () => {
    const { state, wrapper } = mountCycle();
    for (const expected of EXPECTED_SEQUENCE) {
      expect(state.value).toBe(expected);
      vi.advanceTimersByTime(INTERVAL);
    }
    wrapper.unmount();
  });

  it("wraps back to the first state after the last one", () => {
    const { state, wrapper } = mountCycle();
    vi.advanceTimersByTime(INTERVAL * EXPECTED_SEQUENCE.length);
    expect(state.value).toBe("rest");
    wrapper.unmount();
  });

  it("holds each state for the whole interval", () => {
    const { state, wrapper } = mountCycle();
    vi.advanceTimersByTime(INTERVAL - 1);
    expect(state.value).toBe("rest");
    vi.advanceTimersByTime(1);
    expect(state.value).toBe("scan");
    wrapper.unmount();
  });

  it("clears its timer on unmount", () => {
    const clear = vi.spyOn(globalThis, "clearInterval");
    const { wrapper } = mountCycle();
    wrapper.unmount();
    expect(clear).toHaveBeenCalled();
    clear.mockRestore();
  });
});