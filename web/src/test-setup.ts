import { beforeEach, vi } from 'vitest';
beforeEach(() => {
  history.replaceState(null, '', '/');
  Object.defineProperty(window, 'scrollTo', { configurable: true, value: vi.fn() });
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
