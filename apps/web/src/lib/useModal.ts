import { useEffect } from "react";

/**
 * Modal niceties: close on Escape and lock body scroll while the modal is open.
 * Pass the close handler; call inside the modal component.
 */
export function useModal(onClose: () => void): void {
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);
}
