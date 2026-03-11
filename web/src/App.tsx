import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import type { AppData } from "./types";
import { LegendList } from "./pages/LegendList";
import { LegendDetail } from "./pages/LegendDetail";
import "./App.css";

export type CardImages = Record<string, string>;

export interface CardMeta {
  code: string;
  energy: string;
  domain: string;
  domainIcon: string;
  cardType: string;
  cardTypeIcon: string;
  rarity: string;
  rarityIcon: string;
  artist: string;
  set: string;
  ability: string;
  orientation: string;
}

export type CardMetaMap = Record<string, CardMeta>;

function App() {
  const [data, setData] = useState<AppData | null>(null);
  const [cardImages, setCardImages] = useState<CardImages>({});
  const [cardMeta, setCardMeta] = useState<CardMetaMap>({});

  useEffect(() => {
    fetch("/data.json")
      .then((r) => r.json())
      .then(setData);
    fetch("/cards.json")
      .then((r) => r.json())
      .then(setCardImages);
    fetch("/card-meta.json")
      .then((r) => r.json())
      .then(setCardMeta)
      .catch(() => {});
  }, []);

  if (!data) return <div className="loading">Loading...</div>;

  return (
    <BrowserRouter>
      <div className="app">
        <header className="app-header">
          <div className="app-header-inner">
            <a href="/">
              <svg className="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
              <h1>RiftRec</h1>
              <span className="subtitle">Riftbound Deck Aggregator</span>
            </a>
          </div>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<LegendList legends={data.legends} />} />
            <Route
              path="/legend/:name"
              element={
                <LegendDetail
                  legends={data.legends}
                  cardImages={cardImages}
                  cardMeta={cardMeta}
                />
              }
            />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
