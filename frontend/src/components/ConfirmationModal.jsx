import { useEffect, useRef } from "react";

export default function ConfirmationModal({
  show, title = "Are you sure?", message, confirmLabel = "Confirm",
  onConfirm, onCancel, confirmDisabled = false, confirmBusy = false,
}) {
  const cancelRef = useRef(null);

  useEffect(() => {
    if (!show) return undefined;
    cancelRef.current?.focus();
    const onKeyDown = (event) => {
      if (event.key === "Escape" && !confirmBusy) onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [confirmBusy, onCancel, show]);

  if (!show) return null;
  return (
    <div className="modal d-block" role="dialog" aria-modal="true" aria-labelledby="confirmation-modal-title" aria-describedby="confirmation-modal-message" tabIndex={-1}>
      <div className="modal-dialog modal-dialog-centered">
        <div className="modal-content">
          <div className="modal-header">
            <h5 className="modal-title" id="confirmation-modal-title">{title}</h5>
            <button type="button" className="btn-close" onClick={onCancel} aria-label="Close" disabled={confirmBusy} />
          </div>
          <div className="modal-body">
            <p id="confirmation-modal-message" className="mb-0">{message}</p>
          </div>
          <div className="modal-footer">
            <button ref={cancelRef} className="btn btn-secondary" onClick={onCancel} disabled={confirmBusy}>Cancel</button>
            <button className="btn btn-danger" onClick={onConfirm} disabled={confirmDisabled || confirmBusy}>
              {confirmBusy ? "Deleting..." : confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
