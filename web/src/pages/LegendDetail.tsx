import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import type { Legend, CardStat } from "../types";
import type { CardImages, CardMetaMap } from "../App";
import { CardTooltip } from "../components/CardTooltip";
import { CardModal } from "../components/CardModal";

const SECTION_ORDER = ["Main Deck", "Battlefields", "Runes", "Sideboard"];

type ViewMode = "cards" | "list";

function getTierColor(rate: number): string {
  if (rate >= 0.8) return "#22c55e";
  if (rate >= 0.5) return "#3b9eff";
  if (rate >= 0.2) return "#f59e0b";
  return "#555570";
}

function getTier(rate: number): { label: string; className: string } {
  if (rate >= 0.8) return { label: "Staple", className: "tier-staple" };
  if (rate >= 0.5) return { label: "Common", className: "tier-common" };
  if (rate >= 0.2) return { label: "Uncommon", className: "tier-uncommon" };
  return { label: "Niche", className: "tier-niche" };
}

function CardTile({
  card,
  imgUrl,
  isLandscape,
  onClick,
}: {
  card: CardStat;
  imgUrl: string | undefined;
  isLandscape: boolean;
  onClick: () => void;
}) {
  const pct = (card.inclusion_rate * 100).toFixed(2);

  return (
    <div
      className={`card-tile ${isLandscape ? "card-tile-landscape" : ""}`}
      onClick={onClick}
    >
      <div className="card-tile-img-wrapper">
        {imgUrl ? (
          <img
            src={imgUrl}
            alt={card.name}
            className="card-tile-img"
            loading="lazy"
          />
        ) : (
          <div className="card-tile-placeholder">
            <span>{card.name}</span>
          </div>
        )}
      </div>
      <div className="card-tile-info">
        <span className="card-tile-name">{card.name}</span>
        <div className="card-tile-stats">
          <div className="card-tile-stat">
            <span className="card-tile-stat-label">Popularity</span>
            <span className="card-tile-stat-value">{pct}%</span>
          </div>
          <div className="card-tile-stat">
            <span className="card-tile-stat-label">Copies/Deck</span>
            <span className="card-tile-stat-value">{card.avg_copies.toFixed(2)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function RateBar({ rate }: { rate: number }) {
  const pct = Math.round(rate * 100);
  const { className } = getTier(rate);
  return (
    <div className="rate-bar-container">
      <div className="rate-bar-track">
        <div className={`rate-bar ${className}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="rate-label">{pct}%</span>
    </div>
  );
}

function CardRow({
  card,
  cardImages,
  onCardClick,
}: {
  card: CardStat;
  cardImages: CardImages;
  onCardClick: (name: string) => void;
}) {
  const { label, className } = getTier(card.inclusion_rate);
  return (
    <tr className={className}>
      <td className="card-name">
        <CardTooltip
          name={card.name}
          cardImages={cardImages}
          onCardClick={onCardClick}
        >
          {card.name}
        </CardTooltip>
      </td>
      <td className="card-rate">
        <RateBar rate={card.inclusion_rate} />
      </td>
      <td className="card-avg">{card.avg_copies.toFixed(1)}</td>
      <td className="card-decks">
        {card.deck_count}/{card.total_decks}
      </td>
      <td className="card-tier">
        <span className={`tier-badge ${className}`}>{label}</span>
      </td>
    </tr>
  );
}

function CardSectionCards({
  title,
  cards,
  cardImages,
  cardMeta,
  onCardClick,
}: {
  title: string;
  cards: CardStat[];
  cardImages: CardImages;
  cardMeta: CardMetaMap;
  onCardClick: (name: string) => void;
}) {
  if (!cards || cards.length === 0) return null;

  return (
    <div className="card-section">
      <div className="card-section-header">
        <h3>{title}</h3>
        <span className="card-section-count">{cards.length} cards</span>
      </div>
      <div className="card-grid">
        {cards.map((card) => (
          <CardTile
            key={card.name}
            card={card}
            imgUrl={cardImages[card.name]}
            isLandscape={cardMeta[card.name]?.orientation === "landscape"}
            onClick={() => onCardClick(card.name)}
          />
        ))}
      </div>
    </div>
  );
}

function CardSectionList({
  title,
  cards,
  cardImages,
  onCardClick,
}: {
  title: string;
  cards: CardStat[];
  cardImages: CardImages;
  onCardClick: (name: string) => void;
}) {
  if (!cards || cards.length === 0) return null;

  return (
    <div className="section-block">
      <h3>
        {title}
        <span className="section-count">{cards.length}</span>
      </h3>
      <table className="cards-table">
        <thead>
          <tr>
            <th>Card</th>
            <th>Inclusion Rate</th>
            <th>Avg Qty</th>
            <th>In Decks</th>
            <th>Tier</th>
          </tr>
        </thead>
        <tbody>
          {cards.map((card) => (
            <CardRow
              key={card.name}
              card={card}
              cardImages={cardImages}
              onCardClick={onCardClick}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function LegendDetail({
  legends,
  cardImages,
  cardMeta,
}: {
  legends: Legend[];
  cardImages: CardImages;
  cardMeta: CardMetaMap;
}) {
  const { name } = useParams<{ name: string }>();
  const [modalCard, setModalCard] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("cards");
  const legend = legends.find(
    (l) => l.name === decodeURIComponent(name || "")
  );

  if (!legend) {
    return (
      <div className="not-found">
        <p>Legend not found.</p>
        <Link to="/">Back to list</Link>
      </div>
    );
  }

  const totalCards = SECTION_ORDER.reduce(
    (sum, s) => sum + (legend.sections[s]?.length || 0),
    0
  );
  const staples =
    legend.sections["Main Deck"]?.filter((c) => c.inclusion_rate >= 0.8)
      .length || 0;

  return (
    <div className="legend-detail">
      <Link to="/" className="back-link">
        &larr; All Legends
      </Link>

      <div className="legend-hero">
        <img
          src={legend.image}
          alt={legend.name}
          className="legend-hero-img"
        />
        <div className="legend-hero-info">
          <h2>{legend.name}</h2>
          <div className="legend-hero-stats">
            <div className="legend-hero-stat">
              <span className="legend-hero-stat-value">
                {legend.deck_count}
              </span>
              <span className="legend-hero-stat-label">Decks</span>
            </div>
            <div className="legend-hero-stat">
              <span className="legend-hero-stat-value">{totalCards}</span>
              <span className="legend-hero-stat-label">Unique Cards</span>
            </div>
            <div className="legend-hero-stat">
              <span className="legend-hero-stat-value">{staples}</span>
              <span className="legend-hero-stat-label">Staples</span>
            </div>
          </div>
        </div>
      </div>

      <div className="view-toggle">
        <button
          className={`view-toggle-btn ${viewMode === "cards" ? "active" : ""}`}
          onClick={() => setViewMode("cards")}
          title="Card view"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="7" />
            <rect x="14" y="3" width="7" height="7" />
            <rect x="3" y="14" width="7" height="7" />
            <rect x="14" y="14" width="7" height="7" />
          </svg>
          Cards
        </button>
        <button
          className={`view-toggle-btn ${viewMode === "list" ? "active" : ""}`}
          onClick={() => setViewMode("list")}
          title="List view"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="8" y1="6" x2="21" y2="6" />
            <line x1="8" y1="12" x2="21" y2="12" />
            <line x1="8" y1="18" x2="21" y2="18" />
            <line x1="3" y1="6" x2="3.01" y2="6" />
            <line x1="3" y1="12" x2="3.01" y2="12" />
            <line x1="3" y1="18" x2="3.01" y2="18" />
          </svg>
          List
        </button>
      </div>

      {SECTION_ORDER.map((section) =>
        viewMode === "cards" ? (
          <CardSectionCards
            key={section}
            title={section}
            cards={legend.sections[section] || []}
            cardImages={cardImages}
            cardMeta={cardMeta}
            onCardClick={setModalCard}
          />
        ) : (
          <CardSectionList
            key={section}
            title={section}
            cards={legend.sections[section] || []}
            cardImages={cardImages}
            onCardClick={setModalCard}
          />
        )
      )}

      {modalCard && (
        <CardModal
          name={modalCard}
          cardImages={cardImages}
          cardMeta={cardMeta}
          onClose={() => setModalCard(null)}
        />
      )}
    </div>
  );
}
