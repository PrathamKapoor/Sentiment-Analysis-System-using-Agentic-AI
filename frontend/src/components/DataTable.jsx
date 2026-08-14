import EmptyState from "./EmptyState";

export default function DataTable({ columns, rows, rowKey = "id", emptyMessage = "No records found" }) {
  if (!rows || rows.length === 0) {
    return <EmptyState title={emptyMessage} />;
  }
  return (
    <div className="table-responsive">
      <table className="table table-hover align-middle">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key}>{col.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row[rowKey]}>
              {columns.map((col) => (
                <td key={col.key}>{col.render ? col.render(row) : row[col.key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
