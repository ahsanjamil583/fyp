export function DynamicForm({ fields, values, onChange, errors = [], columns = "auto" }) {
  const errorMap = new Map(errors.map((error) => [error.key, error.message]));
  const visibleFields = fields.filter((field) => field.isActive && field.showInForm).sort((a, b) => a.order - b.order);
  const gridClassName = columns === "single" ? "grid gap-4" : "grid gap-4 md:grid-cols-2";

  if (!visibleFields.length) {
    return <div className="rounded-xl border border-dashed border-line bg-surface p-4 text-sm text-muted">No active form fields yet.</div>;
  }

  function updateValue(key, value) {
    onChange({ ...values, [key]: value });
  }

  return (
    <div className={gridClassName}>
      {visibleFields.map((field) => (
        <label key={field.id} className="block">
          <span className="mb-1.5 block text-sm font-medium text-ink">
            {field.label}
            {field.required ? <span className="text-red-500"> *</span> : null}
          </span>
          <FieldInput field={field} value={values[field.key]} onChange={(value) => updateValue(field.key, value)} />
          {errorMap.has(field.key) ? <span className="mt-1 block text-xs text-red-600">{errorMap.get(field.key)}</span> : null}
        </label>
      ))}
    </div>
  );
}

function FieldInput({ field, value, onChange }) {
  if (field.type === "number") {
    return <input className="form-input" type="number" value={value ?? ""} onChange={(event) => onChange(event.target.value === "" ? "" : Number(event.target.value))} />;
  }

  if (field.type === "date") {
    return <input className="form-input" type="date" value={value ?? ""} onChange={(event) => onChange(event.target.value)} />;
  }

  if (field.type === "boolean") {
    return (
      <div className="flex h-[46px] items-center rounded-xl border border-line px-3">
        <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
        <span className="ml-2 text-sm text-muted">Enabled</span>
      </div>
    );
  }

  if (field.type === "select") {
    return (
      <select className="form-input" value={value ?? ""} onChange={(event) => onChange(event.target.value)}>
        <option value="">Select</option>
        {field.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }

  if (field.type === "multi_select") {
    return (
      <select
        className="form-input"
        multiple
        value={Array.isArray(value) ? value : []}
        onChange={(event) => onChange(Array.from(event.target.selectedOptions).map((option) => option.value))}
      >
        {field.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }

  if (field.type === "file" || field.type === "reference") {
    return <input className="form-input" value={value ?? ""} onChange={(event) => onChange(event.target.value)} placeholder={`${field.type} placeholder`} />;
  }

  return <input className="form-input" value={value ?? ""} onChange={(event) => onChange(event.target.value)} />;
}
