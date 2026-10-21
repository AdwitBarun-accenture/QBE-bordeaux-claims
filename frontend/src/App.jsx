import React, { useEffect, useState } from "react";
import { api, setToken } from "./api/client.js";
import Sidebar from "./components/Sidebar.jsx";
import Login from "./pages/Login.jsx";
import Inbox from "./pages/Inbox.jsx";
import Pipeline from "./pages/Pipeline.jsx";
import Insights from "./pages/Insights.jsx";
import Memory from "./pages/Memory.jsx";
import Settings from "./pages/Settings.jsx";
import Connections from "./pages/Connections.jsx";

export default function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState("inbox");
  const [openRunId, setOpenRunId] = useState(null);
  const [pending, setPending] = useState(0);

  useEffect(() => {
    api.get("/api/auth/me").then(setUser).catch(() => {});
    const out = () => setUser(null);
    window.addEventListener("bdx-logout", out);
    return () => window.removeEventListener("bdx-logout", out);
  }, []);

  useEffect(() => {
    if (user?.role === "underwriter") setView("insights");
  }, [user]);

  if (!user) return <Login onLogin={(u) => setUser(u)} />;

  const openFile = (runId) => { setOpenRunId(runId); setView("pipeline"); };
  const logout = () => { setToken(""); setUser(null); };

  return (
    <div className="shell">
      <Sidebar user={user} view={view} onNav={setView} pending={pending} onLogout={logout} hasRun={!!openRunId} />
      <main className="main">
        {view === "inbox" && <Inbox user={user} onOpen={openFile} onPending={setPending} />}
        {view === "pipeline" && <Pipeline runId={openRunId} user={user} onBack={() => setView("inbox")} />}
        {view === "insights" && <Insights />}
        {view === "memory" && <Memory />}
        {view === "settings" && <Settings />}
        {view === "connections" && <Connections />}
      </main>
    </div>
  );
}
