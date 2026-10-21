import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import { Badge, Modal, StatusBadge } from "../components/ui.jsx";

const FILTERS = [["all", "All"], ["review", "Needs review"], ["processed", "Processed"], ["failed", "Failed"],
  ["email", "Email"], ["sftp", "SFTP"], ["upload", "Uploaded"]];

export default function Inbox({ user, onOpen, onPending }) {
  const [data, setData] = useState({ files: [], total: 0 });
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [err, setErr] = useState("");
  const [dragging, setDragging] = useState(false);
  const [unlock, setUnlock] = useState(null);
  const [pw, setPw] = useState(""); const [remember, setRemember] = useState(true);
  const fileRef = useRef();

  const load = useCallback(() => {
    api.get(`/api/files?q=${encodeURIComponent(q)}&filter=${filter}`)
      .then((d) => { setData(d); onPending?.(d.pending_review); }).catch((e) => setErr(e.message));
  }, [q, filter, onPending]);

  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); }, [load]);

  const upload = async (file) => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try { await api.upload("/api/files/upload", form); setErr(""); load(); } catch (e) { setErr(e.message); }
  };

  const open = (f) => {
    if (f.status === "awaiting-password") { setUnlock(f); setPw(""); return; }
    if (f.latest_run_id) onOpen(f.latest_run_id);
  };

  const doUnlock = async () => {
    try { await api.post(`/api/files/${unlock.id}/unlock`, { password: pw, remember }); setUnlock(null); load(); }
    catch (e) { setErr(e.message); }
  };

  const analyst = user.role !== "underwriter";
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>BDX inbox</h1>
          <p className="muted">Every bordereaux received by email, SFTP or upload. Agents start on arrival; you review at the gates.</p>
        </div>
        {analyst && <button className="btn primary" onClick={() => fileRef.current.click()}>Upload file</button>}
        <input ref={fileRef} type="file" hidden accept=".csv,.xlsx,.xlsm,.xls,.zip" onChange={(e) => upload(e.target.files[0])} />
      </header>

      <div className="toolbar">
        <input className="search" placeholder="Search coverholder or file" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="tabs">
          {FILTERS.map(([id, label]) => (
            <button key={id} className={`tab ${filter === id ? "active" : ""}`} onClick={() => setFilter(id)}>{label}</button>
          ))}
        </div>
        <span className="muted small">{data.files.length} of {data.total} files</span>
      </div>
      {err && <div className="error">{err}</div>}

      <div className="table-wrap">
        <table className="data inbox">
          <thead><tr><th>Coverholder / file</th><th>Type</th><th>Source</th><th className="num">Records</th>
            <th className="num">Quality</th><th>Status</th><th>SLA</th></tr></thead>
          <tbody>
            {data.files.map((f) => (
              <tr key={f.id} className={`clickable ${f.hitl_gate ? "needs-review" : ""}`} onClick={() => open(f)}>
                <td><div className="strong">{f.coverholder}</div><div className="muted small">{f.filename}</div>
                  {f.error && <div className="small bad-text">{f.error}</div>}</td>
                <td>{f.status === "awaiting-password" ? <span className="muted">–</span> : <Badge>{f.file_type}</Badge>}</td>
                <td className="muted">{f.source}</td>
                <td className="num">{f.records || "–"}</td>
                <td className={`num ${f.quality >= 90 ? "ok-text" : f.quality >= 70 ? "warn-text" : f.quality ? "bad-text" : ""}`}>{f.quality ? `${f.quality}%` : "–"}</td>
                <td><StatusBadge status={f.status} /></td>
                <td className={f.sla_days < 0 ? "bad-text" : f.sla_days <= 3 ? "warn-text" : ""}>
                  {f.sla_days == null ? "–" : f.sla_days < 0 ? `Overdue ${-f.sla_days}d` : f.sla_days === 0 ? "Due today" : `Due in ${f.sla_days}d`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.files.length && <div className="empty">No files yet. Upload a bordereaux or connect a mailbox in Connections.</div>}
      </div>

      {analyst && (
        <div className={`dropzone ${dragging ? "over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); upload(e.dataTransfer.files[0]); }}
          onClick={() => fileRef.current.click()}>
          Drop a CSV, Excel or zip bordereaux here
        </div>
      )}

      <Modal open={!!unlock} title="Password-protected file" onClose={() => setUnlock(null)}
        actions={<><button className="btn" onClick={() => setUnlock(null)}>Cancel</button>
          <button className="btn primary" onClick={doUnlock} disabled={!pw}>Unlock and process</button></>}>
        <p>{unlock?.filename} from {unlock?.coverholder} is encrypted.</p>
        <label>Password<input type="password" value={pw} autoFocus onChange={(e) => setPw(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && pw && doUnlock()} /></label>
        <label className="check"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Save to the vault for this coverholder</label>
      </Modal>
    </div>
  );
}
