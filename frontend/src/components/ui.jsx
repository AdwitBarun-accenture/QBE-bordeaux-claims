import React from "react";

export const STATUS = {
  received: ["Received", "neutral"], running: ["Agents running", "info"], "awaiting-password": ["Password needed", "warn"],
  "awaiting-mapping": ["Mapping sign-off", "info"], "awaiting-exceptions": ["Exceptions to review", "warn"],
  "awaiting-load": ["Ready to load", "info"], processed: ["Processed", "ok"], rejected: ["Rejected", "bad"],
  failed: ["Failed", "bad"], duplicate: ["Duplicate", "neutral"],
};

export function Badge({ tone = "neutral", children, title }) {
  return <span className={`badge ${tone}`} title={title}>{children}</span>;
}

export function StatusBadge({ status }) {
  const [label, tone] = STATUS[status] || [status, "neutral"];
  return <Badge tone={tone}>{label}</Badge>;
}

export function SevBadge({ sev }) {
  return <Badge tone={sev === "high" ? "bad" : sev === "medium" ? "warn" : "neutral"}>{sev}</Badge>;
}

export function Panel({ title, right, children, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      {(title || right) && <header className="panel-head"><h3>{title}</h3><div>{right}</div></header>}
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function Modal({ open, title, children, onClose, actions }) {
  if (!open) return null;
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <h3>{title}</h3>
        <div className="modal-body">{children}</div>
        <div className="modal-actions">{actions}</div>
      </div>
    </div>
  );
}

export function DataTable({ rows, columns, max = 50, highlight }) {
  if (!rows?.length) return <div className="empty">No rows.</div>;
  const cols = columns || Object.keys(rows[0]).filter((k) => !k.startsWith("_"));
  return (
    <div className="table-wrap">
      <table className="data">
        <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.slice(0, max).map((r, i) => (
            <tr key={i} className={highlight?.(r) || ""}>
              {cols.map((c) => <td key={c} title={String(r[c] ?? "")}>{fmtCell(r[c])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > max && <div className="table-more">Showing {max} of {rows.length} rows</div>}
    </div>
  );
}

function fmtCell(v) {
  if (v == null) return "";
  if (Array.isArray(v)) return v.join(", ");
  const s = String(v);
  return s.length > 42 ? s.slice(0, 41) + "…" : s;
}

export function Score({ label, value, note }) {
  const tone = value >= 90 ? "ok" : value >= 70 ? "warn" : "bad";
  return (
    <div className="score">
      <div className={`score-val ${tone}`}>{value ?? "–"}%</div>
      <div className="score-label">{label}</div>
      {note && <div className="score-note">{note}</div>}
    </div>
  );
}

export const gbp = (n) => (n == null ? "–" : "£" + Math.round(n).toLocaleString("en-GB"));
