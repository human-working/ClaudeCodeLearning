import { useCallback, useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api.js";
import { AuthContext, useAuth } from "./auth.js";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import Packages from "./pages/Packages.jsx";
import Matcher from "./pages/Matcher.jsx";



function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <p className="muted center">Loading…</p>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

function Header() {
  const { user, logout } = useAuth();
  return (
    <header className="topbar">
      <span className="brand">Northstar AI Consultancy</span>
      {user && (
        <nav>
          <NavLink to="/packages">Packages</NavLink>
          <NavLink to="/matcher">Needs matcher</NavLink>
          <span className="muted user">{user.username}</span>
          <button className="link" onClick={logout}>Log out</button>
        </nav>
      )}
    </header>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  // Latest needs-matcher run, shared by the Matcher and Packages pages.
  // Private by design: held in memory only (never localStorage/sessionStorage), so it
  // disappears on reload, logout or closing the tab. Clear any copy left by older builds.
  const [match, setMatch] = useState(null);
  useEffect(() => {
    try {
      sessionStorage.removeItem("lastMatch");
    } catch {
      /* storage unavailable */
    }
  }, []);

  useEffect(() => {
    api("/api/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  // Session expiry: tokens are short-lived, so drop the user when any call returns 401.
  const onUnauthorized = useCallback(() => {
    setUser(null);
    setMatch(null);
    navigate("/login", { replace: true });
  }, [navigate, setMatch]);

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      setUser(null);
      setMatch(null);
      navigate("/login", { replace: true });
    }
  }, [navigate, setMatch]);

  return (
    <AuthContext.Provider value={{ user, setUser, loading, logout, onUnauthorized, match, setMatch }}>
      <Header />
      <main>
        <Routes>
          <Route path="/login" element={user ? <Navigate to="/packages" replace /> : <Login />} />
          <Route path="/register" element={user ? <Navigate to="/packages" replace /> : <Register />} />
          <Route path="/packages" element={<RequireAuth><Packages /></RequireAuth>} />
          <Route path="/matcher" element={<RequireAuth><Matcher /></RequireAuth>} />
          <Route path="*" element={<Navigate to={user ? "/packages" : "/login"} replace />} />
        </Routes>
      </main>
    </AuthContext.Provider>
  );
}
