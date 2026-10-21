import React, { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { Badge, Panel } from "../components/ui.jsx";

export default function Connections() {
  const [c, setC] = useState(null);
  const [sftp, setSftp] = useState({ host: "", port: 22, username: "", password: "", watch_dir: "/inbound/bordereaux" });
  const [msg, setMsg] = useState("");
  useEffect(() => { api.get("/api/connections").then(setC); }, []);
  const test = async () => { setMsg("Testing…"); try { const r = await api.post("/api/connections/sftp/test", sftp); setMsg(`Connected. ${r.files_waiting} file(s) waiting.`); } catch (e) { setMsg(e.message); } };
  const poll = async () => { setMsg("Checking sources…"); try { setMsg("Pulled: " + JSON.stringify(await api.post("/api/connections/poll-now"))); } catch (e) { setMsg(e.message); } };
  if (!c) return <div className="page"><div className="empty">Loading…</div></div>;
  const St = ({ ok }) => <Badge tone={ok ? "ok" : "neutral"}>{ok ? "Configured" : "Not configured"}</Badge>;
  return (
    <div className="page">
      <header className="page-head"><div><h1>Connections</h1>
        <p className="muted">Where bordereaux come from and where clean data goes. Credentials are set as server settings (Key Vault on Azure), never in the browser.</p></div>
        <button className="btn primary" onClick={poll}>Check sources now</button></header>
      {msg && <div className="notice">{msg}</div>}
      <div className="grid2">
        <Panel title="Microsoft 365 shared mailbox" right={<St ok={c.email_m365.configured} />}>
          <p className="small">{c.email_m365.mailbox || "Set GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET and GRAPH_MAILBOX."}</p>
          <p className="muted small">Polled every {c.scheduler.poll_minutes} minutes when the scheduler is on ({c.scheduler.enabled ? "on" : "off"}).</p>
        </Panel>
        <Panel title="Gmail" right={<St ok={false} />}><p className="muted small">Not implemented. See connectors/email_graph.py for the extension point.</p></Panel>
      </div>
      <Panel title="SFTP server" right={<St ok={c.sftp.configured} />}>
        <p className="muted small">Test credentials here, then store them as SFTP_* settings.</p>
        <div className="row3">
          <label>Host<input value={sftp.host} onChange={(e) => setSftp({ ...sftp, host: e.target.value })} /></label>
          <label>Username<input value={sftp.username} onChange={(e) => setSftp({ ...sftp, username: e.target.value })} /></label>
          <label>Password<input type="password" value={sftp.password} onChange={(e) => setSftp({ ...sftp, password: e.target.value })} /></label>
        </div>
        <label>Watch directory<input value={sftp.watch_dir} onChange={(e) => setSftp({ ...sftp, watch_dir: e.target.value })} /></label>
        <button className="btn" onClick={test} disabled={!sftp.host}>Test connection</button>
      </Panel>
      <Panel title="Platform">
        <dl className="meta">
          <div><dt>Warehouse loader</dt><dd>{c.warehouse.loader}</dd></div>
          <div><dt>AI provider</dt><dd>{c.llm.provider} · {c.llm.model}</dd></div>
          <div><dt>File storage</dt><dd>{c.storage.backend}</dd></div>
          <div><dt>Job queue</dt><dd>{c.queue.backend}</dd></div>
        </dl>
      </Panel>
    </div>
  );
}
