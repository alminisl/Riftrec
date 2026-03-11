import { useState } from "react";
import { createPortal } from "react-dom";
import type { CardImages } from "../App";

interface Props {
  name: string;
  cardImages: CardImages;
  onCardClick: (name: string) => void;
  children: React.ReactNode;
}

export function CardTooltip({ name, cardImages, onCardClick, children }: Props) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const imgUrl = cardImages[name];

  if (!imgUrl) return <span onClick={() => onCardClick(name)}>{children}</span>;

  const handleMove = (e: React.MouseEvent) => {
    const imgW = 250 + 12 + 16; // image width + padding + gap
    const imgH = 370;
    let x = e.clientX + 16;
    let y = e.clientY - 40;

    if (x + imgW > window.innerWidth) {
      x = e.clientX - imgW;
    }
    if (y + imgH > window.innerHeight) {
      y = window.innerHeight - imgH;
    }
    if (y < 8) y = 8;

    setPos({ x, y });
  };

  return (
    <span
      className="card-tooltip-trigger"
      onMouseEnter={(e) => { handleMove(e); setShow(true); }}
      onMouseMove={handleMove}
      onMouseLeave={() => setShow(false)}
      onClick={() => onCardClick(name)}
    >
      {children}
      {show &&
        createPortal(
          <div className="card-tooltip" style={{ left: pos.x, top: pos.y }}>
            <img src={imgUrl} alt={name} />
          </div>,
          document.body
        )}
    </span>
  );
}
