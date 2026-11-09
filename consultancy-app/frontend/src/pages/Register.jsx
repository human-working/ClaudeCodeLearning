import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.js";

export default function Register() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", password: "", confirm: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (form.password !== form.confirm) {
      setError("Passwords do not match");
      return;
    }
    setBusy(true);
    try {
      const user = await api("/api/auth/register", {
        method: "POST",
        body: { username: form.username, password: form.password },
      });
      setUser(user);
      navigate("/packages", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card auth" onSubmit={submit} noValidate>
      <h1>Create account</h1>
      <label>
        Username
        <input autoComplete="username" required minLength={3} maxLength={32} value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })} />
      </label>
      <label>
        Password
        <input type="password" autoComplete="new-password" required minLength={12} maxLength={72} value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })} />
      </label>
      <label>
        Confirm password
        <input type="password" autoComplete="new-password" required maxLength={72} value={form.confirm}
          onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
      </label>
      <p className="muted small">
        At least 12 characters, with 3 of: lowercase, uppercase, digit, symbol. Must not contain your username.
      </p>
      {error && <p className="error" role="alert">{error}</p>}
      <button disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
      <p className="muted">Already registered? <Link to="/login">Sign in</Link></p>
    </form>
  );
}
