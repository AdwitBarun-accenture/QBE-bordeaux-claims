import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";
import { Badge, StatusBadge } from "../components/ui.jsx";
import { IngestStage, MappingStage, ValidationStage, CleanseStage, FreeTextStage, LoadStage } from "../components/stages.jsx";
import GateBar from "../components/GateBar.jsx";
import AgentFeed from "../components/AgentFeed.jsx";

const STAGES = [
  ["Ingest", "ingest", "Ingestion Agent"], ["Parse and map", "map", "Mapping Agent"], ["Validate", "validate", "Validation Agent"],
  ["Cleanse", "cleanse", "Cleansing Agent"], ["Free text", "freetext", "Classification Agent"], ["Load", "load", "Reporting Agent"],
];
const ORDER = ["ingest", "map", "validate", "cleanse", "freetext", "reconcile", "load"];
const GATE_STAGE = { 1: 1, 2: 2, 3: 5 };

export default function Pipeline({ runId, user, onBack }) {
  const [run, setRun] = useState(null);
  const [tab, setTab] = useState(null);
  const [err, setErr] = useState("");
  const [tick, setTick] = useState(0);
  const [lastGate, setLastGate] = useState(undefined);

  const load = useCallback(() => {
    if (!runId) return;
    api.get(`/api/runs/${runId}`).then((r) => {
      setRun(r);
      setTab((t) => (t == null ? (r.file.hitl_gate ? GATE_STAGE[r.file.hitl_gate] : 0) : t));
    }).catch((e) => setErr(e.message));
  }, [runId]);

  useEffect(() => { setTab(null); setLastGate(undefined); load(); }, [runId, load]);
  // when a new gate opens, take the analyst straight to the stage it concerns
  useEffect(() => {
    if (!run) return;
    const g = run.file.hitl_gate;
    if (lastGate !== undefined && g && g !== lastGate) setTab(GATE_STAGE[g]);
    if (run.file.status === "processed" && lastGate) setTab(5);
    setLastGate(g);
  }, [run?.file.hitl_gate, run?.file.status]); // eslint-disable-line
  useEffect(() => {
    if (!run || !["running", "received"].includes(run.file.status)) return;
    const t = setInterval(() => { load(); setTick((x) => x + 1); }, 2000);
    return () => clearInterval(t);
  }, [run, load]);

  const refresh = () => { load(); setTick((x) => x + 1); };
  if (!runId) return <div className="page"><div className="empty">Open a file from the inbox.</div></div>;
  if (!run) return <div className="page">{err ? <div className="error">{err}</div> : <div className="empty">Loading…</div>}</div>;

  const reached = ORDER.indexOf(run.stage);
  const f = run.file;
  const stageDone = (i) => (i === 5 ? f.status === "processed" : reached >= ORDER.indexOf(STAGES[i][1]));

  return (
    <div className="pipeline">
      <div className="page">
        <header className="page-head">
          <div>
            <button className="link" onClick={onBack}>Back to inbox</button>
            <h1>{f.coverholder}</h1>
            <p className="muted">{f.filename} · {f.file_type} · via {f.source} · correlation {run.correlation_id}</p>
          </div>
          <StatusBadge status={f.status} />
        </header>

        <GateBar run={run} user={user} onDone={refresh} onGo={(i) => setTab(i)} />

        <nav className="stages" aria-label="Pipeline stages">
          {STAGES.map(([label, , agent], i) => (
            <button key={label} className={`stage ${tab === i ? "active" : ""} ${stageDone(i) ? "done" : ""}`} onClick={() => setTab(i)}>
              <span className="stage-no">{i + 1}</span>
              <span><span className="stage-label">{label}</span><span className="stage-agent">{agent}</span></span>
            </button>
          ))}
        </nav>

        {f.status === "running" && <div className="notice">Agents are working on this file… this view refreshes automatically.</div>}
        {f.error && <div className="error">{f.error}</div>}

        <div className="stage-body">
          {tab === 0 && <IngestStage run={run} />}
          {tab === 1 && <MappingStage run={run} onChange={refresh} />}
          {tab === 2 && <ValidationStage run={run} onChange={refresh} />}
          {tab === 3 && <CleanseStage run={run} key={tick} />}
          {tab === 4 && <FreeTextStage run={run} />}
          {tab === 5 && <LoadStage run={run} key={tick} onChange={refresh} />}
        </div>
      </div>
      <AgentFeed runId={run.id} tick={tick} decisions={run.decisions} />
    </div>
  );
}
