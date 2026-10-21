import React, { useState } from "react";
import { api } from "../api/client.js";
import { Modal } from "./ui.jsx";

const GATES = {
  1: ["Mapping sign-off", "Check the column mappings, correct anything wrong, then approve. Approved pairs are remembered for this coverholder.", 1],
  2: ["Exception review", "Accept or exclude each exception. Approving accepts the rest and moves claims rows found in a premium file out of the load.", 2],
  3: ["Warehouse load sign-off", "Reconciliation is complete. Approve to commit the dataset to the warehouse.", 5],
};

export default function GateBar({ run, user, onDone, onGo }) {
  const gate = run.file.hitl_gate;
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [email, setEmail] = useState("");
  if (!gate || user.role === "underwriter") {
    return run.file.status === "awaiting-password"
      ? <div className="gate warn">This file is password protected. Unlock it from the inbox.</div> : null;
  }
  const [title, text, stage] = GATES[gate];
  const reviewCount = gate === 1 ? run.mappings.filter((m) => m.status === "review").length : 0;

  const act = async (kind) => {
    setBusy(true); setErr("");
    try {
      const r = await api.post(`/api/runs/${run.id}/gates/${gate}/${kind}`, { comment });
      if (kind === "reject") setEmail(r.dua_email_draft || "");
      setComment(""); onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="gate">
      <div className="gate-text">
        <div className="gate-title">Gate {gate} · {title}</div>
        <div className="small">{text}{reviewCount ? ` ${reviewCount} column(s) still need review.` : ""}</div>
        {err && <div className="error small">{err}</div>}
      </div>
      <input className="gate-comment" placeholder={reviewCount ? "Comment (required to approve with columns in review)" : "Comment (optional)"}
        value={comment} onChange={(e) => setComment(e.target.value)} />
      <button className="btn" onClick={() => onGo(stage)}>Show me</button>
      <button className="btn danger" disabled={busy} onClick={() => act("reject")}>Reject</button>
      <button className="btn primary" disabled={busy} onClick={() => act("approve")}>{busy ? "Working…" : "Approve"}</button>
      <Modal open={!!email} title="Draft email to the coverholder" onClose={() => setEmail("")}
        actions={<><button className="btn" onClick={() => navigator.clipboard.writeText(email)}>Copy</button>
          <button className="btn primary" onClick={() => setEmail("")}>Done</button></>}>
        <p className="muted small">The file was rejected. Review this draft before sending it from your mail client.</p>
        <textarea className="email" value={email} onChange={(e) => setEmail(e.target.value)} rows={14} />
      </Modal>
    </div>
  );
}
