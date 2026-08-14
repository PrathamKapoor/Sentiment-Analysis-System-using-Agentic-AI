export function formatDate(isoString) {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleDateString();
}
