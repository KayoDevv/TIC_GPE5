import type { IconState } from "~/types/icon";

const STATE_COLORS: Record<IconState, string> = {
  rest: "var(--icon-base)",
  scan: "var(--gold)",
  suspect: "var(--warn)",
  clear: "var(--safe)",
  threat: "var(--danger)",
};

export function stateColor(state: IconState): string {
  return STATE_COLORS[state];
}