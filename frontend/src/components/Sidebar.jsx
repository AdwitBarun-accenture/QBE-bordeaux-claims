import React from "react";

const NAV = [
  { id: "inbox", label: "BDX inbox", roles: ["analyst", "underwriter", "admin"] },
  { id: "pipeline", label: "Pipeline", roles: ["analyst", "admin"], needsRun: true },
  { id: "insights", label: "Insights", roles: ["analyst", "underwriter", "admin"] },
  { id: "memory", label: "Memory", roles: ["analyst", "admin"] },
  { id: "settings", label: "Settings", roles: ["analyst", "admin"] },
  { id: "connections", label: "Connections", roles: ["analyst", "admin"] },
];

export default function Sidebar({ user, view, onNav, pending, onLogout, hasRun }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">B</div>
        <div>
          <div className="brand-name">Bordereaux</div>
          <div className="brand-sub">Intelligence platform</div>
        </div>
      </div>
      <nav>
        {NAV.filter((n) => n.roles.includes(user.role)).map((n) => (
          <button key={n.id} className={`nav-item ${view === n.id ? "active" : ""}`}
            disabled={n.needsRun && !hasRun} onClick={() => onNav(n.id)}>
            <span>{n.label}</span>
            {n.id === "inbox" && pending > 0 && <span className="nav-count">{pending}</span>}
          </button>
        ))}
      </nav>
      <div className="sidebar-foot">
        <div className="avatar">{user.initials}</div>
        <div className="who">
          <div className="who-name">{user.name}</div>
          <div className="who-role">{user.role === "analyst" ? "Bordereaux analyst" : "Underwriter"}</div>
        </div>
        <button className="link" onClick={onLogout}>Sign out</button>
      </div>
    </aside>
  );
}
