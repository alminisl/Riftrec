import { useState } from "react";
import { Link } from "react-router-dom";
import type { Legend } from "../types";

export function LegendList({ legends }: { legends: Legend[] }) {
  const [search, setSearch] = useState("");
  const total = legends.reduce((s, l) => s + l.deck_count, 0);

  const filtered = search
    ? legends.filter((l) =>
        l.name.toLowerCase().includes(search.toLowerCase())
      )
    : legends;

  return (
    <div className="legend-list">
      <div className="hero-stats">
        <div className="hero-stat accent-glow">
          <div className="hero-stat-value">{total.toLocaleString()}</div>
          <div className="hero-stat-label">Decklists Analyzed</div>
        </div>
        <div className="hero-stat">
          <div className="hero-stat-value">{legends.length}</div>
          <div className="hero-stat-label">Legends</div>
        </div>
        <div className="hero-stat">
          <div className="hero-stat-value">{legends[0]?.name.split(",")[0] || "—"}</div>
          <div className="hero-stat-label">Most Popular</div>
        </div>
      </div>

      <div className="search-container">
        <svg className="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          type="text"
          className="search-input"
          placeholder="Search legends..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="legend-grid">
        {filtered.map((legend, i) => (
          <Link
            key={legend.name}
            to={`/legend/${encodeURIComponent(legend.name)}`}
            className="legend-card"
            style={{ animationDelay: `${Math.min(i * 30, 500)}ms` }}
          >
            <span className="legend-card-rank">#{i + 1}</span>
            <img
              src={legend.image}
              alt={legend.name}
              className="legend-avatar"
              loading="lazy"
            />
            <div className="legend-info">
              <span className="legend-name">{legend.name}</span>
              <span className="deck-count">
                {legend.deck_count} deck{legend.deck_count !== 1 ? "s" : ""}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
