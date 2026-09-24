import { afterEach, describe, expect, it, vi } from 'vitest';
import background from '../../entrypoints/background';
import {
  connectToolbarIcon,
  POPUP_PORT_NAME,
  resolveCharonState,
  toolbarIconPaths
} from '../../src/ui/charonState';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('resolveCharonState', () => {
  it('follows the analysis phase and the verdict tone', () => {
    expect(resolveCharonState('idle', null)).toBe('idle');
    expect(resolveCharonState('selected', null)).toBe('idle');
    expect(resolveCharonState('analyzing', null)).toBe('analyzing');
    expect(resolveCharonState('completed', 'blocked')).toBe('blocked');
    expect(resolveCharonState('completed', null)).toBe('idle');
    expect(resolveCharonState('failed', null)).toBe('idle');
  });
});

describe('toolbarIconPaths', () => {
  it('maps verdict states onto the shipped icon files', () => {
    expect(toolbarIconPaths('allowed')[16]).toBe('icons/eye/icon16-safe.png');
    expect(toolbarIconPaths('warning')[128]).toBe('icons/eye/icon128-warn.png');
    expect(toolbarIconPaths('blocked')[48]).toBe('icons/eye/icon48-danger.png');
    expect(Object.keys(toolbarIconPaths('idle'))).toEqual(['16', '32', '48', '128']);
  });
});

describe('connectToolbarIcon', () => {
  it('is a no-op outside of an extension context', () => {
    vi.stubGlobal('chrome', undefined);

    expect(() => connectToolbarIcon()('analyzing')).not.toThrow();
  });

  it('posts every state change on the popup port', () => {
    const postMessage = vi.fn();
    const connect = vi.fn(() => ({ postMessage }));
    vi.stubGlobal('chrome', { runtime: { connect } });

    connectToolbarIcon()('warning');

    expect(connect).toHaveBeenCalledWith({ name: POPUP_PORT_NAME });
    expect(postMessage).toHaveBeenCalledWith({ state: 'warning' });
  });
});

describe('background toolbar icon', () => {
  function startBackground() {
    const setIcon = vi.fn(async () => {});
    let onConnect: (port: unknown) => void = () => {};
    vi.stubGlobal('chrome', {
      action: { setIcon },
      runtime: { onConnect: { addListener: (listener: typeof onConnect) => (onConnect = listener) } }
    });
    background.main();
    return { setIcon, connect: (port: unknown) => onConnect(port) };
  }

  function buildPort(name: string) {
    const listeners: { message?: (message: unknown) => void; disconnect?: () => void } = {};
    return {
      listeners,
      port: {
        name,
        onMessage: { addListener: (listener: (message: unknown) => void) => (listeners.message = listener) },
        onDisconnect: { addListener: (listener: () => void) => (listeners.disconnect = listener) }
      }
    };
  }

  it('shows the popup state and falls back to idle when the popup closes', () => {
    const { setIcon, connect } = startBackground();
    const { port, listeners } = buildPort(POPUP_PORT_NAME);

    connect(port);
    listeners.message?.({ state: 'blocked' });
    listeners.disconnect?.();

    expect(setIcon).toHaveBeenNthCalledWith(1, { path: toolbarIconPaths('blocked') });
    expect(setIcon).toHaveBeenNthCalledWith(2, { path: toolbarIconPaths('idle') });
  });

  it('ignores ports opened by other extension pages', () => {
    const { connect } = startBackground();
    const { port, listeners } = buildPort('other');

    connect(port);

    expect(listeners.message).toBeUndefined();
  });
});
