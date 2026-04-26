import { useEffect, useState } from "react";

/**
 * Returns the input value debounced by `delay` ms.
 * Resets the timer on every change so only the last value (after a quiet period) is committed.
 */
export function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(handle);
  }, [value, delay]);
  return debounced;
}
