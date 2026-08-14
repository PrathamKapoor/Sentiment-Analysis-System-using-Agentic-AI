import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PermissionGuard from "./PermissionGuard";
import { formatDate } from "../utils/formatDate";

const ACTION_WIDTH = 112;
const DIRECTION_THRESHOLD = 10;
const INTERACTIVE_SELECTOR = "a, button, input, select, textarea, [role='menuitem']";

function Icon({ type }) {
  const paths = {
    open: <path d="M9 5H5v14h14v-4M13 5h6v6m0-6-9 9" />,
    data: <path d="M4 7c0 1.7 3.6 3 8 3s8-1.3 8-3-3.6-3-8-3-8 1.3-8 3Zm0 0v5c0 1.7 3.6 3 8 3s8-1.3 8-3V7m-16 5v5c0 1.7 3.6 3 8 3s8-1.3 8-3v-5" />,
    archive: <path d="M4 7h16M6 7v13h12V7M3 4h18v3H3V4Zm6 7h6" />,
    trash: <path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3" />,
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[type]}</g>
    </svg>
  );
}

export default function SwipeableProjectRow({
  project, isOpen, isRemoving, isArchiving, canDelete,
  onReveal, onClose, onDelete, onArchive,
}) {
  const navigate = useNavigate();
  const rootRef = useRef(null);
  const gesture = useRef(null);
  const suppressClick = useRef(false);
  const [offset, setOffset] = useState(isOpen ? -ACTION_WIDTH : 0);
  const [menuOpen, setMenuOpen] = useState(false);

  const projectPath = `/projects/${project.id}`;

  useEffect(() => {
    if (!gesture.current) setOffset(isOpen ? -ACTION_WIDTH : 0);
  }, [isOpen]);

  useEffect(() => {
    if (!menuOpen && !isOpen) return undefined;
    const handleOutside = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setMenuOpen(false);
        onClose();
      }
    };
    document.addEventListener("pointerdown", handleOutside);
    return () => document.removeEventListener("pointerdown", handleOutside);
  }, [isOpen, menuOpen, onClose]);

  const openProject = () => navigate(projectPath);

  const onPointerDown = (event) => {
    if (!canDelete || event.button !== 0 || event.target.closest(INTERACTIVE_SELECTOR)) return;
    gesture.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startOffset: offset,
      lastOffset: offset,
      direction: null,
      dragged: false,
    };
  };

  const onPointerMove = (event) => {
    const current = gesture.current;
    if (!current || current.pointerId !== event.pointerId) return;
    const dx = event.clientX - current.startX;
    const dy = event.clientY - current.startY;

    if (!current.direction && Math.max(Math.abs(dx), Math.abs(dy)) >= DIRECTION_THRESHOLD) {
      const horizontal = Math.abs(dx) > Math.abs(dy) * 1.15;
      const allowedDirection = dx < 0 || current.startOffset < 0;
      current.direction = horizontal && allowedDirection ? "horizontal" : "vertical";
      if (current.direction === "horizontal") {
        current.dragged = true;
        event.currentTarget.setPointerCapture?.(event.pointerId);
        onReveal();
      }
    }

    if (current.direction !== "horizontal") return;
    event.preventDefault();
    current.lastOffset = Math.min(0, Math.max(-ACTION_WIDTH, current.startOffset + dx));
    setOffset(current.lastOffset);
  };

  const finishGesture = (event, cancelled = false) => {
    const current = gesture.current;
    if (!current || current.pointerId !== event.pointerId) return;

    if (current.direction === "horizontal") {
      const shouldOpen = !cancelled && current.lastOffset < -ACTION_WIDTH * 0.42;
      setOffset(shouldOpen ? -ACTION_WIDTH : 0);
      if (shouldOpen) onReveal(); else onClose();
      suppressClick.current = true;
      window.setTimeout(() => { suppressClick.current = false; }, 0);
      if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    }
    gesture.current = null;
  };

  const onCardClick = (event) => {
    if (suppressClick.current || event.target.closest(INTERACTIVE_SELECTOR)) return;
    setOffset(0);
    onClose();
    openProject();
  };

  const onCardKeyDown = (event) => {
    if (event.currentTarget !== event.target || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    openProject();
  };

  const requestDelete = (event) => {
    event?.stopPropagation();
    setMenuOpen(false);
    setOffset(0);
    onClose();
    onDelete(project);
  };

  const requestArchive = (event) => {
    event.stopPropagation();
    setMenuOpen(false);
    onArchive(project);
  };

  const summary = project.productOrTopic || project.description || "Sentiment analysis workspace";

  return (
    <article ref={rootRef} role="listitem" className={`project-swipe-shell${isRemoving ? " is-removing" : ""}${menuOpen ? " has-menu" : ""}`}>
      {canDelete ? (
        <div className="project-delete-reveal" aria-hidden={!isOpen}>
          <button type="button" className="project-delete-button" onClick={requestDelete} tabIndex={isOpen ? 0 : -1}>
            <Icon type="trash" />
            <span>Delete</span>
          </button>
        </div>
      ) : null}

      <div
        className="project-swipe-card"
        role="link"
        tabIndex={0}
        aria-label={`Open ${project.name}`}
        style={{ transform: `translate3d(${offset}px, 0, 0)` }}
        onClick={onCardClick}
        onKeyDown={onCardKeyDown}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={(event) => finishGesture(event)}
        onPointerCancel={(event) => finishGesture(event, true)}
      >
        <div className="project-card-main">
          <div className="project-card-heading">
            <h3 className="project-card-title">{project.name}</h3>
            <span className={`project-status project-status-${project.status}`}>
              <span aria-hidden="true" />{project.status}
            </span>
          </div>
          <p className="project-card-summary">{summary}</p>
          {project.productOrTopic && project.description ? <p className="project-card-description">{project.description}</p> : null}
          <div className="project-card-metadata">
            <span><small>Created</small>{formatDate(project.createdAt)}</span>
            <span><small>Updated</small>{formatDate(project.updatedAt)}</span>
            {project.startDate || project.endDate ? <span><small>Analysis period</small>{formatDate(project.startDate)} – {formatDate(project.endDate)}</span> : null}
          </div>
        </div>

        <div className="project-context-actions" onClick={(event) => event.stopPropagation()}>
          <button type="button" className="project-action project-action-open" onClick={openProject}>
            <Icon type="open" /> Open
          </button>
          <Link className="project-action project-action-data" to={`${projectPath}/sources`}>
            <Icon type="data" /> Data Sources
          </Link>
          <button
            type="button"
            className="project-more-button"
            aria-label={`Open actions for ${project.name}`}
            aria-expanded={menuOpen}
            aria-haspopup="menu"
            onClick={() => setMenuOpen((current) => !current)}
          >•••</button>
        </div>

        {menuOpen ? (
          <div className="project-actions-menu" role="menu" onClick={(event) => event.stopPropagation()}>
            <button type="button" role="menuitem" onClick={openProject}><Icon type="open" /> Open workspace</button>
            <Link role="menuitem" to={`${projectPath}/sources`}><Icon type="data" /> Data Sources</Link>
            <PermissionGuard permission="edit_project">
              <button type="button" role="menuitem" className="archive-action" onClick={requestArchive} disabled={isArchiving}>
                <Icon type="archive" /> {isArchiving ? "Updating..." : project.status === "archived" ? "Unarchive" : "Archive"}
              </button>
            </PermissionGuard>
            <PermissionGuard permission="delete_project">
              <button type="button" role="menuitem" className="delete-action" onClick={requestDelete}><Icon type="trash" /> Delete project</button>
            </PermissionGuard>
          </div>
        ) : null}
      </div>
    </article>
  );
}
