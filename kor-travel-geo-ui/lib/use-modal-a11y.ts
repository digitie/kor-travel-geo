import { useEffect, type RefObject } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Shared modal a11y (T-227). Extracted from the T-258 backup ManifestViewer so every admin
 * dialog behaves the same for keyboard users: focus moves into the dialog on open, Tab is
 * trapped within it, Escape closes it, and focus returns to the triggering element on close.
 *
 * Most callers mount the dialog only while open (mount === open) and can omit `open` (it
 * defaults to true). Always-mounted overlays that toggle via CSS (e.g. the mobile nav drawer)
 * pass `open` so the focus move/trap/restore and the Escape handler engage only while shown.
 * Focus restore is best-effort: it is skipped when the previously-focused trigger has been
 * detached (e.g. a virtual-table row re-windowed while the modal was open) so focus is not
 * dumped to the document body.
 */
export function useModalA11y({
  dialogRef,
  onClose,
  initialFocusRef,
  open = true
}: {
  dialogRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  initialFocusRef?: RefObject<HTMLElement | null>;
  open?: boolean;
}): void {
  // Move focus into the modal on open; restore it to the trigger on close.
  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const target =
      initialFocusRef?.current ??
      dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE) ??
      dialogRef.current;
    target?.focus();
    return () => {
      if (previouslyFocused?.isConnected) previouslyFocused.focus();
    };
  }, [dialogRef, initialFocusRef, open]);

  // Escape closes; Tab is trapped within the dialog.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (!focusables || focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [dialogRef, onClose, open]);
}
