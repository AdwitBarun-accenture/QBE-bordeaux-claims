import React, { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { Modal, Panel, gbp } from "../components/ui.jsx";

function Toggle({ label, sub, checked, onChange }) {
  return (
    <label className="setting"><div><div className="strong">{label}</div><div className="muted small">{sub}</div></div>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /></label>
  );
}

const EMPTY = { name: "", class_of_business: "", da_limit_gbp: 0, date_order: "dmy", aliases: [], sender_emails: [] };

export default function Settings() {
  const [s, setS] = useState(null);
  const [chs, setChs] = useState([]);
  const [vault, setVault] = useState([]);
  const [edit, setEdit] = useState(null);
  const [saved, setSaved] = useState("");
  const load = () => { api.get("/api/settings").then(setS); api.get("/api/coverholders").then(setChs); api.get("/api/vault").then(setVault); };
  useEffect(load, []);
  const patch = async (p) => { setS(await api.put("/api/settings", p)); setSaved("Saved"); setTimeout(() => setSaved(""), 1500); };
  const saveCh = async () => {
    await api.post("/api/coverholders", { ...edit, da_limit_gbp: Number(edit.da_limit_gbp) || 0,
      aliases: String(edit.aliases).split(",").map((x) => x.trim()).filter(Boolean),
      sender_emails: String(edit.sender_emails).split(",").map((x) => x.trim()).filter(Boolean) });
    setEdit(null); load();
  };
  if (!s) return <div className="page"><div className="empty">Loading…</div></div>;
  return (
    <div className="page">
      <header className="page-head"><div><h1>Settings</h1><p className="muted">Thresholds, review gates and coverholder profiles. {saved}</p></div></header>
      <div className="grid2">
        <Panel title="AI confidence thresholds">
          <label className="setting"><div><div className="strong">Auto-approve mapping at</div><div className="muted small">Columns at or above this confidence need no review</div></div>
            <input type="number" min="50" max="100" value={s.auto_approve_threshold} onChange={(e) => patch({ auto_approve_threshold: Number(e.target.value) })} /></label>
          <label className="setting"><div><div className="strong">Review below</div><div className="muted small">Under this confidence a column is treated as unmapped</div></div>
            <input type="number" min="0" max="99" value={s.review_threshold} onChange={(e) => patch({ review_threshold: Number(e.target.value) })} /></label>
          <label className="setting"><div><div className="strong">Free-text fill at</div><div className="muted small">Extracted facts below this never fill a field</div></div>
            <input type="number" min="0" max="100" value={s.freetext_merge_threshold} onChange={(e) => patch({ freetext_merge_threshold: Number(e.target.value) })} /></label>
          <label className="setting"><div><div className="strong">Brokerage cap %</div><div className="muted small">Higher commission is flagged</div></div>
            <input type="number" value={s.brokerage_cap_percent} onChange={(e) => patch({ brokerage_cap_percent: Number(e.target.value) })} /></label>
        </Panel>
        <Panel title="Review gates">
          <Toggle label="Mapping sign-off" sub="Always ask, even when every column is confident" checked={s.gates.mapping} onChange={(v) => patch({ gates: { mapping: v } })} />
          <Toggle label="Exception review" sub="Always ask, even with no exceptions" checked={s.gates.exceptions} onChange={(v) => patch({ gates: { exceptions: v } })} />
          <Toggle label="Warehouse load sign-off" sub="Require approval before loading" checked={s.gates.load} onChange={(v) => patch({ gates: { load: v } })} />
          <p className="muted small">A gate always opens when something needs a person, whatever these switches say.</p>
        </Panel>
      </div>
      <Panel title="Processing options">
        {[["multi_sheet_detection", "Multi-sheet Excel detection", "Pick the bordereaux sheet automatically"],
          ["structural_change_detection", "Layout change detection", "Warn when columns differ from the last file"],
          ["dedup_check", "Prior submission check", "Flag UMRs already loaded"],
          ["ai_anomaly_detection", "AI anomaly detection", "Let the model look for issues rules can't see"],
          ["freetext_extraction", "Free-text extraction", "Read notes and descriptions"]].map(([k, l, sub]) => (
          <Toggle key={k} label={l} sub={sub} checked={s.processing[k]} onChange={(v) => patch({ processing: { [k]: v } })} />))}
      </Panel>
      <Panel title="Coverholder profiles" right={<button className="btn small" onClick={() => setEdit({ ...EMPTY })}>Add coverholder</button>}>
        <table className="data"><thead><tr><th>Coverholder</th><th>Class</th><th className="num">DA limit</th><th>Dates</th><th>Matches files named</th><th>Password</th><th /></tr></thead>
          <tbody>{chs.map((c) => (<tr key={c.id}><td className="strong">{c.name}</td><td>{c.class_of_business}</td><td className="num">{gbp(c.da_limit_gbp)}</td>
            <td>{c.date_order.toUpperCase()}</td><td className="small">{c.aliases.join(", ")}</td><td>{c.password_saved ? "Saved" : "–"}</td>
            <td><button className="link" onClick={() => setEdit({ ...c, aliases: c.aliases.join(", "), sender_emails: c.sender_emails.join(", ") })}>Edit</button></td></tr>))}</tbody></table>
      </Panel>
      <Panel title="Password vault">
        {vault.map((v) => (<div key={v} className="setting"><span>{v}</span>
          <button className="btn small danger" onClick={async () => { await api.del(`/api/vault/${encodeURIComponent(v)}`); load(); }}>Remove</button></div>))}
        {!vault.length && <div className="empty">No saved passwords. Tick "save to the vault" when unlocking a file.</div>}
      </Panel>
      <Modal open={!!edit} title={edit?.id ? "Edit coverholder" : "Add coverholder"} onClose={() => setEdit(null)}
        actions={<><button className="btn" onClick={() => setEdit(null)}>Cancel</button><button className="btn primary" onClick={saveCh} disabled={!edit?.name}>Save coverholder</button></>}>
        {edit && <>
          <label>Name<input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></label>
          <div className="row3">
            <label>Class<input value={edit.class_of_business} onChange={(e) => setEdit({ ...edit, class_of_business: e.target.value })} /></label>
            <label>DA limit (GBP)<input type="number" value={edit.da_limit_gbp} onChange={(e) => setEdit({ ...edit, da_limit_gbp: e.target.value })} /></label>
            <label>Date order<select value={edit.date_order} onChange={(e) => setEdit({ ...edit, date_order: e.target.value })}>
              <option value="dmy">DD/MM/YYYY</option><option value="mdy">MM/DD/YYYY</option></select></label>
          </div>
          <label>File name prefixes (comma separated)<input value={edit.aliases} onChange={(e) => setEdit({ ...edit, aliases: e.target.value })} /></label>
          <label>Sender email domains (comma separated)<input value={edit.sender_emails} onChange={(e) => setEdit({ ...edit, sender_emails: e.target.value })} /></label>
        </>}
      </Modal>
    </div>
  );
}
