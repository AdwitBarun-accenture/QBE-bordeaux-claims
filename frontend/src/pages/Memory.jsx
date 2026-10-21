import React, { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { Panel } from "../components/ui.jsx";

export default function Memory() {
  const [m, setM] = useState(null);
  const load = () => api.get("/api/memory").then(setM);
  useEffect(() => { load(); }, []);
  const forget = async (s) => { await api.post("/api/memory/semantic/forget", { coverholder: s.coverholder, file_type: s.file_type, source: s.source }); load(); };
  if (!m) return <div className="page"><div className="empty">Loading…</div></div>;
  return (
    <div className="page">
      <header className="page-head"><div><h1>Memory</h1>
        <p className="muted">How the agents learn: approved mappings are reused, past runs inform the next one, and every action is audited.</p></div></header>
      <Panel title={`Semantic memory: approved mappings (${m.semantic.length})`}>
        <p className="muted small">Recalled at 100% on the next file from the same coverholder, with no AI call.</p>
        <table className="data"><thead><tr><th>Coverholder</th><th>Type</th><th>Source column</th><th>LCRS field</th><th>Origin</th><th>Approved by</th><th className="num">Used</th><th /></tr></thead>
          <tbody>{m.semantic.map((s) => (<tr key={s.coverholder + s.file_type + s.source}><td>{s.coverholder}</td><td>{s.file_type}</td>
            <td className="strong">{s.source}</td><td>{s.canonical}</td><td>{s.origin}</td><td className="small">{s.approved_by}</td>
            <td className="num">{s.times_used}</td><td><button className="link" onClick={() => forget(s)}>Forget</button></td></tr>))}</tbody></table>
      </Panel>
      <Panel title={`Episodic memory: past runs (${m.episodic.length})`}>
        <table className="data"><thead><tr><th>When</th><th>Coverholder</th><th>File</th><th className="num">Quality</th><th className="num">Exceptions</th><th>Gates</th><th>Outcome</th></tr></thead>
          <tbody>{m.episodic.map((e, i) => (<tr key={i}><td className="small">{e.at.slice(0, 16).replace("T", " ")}</td><td>{e.coverholder}</td>
            <td className="small">{e.filename}</td><td className="num">{e.quality}%</td><td className="num">{e.exceptions}</td>
            <td className="small">{Object.entries(e.hitl).map(([g, d]) => `${g}: ${d}`).join(", ")}</td><td>{e.outcome}</td></tr>))}</tbody></table>
      </Panel>
      <Panel title="Operational memory: audit trail and AI usage">
        <table className="data"><thead><tr><th>Agent</th><th className="num">Input tokens</th><th className="num">Output tokens</th><th className="num">Events</th></tr></thead>
          <tbody>{Object.entries(m.token_usage).map(([a, t]) => (<tr key={a}><td>{a}</td><td className="num">{t.input_tokens.toLocaleString()}</td>
            <td className="num">{t.output_tokens.toLocaleString()}</td><td className="num">{t.events}</td></tr>))}</tbody></table>
        <h4>Latest events</h4>
        {m.operational.slice(0, 30).map((o, i) => (<div key={i} className="line small"><span className="muted">{o.at.slice(11, 19)}</span>{" "}
          <span className="strong">{o.agent}</span> {o.action} <span className="muted">{o.correlation_id}</span></div>))}
      </Panel>
    </div>
  );
}
