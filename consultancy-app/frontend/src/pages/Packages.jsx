import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.js";

export function formatPrice(amount, currency) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
}

export function usePackages() {
  const { onUnauthorized } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/api/packages")
      .then(setData)
      .catch((err) => (err.status === 401 ? onUnauthorized() : setError(err.message)));
  }, [onUnauthorized]);
  return { data, error };
}

/** The three package cards. When `result` is given, the recommended card is highlighted
 *  and each key point is shown on the card of the package it refers to. */
export function PackageGrid({ catalogue, result }) {
  const pointsFor = (id) => (result?.key_points || []).filter((kp) => kp.package_id === id);
  return (
    <div className="tiers">
      {catalogue.packages.map((p, i) => {
        const recommended = result?.recommended_package === p.id;
        const points = pointsFor(p.id);
        const added = (result?.tailored_items || []).filter((t) => t.package_id === p.id);
        const cls = ["card", "tier"];
        if (result ? recommended : i === 1) cls.push("featured");
        if (result && !recommended && points.length === 0 && added.length === 0) cls.push("dimmed");
        return (
          <article key={p.id} className={cls.join(" ")}>
            {result
              ? recommended && <span className="badge">Recommended for you</span>
              : i === 1 && <span className="badge">Most popular</span>}
            <h2>{p.name}</h2>
            <p className="price">
              {formatPrice(p.price_per_month, catalogue.currency)}
              <span className="muted"> / month</span>
            </p>
            <p className="muted">{p.tagline}</p>
            {points.length > 0 && (
              <div className="fit">
                <h3>Why it fits your needs</h3>
                <ul>
                  {points.map((kp, j) => (
                    <li key={j}>
                      <strong>{kp.title}</strong>
                      <p>{kp.detail}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <ul className="features">
              {added.map((t, j) => (
                <li key={`added-${j}`} className="added">
                  {t.item}
                  <span className="because">{t.because}</span>
                </li>
              ))}
              {p.features.map((f) => <li key={f}>{f}</li>)}
            </ul>
            <p className="small muted">Best for: {p.best_for}</p>
          </article>
        );
      })}
    </div>
  );
}

export default function Packages() {
  const { match, setMatch } = useAuth();
  const { data, error } = usePackages();
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted center">Loading packages…</p>;

  return (
    <section>
      <h1>AI consultancy assistance</h1>
      {match ? (
        <div className="card needs-summary">
          <p>
            <strong>Tailored to your needs.</strong>{" "}
            <span className="muted small">Bullets marked + were added from what you described. Your text isn't stored and is cleared on reload or logout.</span>
          </p>
          {match.result.source === "mock" && (
            <p className="small warn">Demo mode: no Claude API key configured, so this is a local keyword-based mock.</p>
          )}
          <p className="small">
            <Link to="/matcher">Edit needs</Link> · <button className="link small" onClick={() => setMatch(null)}>Clear</button>
          </p>
        </div>
      ) : (
        <p className="muted">Monthly packages. Not sure which fits? Describe your needs in the <Link to="/matcher">needs matcher</Link> and we'll tailor this page.</p>
      )}
      <PackageGrid catalogue={data} result={match?.result} />
    </section>
  );
}
