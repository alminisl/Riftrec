import { useEffect } from "react";
import type { CardImages, CardMeta } from "../App";

// Icon URLs from Riot CDN for :rb_*: token replacement
const RB_ICON_MAP: Record<string, string> = {
  ":rb_rune_chaos:": "https://cmsassets.rgpub.io/sanity/images/dsfx7636/game_data_live/597ddb82be59e87b467c52bb10204f02c2005d06-64x64.png?accountingTag=RB",
  ":rb_rune_order:": "https://cmsassets.rgpub.io/sanity/images/dsfx7636/game_data_live/8bb1b193a8e1adc26ca28e1a21da8d1e2f5d2f72-64x64.png?accountingTag=RB",
  ":rb_rune_calm:": "https://cmsassets.rgpub.io/sanity/images/dsfx7636/game_data_live/b9ef2f5b74841ad11f3629aa381a76ac0187d007-64x64.png?accountingTag=RB",
  ":rb_rune_fury:": "https://cmsassets.rgpub.io/sanity/images/dsfx7636/game_data_live/5aeb4bfd203b5d265902f65aa5afae7da1682eaa-64x64.png?accountingTag=RB",
  ":rb_rune_mind:": "https://cmsassets.rgpub.io/sanity/images/dsfx7636/game_data_live/17ab95a6bd052085b6803d846a287f625f347288-64x64.png?accountingTag=RB",
  ":rb_rune_body:": "https://cmsassets.rgpub.io/sanity/images/dsfx7636/game_data_live/7a5533034de5870808347bc4b296f0029bdd8eea-64x64.png?accountingTag=RB",
};

function replaceRbTokens(html: string): string {
  // Replace :rb_rune_*: with domain icons
  for (const [token, url] of Object.entries(RB_ICON_MAP)) {
    html = html.replaceAll(token, `<img src="${url}" alt="${token}" class="rb-icon" />`);
  }
  // Replace :rb_rune_rainbow: with all rune icons combined
  html = html.replaceAll(
    ":rb_rune_rainbow:",
    `<span class="rb-rainbow">${Object.entries(RB_ICON_MAP).map(([t, u]) => `<img src="${u}" alt="${t}" class="rb-icon" />`).join("")}</span>`
  );
  // Replace :rb_energy_N: with styled energy badges
  html = html.replace(/:rb_energy_(\d+):/g, '<span class="rb-energy">$1</span>');
  // Replace :rb_might: with a styled badge
  html = html.replaceAll(":rb_might:", '<span class="rb-keyword">Might</span>');
  // Replace :rb_exhaust: with a styled badge
  html = html.replaceAll(":rb_exhaust:", '<span class="rb-keyword">Exhaust</span>');
  return html;
}

interface Props {
  name: string;
  cardImages: CardImages;
  cardMeta?: Record<string, CardMeta>;
  onClose: () => void;
}

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="card-modal-meta-row">
      <div className="card-modal-meta-label">{label}</div>
      <div className="card-modal-meta-value">{children}</div>
    </div>
  );
}

function IconValue({ icon, label }: { icon?: string; label: string }) {
  return (
    <span className="card-modal-icon-value">
      {icon && <img src={icon} alt="" className="card-modal-meta-icon" />}
      <span>{label}</span>
    </span>
  );
}

export function CardModal({ name, cardImages, cardMeta, onClose }: Props) {
  const imgUrl = cardImages[name];
  const meta = cardMeta?.[name];

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div className="card-modal-overlay" onClick={onClose}>
      <div className="card-modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="card-modal-header">
          <div>
            <h2 className="card-modal-title">{name}</h2>
            {meta?.code && (
              <span className="card-modal-code">{meta.code}</span>
            )}
          </div>
          <button className="card-modal-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="card-modal-body">
          <div className="card-modal-image-col">
            {imgUrl ? (
              <img src={imgUrl} alt={name} className="card-modal-card-img" />
            ) : (
              <div className="card-modal-placeholder">{name}</div>
            )}
          </div>

          {meta && (
            <div className="card-modal-details">
              {meta.energy && (
                <MetaRow label="Energy">
                  <span className="card-modal-energy-pip">{meta.energy}</span>
                </MetaRow>
              )}

              {meta.domain && (
                <MetaRow label="Domain">
                  <IconValue icon={meta.domainIcon} label={meta.domain} />
                </MetaRow>
              )}

              {meta.cardType && (
                <MetaRow label="Card Type">
                  <IconValue icon={meta.cardTypeIcon} label={meta.cardType} />
                </MetaRow>
              )}

              {meta.ability && (
                <MetaRow label="Ability">
                  <div
                    className="card-modal-ability"
                    dangerouslySetInnerHTML={{ __html: replaceRbTokens(meta.ability) }}
                  />
                </MetaRow>
              )}

              {meta.rarity && (
                <MetaRow label="Rarity">
                  <IconValue icon={meta.rarityIcon} label={meta.rarity} />
                </MetaRow>
              )}

              {meta.artist && (
                <MetaRow label="Artist">
                  <span>{meta.artist}</span>
                </MetaRow>
              )}

              {meta.set && (
                <MetaRow label="Card Set">
                  <span>{meta.set}</span>
                </MetaRow>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
