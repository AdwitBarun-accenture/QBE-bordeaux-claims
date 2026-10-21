import React, { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { Badge, Panel, gbp } from "../components/ui.jsx";

function Bars({ data, label, value, fmt = (v) => v }) {
  const max = Math.max(1, ...data.map((d) => d[value]));
  return (
    <div className="bars">
      {data.map((d) => (
        <div key={d[label]} className="bar-row">
          <span className="bar-label">{d[label]}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width: `${(d[value] / max) * 100}%` }} /></span>
          <span className="bar-val">{fmt(d[value])}</span>
        </div>
      ))}
      {!data.length && <div className="empty">No loaded data yet.</div>}
    </div>
  );
}

export default function Insights() {
  const [d, setD] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/api/insights").then(setD); }, []);

  const ask = async (question) => {
    const text = question || q;
    if (!text.trim()) return;
    setMsgs((m) => [...m, { who: "You", text }]); setQ(""); setBusy(true);
    try { const r = await api.post("/api/insights/ask", { question: text }); setMsgs((m) => [...m, { who: "Insights Agent", text: r.answer }]); }
    catch (e) { setMsgs((m) => [...m, { who: "Insights Agent", text: e.message }]); } finally { setBusy(false); }
  };

  if (!d) return <div className="page"><div className="empty">Loading…</div></div>;
  const k = d.kpis;
  return (
    <div className="page">
      <header className="page-head"><div><h1>Portfolio insights</h1>
        <p className="muted">Computed from records loaded to the warehouse, coverholder profiles and processing history.</p></div></header>
      <div className="cards">
        <div className="card"><div className="card-val">{gbp(k.gwp_gbp)}</div><div className="card-label">Gross written premium</div></div>
        <div className="card"><div className="card-val">{k.files_loaded} / {k.files_received}</div><div className="card-label">Files loaded / received</div></div>
        <div className="card"><div className="card-val">{k.avg_quality}%</div><div className="card-label">Average quality</div></div>
        <div className="card"><div className="card-val">{k.open_exceptions}</div><div className="card-label">Open exceptions ({k.open_high} high)</div></div>
      </div>
      <div className="grid2">
        <Panel title="GWP by class of business"><Bars data={d.gwp_by_cob} label="cob" value="gbp" fmt={gbp} /></Panel>
        <Panel title="Files by inception month"><Bars data={d.files_by_month} label="month" value="files" /></Panel>
      </div>
      <Panel title="Delegated authority utilisation">
        <table className="data"><thead><tr><th>Coverholder</th><th>Class</th><th className="num">Limit</th><th className="num">Written</th><th className="num">Used</th><th>Status</th></tr></thead>
          <tbody>{d.da_utilisation.map((r) => (
            <tr key={r.coverholder}><td className="strong">{r.coverholder}</td><td>{r.class}</td><td className="num">{gbp(r.limit_gbp)}</td>
              <td className="num">{gbp(r.written_gbp)}</td><td className="num">{r.utilisation}%</td>
              <td><Badge tone={r.status === "approaching" ? "bad" : r.status === "watch" ? "warn" : "ok"}>{r.status}</Badge></td></tr>))}</tbody></table>
      </Panel>
      <div className="grid2">
        <Panel title="Claims by coverholder">
          <table className="data"><thead><tr><th>Coverholder</th><th className="num">Incurred</th><th className="num">Paid</th><th className="num">Outstanding</th></tr></thead>
            <tbody>{d.claims_by_coverholder.map((r) => (<tr key={r.coverholder}><td>{r.coverholder}</td><td className="num">{gbp(r.incurred)}</td>
              <td className="num">{gbp(r.paid)}</td><td className="num">{gbp(r.outstanding)}</td></tr>))}</tbody></table>
        </Panel>
        <Panel title="Recurring exception patterns">
          <table className="data"><thead><tr><th>Exception</th><th className="num">Count</th><th>Coverholders</th><th>Last seen</th></tr></thead>
            <tbody>{d.exception_patterns.map((r) => (<tr key={r.exception}><td>{r.exception}</td><td className="num">{r.count}</td>
              <td className="small">{r.coverholders.join(", ")}</td><td className="small">{r.last_seen}</td></tr>))}</tbody></table>
        </Panel>
      </div>
      <Panel title="Quality trend by coverholder">
        {d.quality_trend.map((t) => (<div key={t.coverholder} className="line"><span className="strong">{t.coverholder}</span>{" "}
          {t.points.map((p) => `${p.at}: ${p.quality}%`).join(" → ")}</div>))}
        {!d.quality_trend.length && <div className="empty">Trends appear after files are processed.</div>}
      </Panel>
      <Panel title="Ask the Insights Agent">
        <div className="chat">{msgs.map((m, i) => <div key={i} className={`chat-msg ${m.who === "You" ? "me" : ""}`}><b>{m.who}</b><div>{m.text}</div></div>)}</div>
        <div className="suggest">{["Which coverholders are near their DA limit?", "Total GWP for property?", "Which coverholder has the most exceptions?"].map((s) =>
          <button key={s} className="btn small" onClick={() => ask(s)}>{s}</button>)}</div>
        <div className="row"><input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()} placeholder="Ask about the portfolio" />
          <button className="btn primary" onClick={() => ask()} disabled={busy}>{busy ? "Thinking…" : "Ask"}</button></div>
      </Panel>
    </div>
  );
}
