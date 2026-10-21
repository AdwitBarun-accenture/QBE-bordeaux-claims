import React, { useEffect, useState } from "react";
import { api } from "../api/client.js";

export default function AgentFeed({ runId, tick, decisions }) {
  const [feed, setFeed] = useState([]);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get(`/api/runs/${runId}/feed`).then(setFeed).catch(() => {}); }, [runId, tick, decisions?.length]);

  const ask = async () => {
    if (!q.trim()) return;
    setBusy(true);
    try { setAnswer((await api.post(`/api/runs/${runId}/ask`, { question: q })).answer); setQ(""); }
    catch (e) { setAnswer(e.message); } finally { setBusy(false); }
  };

  return (
    <aside className="feed">
      <h3>Agent activity</h3>
      <div className="feed-list">
        {feed.map((e, i) => (
          <div key={i} className={`feed-item lvl-${e.level}`}>
            <div className="feed-top"><span className="feed-agent">{e.agent}</span>
              <span className="feed-time">{new Date(e.at).toLocaleTimeString("en-GB")}</span></div>
            <div className="feed-action">{e.action}</div>
            {e.detail && <div className="feed-detail">{e.detail}</div>}
            {e.tokens > 0 && <div className="feed-meta">{e.model} · {e.tokens} tokens · {e.duration_ms} ms</div>}
          </div>
        ))}
        {!feed.length && <div className="empty">No activity yet.</div>}
      </div>
      <div className="ask">
        <h3>Ask about this file</h3>
        <textarea rows={2} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Which rows block the load?"
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }} />
        <button className="btn" onClick={ask} disabled={busy}>{busy ? "Thinking…" : "Ask"}</button>
        {answer && <div className="answer">{answer}</div>}
      </div>
    </aside>
  );
}
