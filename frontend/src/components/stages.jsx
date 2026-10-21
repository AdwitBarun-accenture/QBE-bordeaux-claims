import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api/client.js";
import { Badge, DataTable, Modal, Panel, Score, SevBadge, gbp } from "./ui.jsx";

function useDataset(runId, name, deps = []) {
  const [d, setD] = useState({ rows: [], total: 0, headers: [] });
  useEffect(() => { api.get(`/api/runs/${runId}/data/${name}?limit=500`).then(setD).catch(() => {}); }, [runId, name, ...deps]);
  return d;
}

/* ---------------- 01 Ingest ---------------- */
export function IngestStage({ run }) {
  const ing = run.ingestion || {};
  const parsed = useDataset(run.id, "parsed");
  const sc = run.structural_change || {};
  const prior = ing.memory?.prior_runs || [];
  const meta = [["Records", ing.records], ["Columns", ing.columns], ["Format", (ing.format || "").toUpperCase()],
    ["Sheet", ing.sheet || "–"], ["Classified as", ing.file_type ? `${ing.file_type} (${ing.file_type_confidence}%)` : "–"],
    ["Encoding", ing.encoding || "–"], ["SHA-256", (ing.sha256 || "").slice(0, 16) + "…"], ["Raw copy", ing.immutable_raw ? "Stored, write-once" : "–"]];
  return (
    <>
      <Panel title="What the Ingestion Agent captured">
        <dl className="meta">{meta.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v ?? "–"}</dd></div>)}</dl>
        {(ing.warnings || []).map((w) => <div key={w} className="notice small">{w}</div>)}
      </Panel>
      <Panel title="Memory recall for this coverholder">
        {prior.length ? prior.map((p) => (
          <div key={p.at} className="line">{p.at.slice(0, 10)} · {p.filename} · quality {p.quality}% · {p.exceptions} exceptions · {p.outcome}</div>
        )) : <div className="muted">First run for {run.file.coverholder}. Approved mappings will be remembered.</div>}
        <div className="muted small">{ing.memory?.recalled_mappings || 0} approved column mappings on file.</div>
        {sc.changed && <div className="notice warn">Layout changed since {sc.previous_file}: added {sc.added?.join(", ") || "none"}; removed {sc.removed?.join(", ") || "none"}{sc.order_changed ? "; column order changed" : ""}.</div>}
      </Panel>
      <Panel title="Raw file preview" right={<span className="muted small">{parsed.total} rows</span>}>
        <DataTable rows={parsed.rows} columns={parsed.headers} max={20} />
      </Panel>
    </>
  );
}

/* ---------------- 02 Mapping ---------------- */
export function MappingStage({ run, onChange }) {
  const [fields, setFields] = useState([]);
  const [ops, setOps] = useState({});
  const [editing, setEditing] = useState(null);
  const [filter, setFilter] = useState("");
  const [formula, setFormula] = useState(null);
  const [err, setErr] = useState("");
  const editable = run.file.hitl_gate === 1;
  useEffect(() => {
    api.get("/api/meta/lcrs-fields").then(setFields);
    api.get("/api/meta/formula-ops").then(setOps);
  }, []);
  const counts = useMemo(() => ({
    auto: run.mappings.filter((m) => m.status === "auto").length,
    review: run.mappings.filter((m) => m.status === "review").length,
    unmapped: run.mappings.filter((m) => m.status === "unmapped").length,
  }), [run.mappings]);

  const save = async (idx, body) => {
    try { await api.put(`/api/runs/${run.id}/mappings/${idx}`, body); setEditing(null); setFormula(null); setErr(""); onChange(); }
    catch (e) { setErr(e.message); }
  };
  const headers = run.ingestion?.headers || [];
  const missing = run.ingestion?.missing_mandatory || [];

  return (
    <>
      <Panel title="Column mappings to LCRS"
        right={<span className="muted small">{counts.auto} mapped · {counts.review} to review · {counts.unmapped} unmapped</span>}>
        {missing.length > 0 && <div className="notice warn">Mandatory fields with no source column: {missing.join(", ")}. Map a column or build a formula.</div>}
        {err && <div className="error">{err}</div>}
        <div className="map-grid map-head"><span>Source column</span><span>Sample values</span><span>LCRS field</span><span>Confidence</span><span>Basis</span></div>
        {run.mappings.map((m, i) => (
          <div key={m.source} className={`map-grid map-row st-${m.status}`}>
            <span className="strong">{m.source}</span>
            <span className="muted small">{(m.samples || []).join(" · ")}</span>
            <span>
              {editing === i ? (
                <div className="picker">
                  <input autoFocus placeholder="Search fields" value={filter} onChange={(e) => setFilter(e.target.value)} />
                  <div className="picker-list">
                    {fields.filter((f) => !f.derived && f.name.includes(filter.toLowerCase())).map((f) => (
                      <button key={f.name} className={f.name === m.canonical ? "on" : ""} onClick={() => save(i, { canonical: f.name })}>
                        {f.name}<span className="muted small"> {f.description}</span></button>
                    ))}
                  </div>
                  <div className="picker-foot">
                    <button className="link" onClick={() => save(i, { canonical: "unmapped" })}>Mark unmapped</button>
                    <button className="link" onClick={() => setFormula({ idx: i, colA: m.source, op: "pct_of", colB: "", target: "" })}>Build a formula</button>
                    <button className="link" onClick={() => setEditing(null)}>Close</button>
                  </div>
                </div>
              ) : (
                <button className="target" disabled={!editable} onClick={() => { setEditing(i); setFilter(""); }}>
                  {m.formula ? `= ${m.formula.colA} ${m.formula.op} ${m.formula.colB} → ${m.formula.target}` : m.canonical === "unmapped" ? "Unmapped" : m.canonical}
                </button>
              )}
            </span>
            <span><div className="conf"><div style={{ width: `${m.confidence || 0}%` }} /></div><span className="small">{m.confidence}%</span></span>
            <span className="small" title={m.notes}><Badge tone={m.origin === "memory" ? "ok" : m.origin === "human" || m.origin === "formula" ? "info" : "neutral"}>{m.origin}</Badge></span>
          </div>
        ))}
        {!editable && <div className="muted small">Mappings can be edited while Gate 1 is open.</div>}
      </Panel>

      <Modal open={!!formula} title="Formula mapping" onClose={() => setFormula(null)}
        actions={<><button className="btn" onClick={() => setFormula(null)}>Cancel</button>
          <button className="btn primary" disabled={!formula?.colB || !formula?.target}
            onClick={() => save(formula.idx, { formula: { colA: formula.colA, op: formula.op, colB: formula.colB, target: formula.target } })}>Apply formula</button></>}>
        {formula && <>
          <label>Target LCRS field<select value={formula.target} onChange={(e) => setFormula({ ...formula, target: e.target.value })}>
            <option value="">Choose…</option>{fields.map((f) => <option key={f.name}>{f.name}</option>)}</select></label>
          <div className="row3">
            <label>Column A<select value={formula.colA} onChange={(e) => setFormula({ ...formula, colA: e.target.value })}>{headers.map((h) => <option key={h}>{h}</option>)}</select></label>
            <label>Operation<select value={formula.op} onChange={(e) => setFormula({ ...formula, op: e.target.value })}>
              {Object.entries(ops).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <label>Column B<select value={formula.colB} onChange={(e) => setFormula({ ...formula, colB: e.target.value })}>
              <option value="">Choose…</option>{headers.map((h) => <option key={h}>{h}</option>)}</select></label>
          </div>
        </>}
      </Modal>
    </>
  );
}

/* ---------------- 03 Validation ---------------- */
export function ValidationStage({ run, onChange }) {
  const v = run.validation || {};
  const s = v.scores || {};
  const [err, setErr] = useState("");
  const canAct = [2, 3].includes(run.file.hitl_gate);
  const act = async (id, action) => {
    const note = action === "exclude" ? prompt("Reason for excluding these rows from the load?") || "" : "";
    try { await api.post(`/api/runs/${run.id}/exceptions/${id}`, { action, note }); onChange(); } catch (e) { setErr(e.message); }
  };
  if (!v.scores) return <div className="empty">Validation runs after mapping sign-off.</div>;
  return (
    <>
      <div className="scores">
        <Score label="Completeness" value={s.completeness} note="Mandatory cells populated" />
        <Score label="Accuracy" value={s.accuracy} note="Rows clean on value rules" />
        <Score label="Consistency" value={s.consistency} note="Rows clean on cross-field rules" />
        <Score label="Overall" value={s.overall} note="Weighted average" />
      </div>
      <Panel title={`Exceptions (${run.exceptions.length})`}>
        {err && <div className="error">{err}</div>}
        {run.exceptions.map((e) => (
          <div key={e.id} className={`exc ${e.status !== "open" ? "closed" : ""}`}>
            <div className="exc-head"><SevBadge sev={e.severity} /><span className="strong">{e.title}</span>
              {e.source === "ai" && <Badge tone="info">AI finding</Badge>}
              <span className="muted small">{e.count} row(s): {e.rows.slice(0, 12).join(", ")}</span>
              <span className="exc-status">{e.status}</span></div>
            <div className="small">{e.suggestion}</div>
            {canAct && (
              <div className="exc-actions">
                {e.status !== "accepted" && <button className="btn small" onClick={() => act(e.id, "accept")}>Accept, load flagged</button>}
                {e.status !== "excluded" && <button className="btn small" onClick={() => act(e.id, "exclude")}>Exclude rows from load</button>}
                {e.status !== "open" && <button className="link" onClick={() => act(e.id, "reopen")}>Reopen</button>}
              </div>
            )}
          </div>
        ))}
        {!run.exceptions.length && <div className="empty">No exceptions. Every rule passed.</div>}
      </Panel>
      {run.resolution_guidance && <Panel title="Resolution guidance"><pre className="prose">{run.resolution_guidance}</pre></Panel>}
      <Panel title={`Business rules run (${v.rules_run})`}>
        <table className="data">
          <thead><tr><th>Rule</th><th>Severity</th><th>Dimension</th><th>Result</th><th>Detail</th></tr></thead>
          <tbody>{(v.checks || []).map((c) => (
            <tr key={c.rule_id} className={c.skipped ? "muted" : ""}>
              <td>{c.rule}</td><td>{c.severity}</td><td>{c.dimension}</td>
              <td className={c.skipped ? "" : c.passed ? "ok-text" : c.severity === "error" ? "bad-text" : "warn-text"}>
                {c.skipped ? "Skipped" : c.passed ? "Pass" : `Fail (${c.count})`}</td>
              <td className="small">{c.detail}</td></tr>))}</tbody>
        </table>
      </Panel>
    </>
  );
}

/* ---------------- 04 Cleanse ---------------- */
export function CleanseStage({ run }) {
  const e = run.enrichment || {};
  const enriched = useDataset(run.id, "enriched");
  const lineage = useDataset(run.id, "lineage");
  if (!e.steps) return <div className="empty">Cleansing runs after mapping sign-off.</div>;
  return (
    <>
      <Panel title="Cleansing and enrichment steps" right={<span className="muted small">{e.changes} value changes · {e.fields} fields</span>}>
        <ol className="steps">{e.steps.map((s) => (
          <li key={s.step}><span className="strong">{s.step}</span><span className="muted small"> {s.description}</span>
            <span className="step-count">{s.changes}</span></li>))}</ol>
      </Panel>
      <Panel title="Enriched dataset"><DataTable rows={enriched.rows} max={30} /></Panel>
      <Panel title="Value lineage" right={<span className="muted small">{lineage.total} changes</span>}>
        <DataTable rows={lineage.rows} columns={["row", "field", "old", "new", "step"]} max={100} />
      </Panel>
    </>
  );
}

/* ---------------- 05 Free text ---------------- */
export function FreeTextStage({ run }) {
  const ft = run.freetext || {};
  if (!ft.results) return <div className="empty">Free-text extraction runs after mapping sign-off.</div>;
  if (!ft.results.length) return <div className="empty">No free-text content in this file.</div>;
  return (
    <Panel title="Facts extracted from notes" right={<span className="muted small">{ft.total} facts · {ft.merged} blank fields filled</span>}>
      <p className="muted small">Facts can fill blank fields. Adjustments, cross-references and flags are kept as annotations and never overwrite reported values.</p>
      {ft.results.map((r) => (
        <div key={r.row} className="ft">
          <div className="ft-text"><span className="strong">Row {r.row} · {r.insured}</span><div className="small muted">{r.text}</div></div>
          <div className="ft-tags">{r.extracted.map((x, i) => (
            <span key={i} className={`ft-tag kind-${x.kind}`} title={`"${x.source_phrase}" · ${x.method}`}>
              {x.field}: <b>{x.value}</b> <span className="small">{x.kind} · {x.confidence}%</span></span>))}</div>
        </div>
      ))}
    </Panel>
  );
}

/* ---------------- 06 Load ---------------- */
export function LoadStage({ run }) {
  const rec = run.reconciliation || {};
  const final = useDataset(run.id, "final");
  const lr = run.load_result || {};
  if (!rec.checks) return <div className="empty">Reconciliation runs after validation.</div>;
  const cards = [["Received", rec.received], ["To load", rec.to_load], ["Flagged", rec.flagged], ["Excluded", rec.excluded],
    ["Re-routed", rec.rerouted], [rec.gbp_measure === "total incurred" ? "Incurred GBP" : "Gross GBP", gbp(rec.gbp_total)]];
  return (
    <>
      <div className="cards">{cards.map(([l, v]) => <div key={l} className="card"><div className="card-val">{v}</div><div className="card-label">{l}</div></div>)}</div>
      <Panel title="Reconciliation">
        {rec.checks.map((c) => (
          <div key={c.check} className="recon"><span className={c.ok ? "ok-text" : "bad-text"}>{c.ok ? "Pass" : "Fail"}</span>
            <span className="strong">{c.check}</span><span className="muted small">{String(c.source)} → {String(c.target)}</span></div>))}
      </Panel>
      {lr.load_id && <Panel title="Warehouse load">
        <div className="line">{lr.rows_written} rows ({lr.rows_flagged} flagged) committed to {lr.target}. Load {lr.load_id.slice(0, 10)} ·
          read-back {lr.verified ? "verified" : "mismatch"}.</div></Panel>}
      <Panel title="Executive summary"><pre className="prose">{run.summary || "Generated after reconciliation."}</pre></Panel>
      <Panel title="Final LCRS dataset" right={<button className="btn small"
        onClick={() => api.download(`/api/runs/${run.id}/export.csv`, `LCRS_${run.file.filename.replace(/\.[^.]+$/, "")}.csv`)}>Download CSV</button>}>
        <DataTable rows={final.rows} max={30} highlight={(r) => (r._dq_flags?.length ? "flagged" : "")} />
      </Panel>
    </>
  );
}
