// Horizontal bars as a table, so the numbers stay readable and selectable.
type Row = { label: string; value: number; shown: string; accent?: boolean };

export function Bars({ rows, caption }: { rows: Row[]; caption: string }) {
  const max = Math.max(...rows.map((r) => r.value));
  return (
    <table className="bars">
      <caption className="muted">{caption}</caption>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label}>
            <th scope="row">{r.label}</th>
            <td>
              <span
                className={`bar${r.accent ? " accent" : ""}`}
                style={{ width: `${Math.max(0.4, (r.value / max) * 100)}%` }}
              />
            </td>
            <td className="num">{r.shown}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
