import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.js";
import { formatPrice, PackageGrid, usePackages } from "./Packages.jsx";

const MAX = 2000;

export default function Matcher() {
  const { onUnauthorized, match, setMatch } = useAuth();
  const { data: catalogue } = usePackages();
  const [needs, setNeeds] = useState(match?.needs || "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const result = match?.result;
  const rec = result && catalogue?.packages.find((p) => p.id === result.recommended_package);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api("/api/matcher/match", { method: "POST", body: { needs } });
      setMatch({ needs: needs.trim(), result: res }); // memory only
    } catch (err) {
      if (err.status === 401) onUnauthorized();
      else setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>Needs matcher</h1>
      <p className="muted">Describe your client's needs. We'll return 1 to 4 key points on which package fits and why, shown on the packages below.</p>
      <form className="card" onSubmit={submit}>
        <label htmlFor="needs">Client needs</label>
        <textarea id="needs" rows={7} maxLength={MAX} value={needs} onChange={(e) => setNeeds(e.target.value)}
          placeholder="e.g. 200-person insurer wants a claims-triage assistant, has strict GDPR requirements and no in-house ML team…" />
        <p className="small muted privacy">
          🔒 Private: email addresses, phone/account numbers, IBANs and links are removed before analysis.
          Nothing you type is saved, logged or kept in your browser after you leave or log out.
        </p>
        <div className="row">
          <span className="muted small">{needs.length} / {MAX}</span>
          <button disabled={busy || needs.trim().length < 10}>{busy ? "Analysing…" : "Match packages"}</button>
        </div>
      </form>

      {error && <p className="error" role="alert">{error}</p>}

      {result && catalogue && (
        <div aria-live="polite">
          <h2 className="result-heading">
            Recommended: {rec?.name || result.recommended_package}
            {rec && <span className="muted"> · {formatPrice(rec.price_per_month, catalogue.currency)} / month</span>}
          </h2>
          {result.source === "mock" && (
            <p className="small warn">Demo mode: no Claude API key configured, so this is a local keyword-based mock.</p>
          )}
          <p className="small muted">These results also appear on the <Link to="/packages">Packages</Link> page.</p>
          <PackageGrid catalogue={catalogue} result={result} />
        </div>
      )}
    </section>
  );
}
