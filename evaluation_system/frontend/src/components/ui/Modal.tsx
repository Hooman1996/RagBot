import { X } from "@phosphor-icons/react";
import { useEffect, useId, useRef, type PropsWithChildren, type ReactNode } from "react";
import { Button } from "./Button";

export function Modal({ open, title, onClose, children, footer }: PropsWithChildren<{ open: boolean; title: string; onClose: () => void; footer?: ReactNode }>) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (open && !node.open) node.showModal();
    if (!open && node.open) node.close();
  }, [open]);
  return (
    <dialog ref={dialog} className="modal" aria-labelledby={titleId} onCancel={(event) => { event.preventDefault(); onClose(); }} onClose={onClose}>
      <div className="modal__header"><h2 id={titleId}>{title}</h2><Button variant="ghost" aria-label="بستن" onClick={onClose}><X size={20} /></Button></div>
      <div className="modal__body">{children}</div>
      {footer && <div className="modal__footer">{footer}</div>}
    </dialog>
  );
}
