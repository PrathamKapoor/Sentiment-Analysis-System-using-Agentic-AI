export default function EmptyState({ title = "Nothing here yet", description, action }) {
  return (
    <div className="text-center text-muted py-5">
      <p className="fs-5 mb-1">{title}</p>
      {description && <p className="mb-3">{description}</p>}
      {action}
    </div>
  );
}
