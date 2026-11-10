/* ============================================================
   PokerStack card art — generated entirely in code.
   No downloaded images, no copyrighted artwork.
   ============================================================ */

export const SUITS = {
  s: { symbol: "\u2660", name: "Spades", colour: "black" },
  h: { symbol: "\u2665", name: "Hearts", colour: "red" },
  d: { symbol: "\u2666", name: "Diamonds", colour: "red" },
  c: { symbol: "\u2663", name: "Clubs", colour: "black" },
};

const RANK_LABELS = {
  2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9",
  10: "10", 11: "J", 12: "Q", 13: "K", 14: "A",
};
const RANK_WORDS = {
  2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven",
  8: "Eight", 9: "Nine", 10: "Ten", 11: "Jack", 12: "Queen", 13: "King",
  14: "Ace",
};

const PIP_LAYOUTS = {
  2: [[50, 24], [50, 76]],
  3: [[50, 20], [50, 50], [50, 80]],
  4: [[30, 24], [70, 24], [30, 76], [70, 76]],
  5: [[30, 24], [70, 24], [50, 50], [30, 76], [70, 76]],
  6: [[30, 20], [70, 20], [30, 50], [70, 50], [30, 80], [70, 80]],
  7: [[30, 20], [70, 20], [50, 35], [30, 55], [70, 55], [30, 82], [70, 82]],
  8: [[30, 18], [70, 18], [50, 34], [30, 42], [70, 42], [50, 66], [30, 82], [70, 82]],
  9: [[30, 17], [70, 17], [30, 39], [70, 39], [50, 50], [30, 61], [70, 61], [30, 83], [70, 83]],
  10: [[30, 15], [70, 15], [30, 36], [70, 36], [50, 27], [50, 73], [30, 64], [70, 64], [30, 85], [70, 85]],
};

function escapeAttr(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

export function cardAria(card) {
  if (!card) return "hidden card";
  const suit = SUITS[card.suit] || SUITS.s;
  return `${RANK_WORDS[card.rank] || card.rank} of ${suit.name}`;
}

function corner(card, klass) {
  const suit = SUITS[card.suit] || SUITS.s;
  const rank = card.rank_label || RANK_LABELS[card.rank] || "?";
  return `<div class="idx ${klass}"><b>${rank}</b><i>${suit.symbol}</i></div>`;
}

function pips(card) {
  const layout = PIP_LAYOUTS[card.rank] || PIP_LAYOUTS[2];
  const suit = SUITS[card.suit] || SUITS.s;
  const many = card.rank >= 9 ? " many" : "";
  return `<div class="pcard-art${many}">${layout.map(([x, y]) =>
    `<span class="pip${y > 55 ? " flip" : ""}" style="left:${x}%;top:${y}%">${suit.symbol}</span>`
  ).join("")}</div>`;
}

function aceArt(card) {
  const suit = SUITS[card.suit] || SUITS.s;
  return `
    <div class="ace-art">
      <div class="ace-rays"></div>
      <div class="ace-ring"></div>
      <div class="ace-suit">${suit.symbol}</div>
      <span class="ace-caption">Kashe Royale</span>
    </div>`;
}

function courtArt(card) {
  const suit = SUITS[card.suit] || SUITS.s;
  const letter = RANK_LABELS[card.rank] || "K";
  return `
    <div class="court-art">
      <div class="court-frame"></div>
      <div class="court-crown"></div>
      <span class="court-suit top">${suit.symbol}</span>
      <div class="court-letter">${letter}</div>
      <span class="court-suit bottom">${suit.symbol}</span>
    </div>`;
}

function artFor(card) {
  if (card.rank === 14) return aceArt(card);
  if (card.rank >= 11) return courtArt(card);
  return pips(card);
}

function frontFace(card) {
  const suit = SUITS[card.suit] || SUITS.s;
  return `
    <div class="pcard-face">
      <div class="paper-texture"></div>
      ${corner(card, "idx-tl")}
      ${corner(card, "idx-br")}
      ${artFor(card)}
    </div>`;
}

function backFace() {
  return `
    <div class="pcard-back">
      <div class="back-crest">\u2660</div>
    </div>`;
}

/**
 * Build one card as an HTML string.
 * opts: { faceDown, deal, flip, winner, tilt, dimmed, extraClass, style, hidden }
 */
export function cardMarkup(card, opts = {}) {
  const faceDown = !card || opts.faceDown;
  const suitColor = card && SUITS[card.suit] ? SUITS[card.suit].colour : "black";
  const classes = ["pcard"];
  if (faceDown) classes.push("face-down");
  if (card) classes.push(`suit-${card.suit}`, suitColor === "red" ? "red" : "black");
  if (opts.winner) classes.push("winner");
  if (opts.tilt) classes.push("tilt");
  if (opts.dimmed) classes.push("dimmed");
  if (opts.extraClass) classes.push(opts.extraClass);
  if (opts.deal) classes.push("will-deal");
  if (!faceDown && opts.flip) classes.push("will-flip");
  if (faceDown && opts.deal) classes.push("will-deal");
  const style = opts.style || "";
  const label = faceDown ? "Hidden card" : cardAria(card);
  const data = faceDown ? "" : ` data-code="${escapeAttr(card.code || "")}"`;
  return `<div class="${classes.join(" ")}" style="${style}" role="img" aria-label="${escapeAttr(label)}"${data}>
    <div class="pcard-inner">
      ${faceDown ? `<div class="pcard-face"></div>` : frontFace(card)}
      ${backFace()}
    </div>
  </div>`;
}

export function slotMarkup(style = "", extra = "") {
  return `<div class="card-slot ${extra}" style="${style}" aria-hidden="true"></div>`;
}

export function miniBackMarkup(width = 22) {
  return `<span class="mini-card" style="--mini-w:${width}px" aria-hidden="true"></span>`;
}

export function renderHeroCards(container) {
  if (!container) return;
  const cards = [
    { rank: 14, suit: "s" },
    { rank: 13, suit: "h" },
    { rank: 12, suit: "d" },
  ];
  container.innerHTML = cards.map((card) => cardMarkup(card, { tilt: true })).join("");
}

/**
 * Turn pre-rendered cards into their deal/flip animations.
 * Must be called after the markup is already in the DOM.
 */
export function runCardAnimations(root, deckAnchor) {
  if (!root) return;
  const anchorRect = deckAnchor
    ? deckAnchor.getBoundingClientRect()
    : { left: window.innerWidth / 2, top: window.innerHeight / 2, width: 0, height: 0 };
  const originX = anchorRect.left + anchorRect.width / 2;
  const originY = anchorRect.top + anchorRect.height / 2;

  const cards = Array.from(root.querySelectorAll(".pcard.will-deal, .pcard.will-flip"));
  cards.forEach((card, index) => {
    const rect = card.getBoundingClientRect();
    if (card.classList.contains("will-deal")) {
      const dx = originX - (rect.left + rect.width / 2);
      const dy = originY - (rect.top + rect.height / 2);
      card.style.setProperty("--dx", `${dx}px`);
      card.style.setProperty("--dy", `${dy}px`);
      card.style.setProperty("--deal-delay", `${Math.min(index * 55, 330)}ms`);
      card.classList.remove("will-deal");
      // Force a style flush so the animation begins from the deck.
      void card.offsetWidth;
      card.classList.add("deal-in");
      card.addEventListener("animationend", () => {
        card.classList.remove("deal-in");
        card.style.removeProperty("--dx");
        card.style.removeProperty("--dy");
        card.style.removeProperty("--deal-delay");
      }, { once: true });
    }
    if (card.classList.contains("will-flip")) {
      card.style.setProperty("--flip-delay", `${Math.min(index * 95, 380)}ms`);
      card.classList.remove("will-flip");
      void card.offsetWidth;
      card.classList.add("flip-in");
      card.addEventListener("animationend", () => {
        card.classList.remove("flip-in");
        card.style.removeProperty("--flip-delay");
      }, { once: true });
    }
  });
}

export function cardFromState(data) {
  if (!data || data.hidden) return null;
  return data;
}
