import { useEffect } from "react";
import type { CardImages, CardMeta } from "../App";

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
                    dangerouslySetInnerHTML={{ __html: meta.ability }}
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
