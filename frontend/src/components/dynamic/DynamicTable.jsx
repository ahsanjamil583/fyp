export function DynamicTable({ fields, rows }) {
  const visibleFields = fields.filter((field) => field.isActive && field.showInTable).sort((a, b) => a.order - b.order);

  if (!visibleFields.length) {
    return <div className="rounded-xl border border-dashed border-line bg-surface p-4 text-sm text-muted">No active table fields yet.</div>;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="min-w-[520px] divide-y divide-line text-sm">
        <thead className="bg-surface">
          <tr>
            {visibleFields.map((field) => (
              <th key={field.id} className="px-4 py-3 text-left font-semibold text-ink">
                {field.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line bg-white">
          {rows.map((row, index) => (
            <tr key={index}>
              {visibleFields.map((field) => (
                <td key={field.id} className="px-4 py-3 text-muted">
                  {formatValue(row[field.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}
