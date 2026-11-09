import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.js";

export default function Login() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const user = await api("/api/auth/login", { method: "POST", body: form });
      setUser(user);
      navigate(location.state?.from || "/packages", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card auth" onSubmit={submit} noValidate>
      <h1>Sign in</h1>
      <label>
        Username
        <input autoComplete="username" required maxLength={32} value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })} />
      </label>
      <label>
        Password
        <input type="password" autoComplete="current-password" required maxLength={128} value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })} />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      <p className="muted">No account? <Link to="/register">Create one</Link></p>
    </form>
  );
}
