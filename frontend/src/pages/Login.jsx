import React, { useState } from "react";
import { api, setToken } from "../api/client.js";

export default function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const r = await api.post("/api/auth/login", { email, password });
      setToken(r.token);
      onLogin(r.user);
    } catch (ex) { setErr(ex.message); } finally { setBusy(false); }
  };

  return (
    <div className="login">
      <div className="login-card">
        <div className="brand-mark big">B</div>
        <h1>Sign in to Bordereaux</h1>
        <p className="muted">Coverholder bordereaux ingestion, validation and loading.</p>
        <form onSubmit={submit}>
          <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus required /></label>
          <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {err && <div className="error">{err}</div>}
          <button className="btn primary wide" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <div className="demo">
          <div className="muted small">Demo accounts (password: demo)</div>
          <button className="link" onClick={() => { setEmail("analyst@lloyds.com"); setPassword("demo"); }}>Analyst — full pipeline</button>
          <button className="link" onClick={() => { setEmail("underwriter@lloyds.com"); setPassword("demo"); }}>Underwriter — insights only</button>
        </div>
      </div>
    </div>
  );
}
