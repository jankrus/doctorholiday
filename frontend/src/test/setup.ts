import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';
import { toast } from '../components/toastStore';

// jsdom has no pointer capture; Radix Toast uses it for swipe-to-dismiss.
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.releasePointerCapture ??= () => {};

afterEach(() => {
  cleanup();
  // The queue is module state; a real reload starts with an empty one.
  toast.clear();
});
