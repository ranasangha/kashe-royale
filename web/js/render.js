/* ============================================================
   PokerStack renderer — table, seats, cards, controls, modals
   ============================================================ */

import {
  cardMarkup,
  runCardAnimations,
  slotMarkup,
} from "./cards.js";

const PHASE_LABELS = {
  waiting: "Waiting",
  preflop: "Pre-flop",
  flop: "Flop",
  turn: "Turn",
  river: "River",
  hand_over: "Complete",
};

const STREET_LABELS = {
  preflop: "Pre-flop",
  flop: "Flop",
  turn: "Turn",
  river: "River",
};

const numberFormat = new Intl.NumberFormat("en-US");

export function formatChips(value) {
  const number = Number(value) || 0;
  return numberFormat.format(number);
}

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function fmtCardLabel(label) {
  if (!label) return "";
  const safe = esc(label);
  return safe;
}

function boardHTML(labels) {
  if (!labels || !labels.length) return "";
  return labels.map((label) => {
    const red = /[\u2665\u2666]/.test(label) || /[HD]$/.test(label);
    return `<span class="board-chip${red ? " red" : ""}">${esc(label)}</span>`;
  }).join("");
}

function initialStateKeys() {
  return {
    seenHoles: new Set(),
    seenFaces: new Set(),
    seenCommunity: new Set(),
  };
}

export class Renderer {
  constructor({ sound, onAction, onCommand } = {}) {
    this.sound = sound;
    this.onAction = onAction || (() => {});
    this.onCommand = onCommand || (() => {});
    this.state = null;
    this.previous = null;
    this.legal = null;
    this.seenHoles = new Set();
    this.seenFaces = new Set();
    this.seenCommunity = new Set();
    this.lastHandNo = null;
    this.lastActionSeq = null;
    this.lastResultKey = null;
    this.lastAudioResultKey = null;
    this.dismissedResultKey = null;
    this.lastCommunityCount = 0;
    this.wagerKey = null;
    this.wagerAmount = 0;
    this.busy = false;
    this.timerEndsAt = null;
    this.timerTotal = 0;
    this.activeSeat = null;
    this.refs = this.collectRefs();
    this.bindControls();
    this.timerInterval = window.setInterval(() => this.tickTimer(), 120);
    this.tickTimer();
  }

  collectRefs() {
    const byId = (id) => document.getElementById(id);
    return {
      game: byId("gameView"),
      tableName: byId("tableName"),
      handLabel: byId("handLabel"),
      blindLabel: byId("blindLabel"),
      playersLabel: byId("playersLabel"),
      roomCode: byId("roomCode"),
      roomCodeBtn: byId("roomCodeBtn"),
      seatsLayer: byId("seatsLayer"),
      community: byId("community"),
      potChips: byId("potChips"),
      potAmount: byId("potAmount"),
      potSide: byId("potSide"),
      streetLabel: byId("streetLabel"),
      tableMessage: byId("tableMessage"),
      deckCount: byId("deckCount"),
      deckAnchor: byId("deckAnchor"),
      winnerBanner: byId("winnerBanner"),
      winnerClose: byId("winnerClose"),
      winnerTitle: byId("winnerTitle"),
      winnerHand: byId("winnerHand"),
      winnerPots: byId("winnerPots"),
      chipLayer: byId("chiplayers"),
      turnDot: byId("turnDot"),
      turnText: byId("turnText"),
      turnTimerBar: byId("turnTimerBar"),
      turnTimerFill: byId("turnTimerFill"),
      dockNote: byId("dockNote"),
      dock: byId("actionDock"),
      dockActions: byId("dockActions"),
      dockSecondary: byId("dockSecondary"),
      dockHint: byId("dockHint"),
      spectatorNote: byId("spectatorNote"),
      btnFold: byId("btnFold"),
      btnCheck: byId("btnCheck"),
      btnCall: byId("btnCall"),
      callAmount: byId("callAmount"),
      btnRaise: byId("btnRaise"),
      raiseLabel: byId("raiseLabel"),
      raiseAmount: byId("raiseAmount"),
      btnAllIn: byId("btnAllIn"),
      allInAmount: byId("allInAmount"),
      wagerControl: byId("wagerControl"),
      wagerLabel: byId("wagerLabel"),
      wagerRange: byId("wagerRange"),
      betSlider: byId("betSlider"),
      betAmount: byId("betAmount"),
      start: byId("btnStart"),
      next: byId("btnNext"),
      sitOut: byId("btnSitOut"),
      rebuy: byId("btnRebuy"),
      undo: byId("btnUndo"),
      peek: byId("btnPeek"),
      copyInvite: byId("btnCopyInvite"),
      settingsBtn: byId("settingsBtn"),
      stackVizBtn: byId("stackVizBtn"),
      muteBtn: byId("muteBtn"),
      muteIcon: byId("muteIcon"),
      muteLabel: byId("muteLabel"),
    };
  }

  setHandlers({ onAction, onCommand }) {
    if (onAction) this.onAction = onAction;
    if (onCommand) this.onCommand = onCommand;
  }

  bindControls() {
    const r = this.refs;
    r.btnFold?.addEventListener("click", () => this.send("fold"));
    r.btnCheck?.addEventListener("click", () => this.send("check"));
    r.btnCall?.addEventListener("click", () => this.send("call"));
    r.btnRaise?.addEventListener("click", () => this.send(this.state?.current?.current_bet ? "raise" : "bet", this.wagerAmount));
    r.btnAllIn?.addEventListener("click", () => this.send("allin"));
    r.winnerClose?.addEventListener("click", () => {
      if (this.lastResultKey) this.dismissedResultKey = this.lastResultKey;
      if (r.winnerBanner) r.winnerBanner.hidden = true;
    });
    document.querySelectorAll("[data-quick]").forEach((button) => {
      button.addEventListener("click", () => this.applyQuick(button.dataset.quick));
    });
    r.betSlider?.addEventListener("input", () => {
      this.wagerAmount = Number(r.betSlider.value) || 0;
      if (r.betAmount) r.betAmount.value = String(this.wagerAmount);
      this.updateRaiseDisplay();
      this.updateSliderFill();
    });
    r.betAmount?.addEventListener("input", () => {
      const value = Number(r.betAmount.value);
      if (Number.isFinite(value)) {
        this.wagerAmount = value;
        if (r.betSlider) r.betSlider.value = String(value);
        this.updateRaiseDisplay();
        this.updateSliderFill();
      }
    });
    r.betAmount?.addEventListener("change", () => this.clampWager());
    r.betAmount?.addEventListener("blur", () => this.clampWager());
    r.start?.addEventListener("click", () => this.onCommand("start"));
    r.next?.addEventListener("click", () => this.onCommand("next"));
    r.sitOut?.addEventListener("click", () => this.onCommand("sit"));
    r.rebuy?.addEventListener("click", () => this.onCommand("rebuy"));
    r.undo?.addEventListener("click", () => this.onCommand("undo"));
    r.peek?.addEventListener("click", () => this.onCommand("peek"));
    r.copyInvite?.addEventListener("click", () => this.onCommand("invite"));
    r.roomCodeBtn?.addEventListener("click", () => this.onCommand("invite"));
    r.settingsBtn?.addEventListener("click", () => this.onCommand("settings"));
  }

  setBusy(value) {
    this.busy = Boolean(value);
    this.refs.dock?.classList.toggle("busy", this.busy);
    if (this.busy) {
      ['btnFold', 'btnCheck', 'btnCall', 'btnRaise', 'btnAllIn'].forEach((key) => {
        const button = this.refs[key];
        if (button) button.disabled = true;
      });
    } else {
      this.renderActionBar();
    }
  }

  resetForGame() {
    this.state = null;
    this.previous = null;
    this.legal = null;
    this.lastHandNo = null;
    this.lastActionSeq = null;
    this.lastResultKey = null;
    this.lastAudioResultKey = null;
    this.lastAnimatedResult = null;
    this.dismissedResultKey = null;
    this.lastCommunityCount = 0;
    this.wagerKey = null;
    this.wagerAmount = 0;
    this.timerEndsAt = null;
    this.timerTotal = 0;
    this.activeSeat = null;
    const keys = initialStateKeys();
    this.seenHoles = keys.seenHoles;
    this.seenFaces = keys.seenFaces;
    this.seenCommunity = keys.seenCommunity;
    if (this.refs.winnerBanner) this.refs.winnerBanner.hidden = true;
    if (this.refs.seatsLayer) this.refs.seatsLayer.innerHTML = "";
    if (this.refs.community) this.refs.community.innerHTML = "";
    if (this.refs.chipLayer) this.refs.chipLayer.innerHTML = "";
  }

  send(action, amount = null) {
    if (this.busy) return;
    if (!this.legal?.is_turn) return;
    this.onAction(action, amount);
  }

  applyQuick(kind) {
    if (!this.legal?.wager?.allowed) return;
    const min = Number(this.legal.wager.min);
    const max = Number(this.legal.wager.max);
    const pot = Number(this.state?.pot?.total || 0);
    const toCall = Number(this.legal.to_call || 0);
    const currentBet = Number(this.state?.current?.current_bet || 0);
    let value;
    if (kind === "min") value = min;
    else if (kind === "allin") value = max;
    else {
      const fraction = kind === "half" ? 0.5 : kind === "threequarter" ? 0.75 : 1;
      const potAfterCall = pot + toCall;
      value = currentBet + Math.round(potAfterCall * fraction);
    }
    this.wagerAmount = Math.max(min, Math.min(max, Math.round(value)));
    this.syncWagerInputs();
    this.updateRaiseDisplay();
    this.updateSliderFill();
    this.sound?.click();
  }

  clampWager() {
    if (!this.legal?.wager) return;
    const min = Number(this.legal.wager.min);
    const max = Number(this.legal.wager.max);
    const raw = Number(this.refs.betAmount?.value);
    const value = Number.isFinite(raw) ? raw : this.wagerAmount;
    this.wagerAmount = Math.max(min, Math.min(max, Math.round(value)));
    this.syncWagerInputs();
    this.updateRaiseDisplay();
    this.updateSliderFill();
  }

  syncWagerInputs() {
    const r = this.refs;
    if (r.betSlider) r.betSlider.value = String(this.wagerAmount);
    if (r.betAmount && document.activeElement !== r.betAmount) {
      r.betAmount.value = String(this.wagerAmount);
    }
  }

  updateSliderFill() {
    const r = this.refs;
    if (!r.betSlider) return;
    const min = Number(r.betSlider.min) || 0;
    const max = Number(r.betSlider.max) || 1;
    const value = Number(r.betSlider.value) || 0;
    const pct = max > min ? ((value - min) / (max - min)) * 100 : 100;
    r.betSlider.style.setProperty("--fill", `${pct}%`);
  }

  updateRaiseDisplay() {
    if (!this.refs.raiseAmount) return;
    this.refs.raiseAmount.textContent = this.legal?.wager?.allowed
      ? `to ${formatChips(this.wagerAmount)}`
      : "";
  }

  updateTimerBase(state) {
    const remaining = state?.current?.turn_remaining;
    const r = this.refs;
    if (remaining === null || remaining === undefined) {
      this.timerEndsAt = null;
      this.timerTotal = 0;
      if (r.turnTimerBar) r.turnTimerBar.hidden = true;
      this.activeSeat = null;
      return;
    }
    this.timerTotal = Math.max(1, Number(state.table.turn_seconds) || remaining || 1);
    this.timerEndsAt = performance.now() + Number(remaining) * 1000;
    this.activeSeat = state.current.actor_seat;
    if (r.turnTimerBar) r.turnTimerBar.hidden = false;
    this.tickTimer();
  }

  tickTimer() {
    const r = this.refs;
    let ratio = 1;
    if (this.timerEndsAt !== null && this.timerTotal > 0) {
      const remaining = Math.max(0, (this.timerEndsAt - performance.now()) / 1000);
      ratio = Math.max(0, Math.min(1, remaining / this.timerTotal));
      if (r.turnTimerFill) r.turnTimerFill.style.width = `${ratio * 100}%`;
      const seat = r.seatsLayer?.querySelector(`.seat[data-seat="${this.activeSeat}"]`);
      seat?.style.setProperty("--progress", ratio.toFixed(3));
      if (ratio <= 0.0001 && seat) seat.style.setProperty("--progress", "0");
    } else if (r.turnTimerFill) {
      r.turnTimerFill.style.width = "0%";
    }
    if (this.activeSeat !== null && this.activeSeat !== undefined) {
      const seat = r.seatsLayer?.querySelector(`.seat[data-seat="${this.activeSeat}"]`);
      seat?.style.setProperty("--progress", ratio.toFixed(3));
    }
  }

  resetForHand() {
    const keys = initialStateKeys();
    this.seenHoles = keys.seenHoles;
    this.seenFaces = keys.seenFaces;
    this.seenCommunity = keys.seenCommunity;
    this.lastCommunityCount = 0;
    this.dismissedResultKey = null;
    if (this.refs.winnerBanner) this.refs.winnerBanner.hidden = true;
  }

  render(state) {
    if (!state) return;
    this.state = state;
    this.legal = state.legal;
    if (state.hand_no !== this.lastHandNo) {
      this.lastHandNo = state.hand_no;
      this.resetForHand();
      this.wagerKey = null;
    }
    if (this.dismissedResultKey && state.phase !== "hand_over") {
      this.dismissedResultKey = null;
    }
    this.renderHeader();
    this.renderSeats();
    this.renderCommunity();
    this.renderPot();
    this.renderStatus();
    this.renderActionBar();
    this.renderWinner();
    this.updateTimerBase(state);
    this.applyAudio(state);
    this.renderSettingsAvailability();
    this.previous = state;

    const anchor = this.refs.deckAnchor && this.refs.deckAnchor.offsetParent
      ? this.refs.deckAnchor
      : null;
    window.requestAnimationFrame(() => {
      runCardAnimations(this.refs.game, anchor);
      this.tickTimer();
    });
  }

  renderHeader() {
    const state = this.state;
    const r = this.refs;
    if (!state) return;
    const table = state.table;
    document.title = `${table.name} · Kashe Royale`;
    if (r.tableName) r.tableName.textContent = table.name;
    if (r.roomCode) r.roomCode.textContent = state.room?.code || state.invite_code || "-----";
    if (r.blindLabel) r.blindLabel.textContent = `Blinds ${formatChips(table.small_blind)} / ${formatChips(table.big_blind)}`;
    if (r.playersLabel) {
      const active = state.seats.filter((seat) => !seat.sitting_out && !seat.waiting).length;
      r.playersLabel.textContent = `${active} / ${table.max_players} players`;
    }
    if (r.handLabel) {
      if (!state.started) r.handLabel.textContent = "Waiting for players";
      else if (state.phase === "hand_over") r.handLabel.textContent = `Hand #${state.hand_no} · complete`;
      else r.handLabel.textContent = `Hand #${state.hand_no} · ${PHASE_LABELS[state.phase] || state.phase}`;
    }
  }

  seatPositions(seats) {
    const ordered = [...seats].sort((a, b) => a.seat - b.seat);
    const viewerSeat = this.state?.viewer?.seat;
    let heroIndex = ordered.findIndex((seat) => seat.seat === viewerSeat);
    if (heroIndex < 0) heroIndex = 0;
    const rotated = [...ordered.slice(heroIndex), ...ordered.slice(0, heroIndex)];
    const total = rotated.length;
    return rotated.map((seat, index) => {
      const angle = ((90 + (index * 360) / Math.max(1, total)) * Math.PI) / 180;
      const x = 50 + 42.5 * Math.cos(angle);
      const y = 48.5 + 39.5 * Math.sin(angle);
      const vx = 50 - x;
      const vy = 48.5 - y;
      const length = Math.hypot(vx, vy) || 1;
      const bx = (vx / length) * 66;
      const by = (vy / length) * 66;
      let side = "side-middle";
      if (y < 36) side = "side-top";
      else if (y > 62) side = "side-bottom";
      else side = x < 50 ? "side-left" : "side-right";
      return { seat, x, y, bx, by, side, isHero: seat.seat === viewerSeat };
    });
  }

  renderSeats() {
    const state = this.state;
    const r = this.refs;
    if (!r.seatsLayer || !state) return;
    if (!state.seats.length) {
      r.seatsLayer.innerHTML = "";
      return;
    }
    const positions = this.seatPositions(state.seats);
    const result = state.phase === "hand_over" ? state.result : null;
    const winnerSeats = new Set((result?.winners || []).map((w) => w.seat));
    const winnerCodes = new Map();
    (result?.winners || []).forEach((winner) => {
      winnerCodes.set(winner.seat, new Set((winner.best_five || []).map((card) => card.code)));
    });
    const revealedBySeat = new Map((result?.revealed || []).map((entry) => [entry.seat, entry]));
    const viewerSeat = state.viewer?.seat;
    const practice = state.practice;
    const html = positions.map((position) => {
      const seat = position.seat;
      const seatVisibleCards = (seat.cards || []).filter((card) => !card.hidden);
      const isHero = seat.seat === viewerSeat;
      const classes = ["seat", position.side];
      if (isHero) classes.push("self");
      if (seat.seat === state.current?.actor_seat && ["preflop", "flop", "turn", "river"].includes(state.phase)) classes.push("active");
      if (winnerSeats.has(seat.seat)) classes.push("winner");
      if (seat.folded) classes.push("folded");
      if (seat.sitting_out) classes.push("sitting-out");
      if (seat.waiting) classes.push("waiting");
      if (!seat.connected) classes.push("disconnected");
      if (seat.chips <= 0 && !seat.in_hand) classes.push("busted");
      if (seat.last_action) classes.push("has-action");
      const badgeList = [];
      if (seat.is_dealer) badgeList.push('<span class="badge dealer">D</span>');
      if (seat.is_sb) badgeList.push('<span class="badge sb">SB</span>');
      if (seat.is_bb) badgeList.push('<span class="badge bb">BB</span>');
      if (winnerSeats.has(seat.seat)) badgeList.push('<span class="badge winner">&#9819;</span>');

      const cards = (seat.cards || []).map((card, index) => {
        const holeKey = `${state.hand_no}:${seat.seat}:${index}`;
        const visible = !card.hidden;
        const faceKey = holeKey;
        const hadBack = this.seenHoles.has(holeKey);
        const faceSeen = this.seenFaces.has(faceKey);
        let markup;
        if (!visible) {
          markup = cardMarkup(null, {
            faceDown: true,
            deal: !hadBack,
            tilt: true,
          });
          if (!hadBack) this.seenHoles.add(holeKey);
        } else {
          const winner = winnerSeats.has(seat.seat)
            && (winnerCodes.get(seat.seat)?.has(card.code) ?? false);
          if (!hadBack) {
            markup = cardMarkup(card, { deal: true, winner, tilt: true });
            this.seenHoles.add(holeKey);
            this.seenFaces.add(faceKey);
          } else if (!faceSeen) {
            markup = cardMarkup(card, { flip: true, winner, tilt: true });
            this.seenFaces.add(faceKey);
          } else {
            markup = cardMarkup(card, { winner, tilt: true });
          }
        }
        return markup;
      }).join("");

      const cardSlots = (!seat.cards || seat.cards.length === 0) && seat.in_hand
        ? slotMarkup("", "") + slotMarkup("", "")
        : "";
      const statusText = seat.waiting
        ? "Waiting"
        : seat.sitting_out
          ? "Sitting out"
          : "";
      const actionText = revealedBySeat.get(seat.seat)?.hand_name || seat.last_action || "";
      const cardClass = ["seat-cards"];
      if (isHero) cardClass.push("self");
      const bet = Number(seat.bet || 0);
      return `
        <article class="${classes.join(" ")}" data-seat="${seat.seat}"
                 style="--sx:${position.x.toFixed(2)}%;--sy:${position.y.toFixed(2)}%;--bx:${position.bx.toFixed(1)}px;--by:${position.by.toFixed(1)}px;--progress:1"
                 title="${esc(seat.name)}${seat.connected ? "" : " (disconnected)"}">
          <div class="seat-inner">
            <div class="${cardClass.join(" ")}">${cards || cardSlots}</div>
            <div class="seat-plate">
              <div class="badges">${badgeList.join("")}</div>
              <div class="seat-avatar">${esc((seat.name || "?").slice(0, 1).toUpperCase())}</div>
              <div class="seat-info">
                <div class="seat-name">${esc(seat.name)}${isHero ? '<span class="seat-you">You</span>' : ""}</div>
                <div class="seat-chips">${formatChips(seat.chips)}</div>
              </div>
              ${statusText ? `<div class="seat-status">${esc(statusText)}</div>` : ""}
            </div>
            ${bet > 0 ? `<div class="seat-bet">${formatChips(bet)}</div>` : ""}
            ${actionText ? `<div class="seat-action">${esc(actionText)}</div>` : ""}
          </div>
        </article>`;
    }).join("");
    r.seatsLayer.innerHTML = html;
    this.tickTimer();
  }

  renderCommunity() {
    const state = this.state;
    const r = this.refs;
    if (!r.community || !state) return;
    const result = state.phase === "hand_over" ? state.result : null;
    const winnerCodes = new Set();
    (result?.winners || []).forEach((winner) => {
      (winner.best_five || []).forEach((card) => winnerCodes.add(card.code));
    });
    const cards = state.community || [];
    let html = "";
    cards.forEach((card, index) => {
      const key = `${state.hand_no}:c:${index}`;
      const seen = this.seenCommunity.has(key);
      const winner = winnerCodes.has(card.code);
      html += cardMarkup(card, {
        flip: !seen,
        winner,
        tilt: true,
      });
      this.seenCommunity.add(key);
    });
    for (let index = cards.length; index < 5; index += 1) {
      html += slotMarkup();
    }
    r.community.innerHTML = html;
    this.lastCommunityCount = cards.length;
  }

  renderPot() {
    const state = this.state;
    const r = this.refs;
    if (!r.potAmount || !state) return;
    const showResult = state.phase === "hand_over" && state.result;
    const amount = showResult ? state.result.pot : (state.pot?.total || 0);
    r.potAmount.textContent = formatChips(amount);
    const levels = Math.min(6, Math.max(0, Math.ceil(amount / Math.max(1, (state.table.big_blind || 10) * 8))));
    let chips = "";
    for (let index = 0; index < levels; index += 1) {
      const cls = index % 3 === 0 ? "black" : index % 5 === 0 ? "red" : "";
      chips += `<span class="chip-disc ${cls}" style="left:${index * 4}px;top:${index * 3}px;z-index:${index}"></span>`;
    }
    r.potChips.innerHTML = chips;
    const layers = showResult && state.result.pot_layers?.length
      ? state.result.pot_layers
      : (state.pot?.layers_top_first || []);
    if (layers.length > 1) {
      r.potSide.innerHTML = layers.map((layer) =>
        `<span title="${esc(layer.label)}: ${formatChips(layer.amount)}">${esc(layer.label.replace("Pot", ""))} ${formatChips(layer.amount)}</span>`
      ).join("");
    } else {
      r.potSide.innerHTML = "";
    }
  }

  renderStatus() {
    const state = this.state;
    const r = this.refs;
    if (!state || !r.streetLabel) return;
    let street = "Waiting";
    if (state.phase === "hand_over") street = state.result?.reason === "showdown" ? "Showdown" : "Hand complete";
    else if (STREET_LABELS[state.phase]) street = STREET_LABELS[state.phase];
    r.streetLabel.textContent = street;
    let message = state.message || "";
    if (state.phase === "hand_over" && state.result?.message) message = state.result.message;
    if (!state.started) {
      if (state.seats.length < 2) message = "Share the room code — waiting for a challenger.";
    }
    r.tableMessage.textContent = message;
    if (r.deckCount) r.deckCount.textContent = String(state.viz?.deck?.size ?? 0);
  }

  renderActionBar() {
    const state = this.state;
    const r = this.refs;
    if (!state) return;
    const spectator = Boolean(state.viewer?.is_spectator);
    const isActive = ["preflop", "flop", "turn", "river"].includes(state.phase);
    const myTurn = Boolean(this.legal?.is_turn);
    const actorName = state.current?.actor_name;
    r.dock?.classList.toggle("myturn", myTurn);
    r.dock?.classList.toggle("spectator", spectator);
    if (r.spectatorNote) r.spectatorNote.hidden = !spectator;
    if (r.dockActions) r.dockActions.hidden = spectator || !isActive;
    if (r.dockHint) r.dockHint.textContent = myTurn ? "F fold · C check/call · R raise" : "";

    if (r.turnDot) r.turnDot.classList.toggle("live", isActive);
    if (r.turnText) {
      if (spectator) r.turnText.textContent = "Spectating the velvet room";
      else if (myTurn) {
        r.turnText.textContent = state.practice
          ? `Hot-seat · ${actorName} to act`
          : "Your turn — choose an action";
      } else if (isActive) {
        r.turnText.textContent = actorName ? `Waiting for ${actorName}…` : "Waiting for the next action…";
      } else if (state.phase === "hand_over") {
        r.turnText.textContent = "Hand complete";
      } else {
        r.turnText.textContent = state.started ? "Preparing the next hand…" : "Waiting for players…";
      }
    }
    if (r.dockNote) {
      r.dockNote.textContent = myTurn
        ? (state.legal?.wager?.reason && !state.legal.wager.allowed ? state.legal.wager.reason : "Your move.")
        : (state.message || "");
    }

    this.renderActionButtons();
    this.renderSecondary();
  }

  setButton(button, enabled, reason) {
    if (!button) return;
    button.disabled = !enabled;
    button.title = enabled ? "" : (reason || "");
  }

  renderActionButtons() {
    const state = this.state;
    const legal = this.legal;
    const r = this.refs;
    const spectator = Boolean(state?.viewer?.is_spectator);
    const active = ["preflop", "flop", "turn", "river"].includes(state?.phase);
    const turn = Boolean(legal?.is_turn);
    const foldOk = turn && legal?.fold?.allowed;
    const checkOk = turn && legal?.check?.allowed;
    const callOk = turn && legal?.call?.allowed;
    const wagerOk = turn && legal?.wager?.allowed;
    const allinOk = turn && legal?.all_in?.allowed;

    this.setButton(r.btnFold, foldOk, legal?.fold?.reason || "It is not your turn.");
    this.setButton(r.btnCheck, checkOk, legal?.check?.reason);
    this.setButton(r.btnCall, callOk, legal?.call?.reason);
    this.setButton(r.btnRaise, wagerOk, legal?.wager?.reason);
    this.setButton(r.btnAllIn, allinOk, legal?.all_in?.reason);

    if (r.btnCall && legal?.call) {
      if (legal.call.allowed) {
        r.callAmount.textContent = legal.call.all_in
          ? `all-in ${formatChips(legal.call.amount)}`
          : formatChips(legal.call.amount);
      } else {
        r.callAmount.textContent = "";
      }
    }
    if (r.callAmount && !legal?.call?.allowed) r.callAmount.textContent = "";

    if (r.raiseLabel) r.raiseLabel.textContent = legal?.wager_label || (state?.current?.current_bet ? "Raise" : "Bet");
    if (r.allInAmount) r.allInAmount.textContent = legal?.all_in?.allowed ? formatChips(legal.chips) : "";
    if (r.wagerLabel) r.wagerLabel.textContent = legal?.wager_label || "Bet";
    if (r.wagerControl) r.wagerControl.title = legal?.wager?.reason || "";

    const min = Number(legal?.wager?.min || 0);
    const max = Number(legal?.wager?.max || 0);
    if (r.wagerRange) {
      r.wagerRange.textContent = wagerOk
        ? `${formatChips(min)} – ${formatChips(max)}`
        : (legal?.wager?.reason || (active ? "No wager available" : "Waiting"));
    }
    if (r.betSlider) {
      r.betSlider.min = String(min || 0);
      r.betSlider.max = String(Math.max(min, max));
      r.betSlider.disabled = !wagerOk;
    }
    if (r.betAmount) {
      r.betAmount.min = String(min || 0);
      r.betAmount.max = String(Math.max(min, max));
      r.betAmount.disabled = !wagerOk;
    }
    const key = `${state?.hand_no}:${legal?.actor_seat ?? "x"}:${state?.phase}:${state?.current?.current_bet}:${min}:${max}:${wagerOk}`;
    if (wagerOk && key !== this.wagerKey) {
      this.wagerKey = key;
      this.wagerAmount = Math.max(min, Math.min(max, min));
      this.syncWagerInputs();
    } else if (wagerOk) {
      this.wagerAmount = Math.max(min, Math.min(max, this.wagerAmount || min));
      this.syncWagerInputs();
    } else {
      this.wagerKey = key;
    }
    this.updateRaiseDisplay();
    this.updateSliderFill();
    document.querySelectorAll("[data-quick]").forEach((button) => {
      button.disabled = !wagerOk;
    });
    if (spectator) {
      [r.btnFold, r.btnCheck, r.btnCall, r.btnRaise, r.btnAllIn].forEach((button) => {
        if (button) button.disabled = true;
      });
    }
  }

  renderSecondary() {
    const state = this.state;
    const r = this.refs;
    if (!state) return;
    const spectator = Boolean(state.viewer?.is_spectator);
    const practice = Boolean(state.practice);
    const host = Boolean(state.room?.is_host);
    const phaseActive = ["preflop", "flop", "turn", "river"].includes(state.phase);
    const seated = Boolean(state.viewer?.is_seated);
    const waiting = state.phase === "waiting";

    if (r.start) {
      r.start.hidden = !(waiting && host && !practice);
      r.start.disabled = !state.can_start;
      r.start.title = state.can_start ? "Deal the first hand" : "Waiting for enough players";
    }
    if (r.next) {
      r.next.hidden = !(state.phase === "hand_over" && (seated || state.viewer?.is_controller));
      r.next.disabled = !state.can_next;
      r.next.title = state.can_next ? "Deal the next hand" : "Waiting for enough players with chips";
    }
    if (r.sitOut) {
      r.sitOut.hidden = practice || !seated || spectator;
      r.sitOut.textContent = state.viewer?.sitting_out ? "Sit in" : "Sit out";
      r.sitOut.title = phaseActive ? "Takes effect next hand" : "Toggle your seat";
    }
    if (r.rebuy) {
      const needs = seated && !practice && !spectator && state.viewer.chips < state.table.big_blind;
      r.rebuy.hidden = !needs || phaseActive;
      r.rebuy.disabled = phaseActive;
      r.rebuy.title = phaseActive ? "Rebuy between hands" : "Add a fresh starting stack";
    }
    if (r.undo) {
      r.undo.hidden = !(state.demo_enabled && host);
      r.undo.disabled = !state.undo_available;
      r.undo.title = state.undo_available ? "Undo the last decision — Stack.pop()" : "Nothing to undo";
    }
    if (r.peek) {
      r.peek.hidden = !(state.demo_enabled && host);
      r.peek.disabled = state.phase === "waiting" || (state.viz?.deck?.size ?? 0) <= 0;
      r.peek.title = "Peek at the top of the deck stack (demo only)";
    }
    if (r.copyInvite) r.copyInvite.hidden = practice;
    if (r.dockHint) {
      r.dockHint.textContent = state.phase === "hand_over"
        ? "Next hand moves the button"
        : (state.current?.actor_name && !spectator ? `${state.practice ? "Hot-seat" : "Turn"}: ${state.current.actor_name}` : "");
    }
  }

  renderSettingsAvailability() {
    const state = this.state;
    const r = this.refs;
    if (!r.settingsBtn || !state) return;
    const allowed = Boolean(state.room?.is_host);
    r.settingsBtn.disabled = !allowed;
    r.settingsBtn.title = allowed ? "Table settings (between hands)" : "Only the host can change settings";
    r.settingsBtn.style.opacity = allowed ? "" : "0.45";
  }

  renderWinner() {
    const state = this.state;
    const r = this.refs;
    if (!r.winnerBanner || !state) return;
    if (state.phase !== "hand_over" || !state.result) {
      if (r.winnerBanner.hidden === false && state.phase !== "hand_over") r.winnerBanner.hidden = true;
      return;
    }
    const result = state.result;
    const key = `${state.hand_no}:${result.headline}`;
    this.lastResultKey = key;
    if (this.dismissedResultKey === key) {
      r.winnerBanner.hidden = true;
      return;
    }
    const winners = result.winners || [];
    const kicker = winners.length > 1
      ? (new Set(winners.map((w) => w.amount)).size === 1 ? "Split pot" : "Pots awarded")
      : "Winner";
    const title = winners.length === 1
      ? `${winners[0].name} wins ${formatChips(winners[0].amount)}`
      : (winners.length > 1
        ? `${winners.map((w) => w.name).join(" & ")}`
        : result.headline);
    const handNames = [...new Set(winners.map((w) => w.hand_name).filter(Boolean))];
    const handLine = result.reason === "fold"
      ? "Everyone folded — cards stay hidden"
      : (handNames.length ? handNames.join(" · ") : "Showdown");
    const pots = (result.pot_layers || []).map((layer) => {
      const names = (layer.winners || []).map((w) => w.name).join(", ");
      return `<span>${esc(layer.label)} ${formatChips(layer.amount)}${names ? ` · ${esc(names)}` : ""}</span>`;
    }).join("");
    r.winnerBanner.innerHTML = `
      <button class="winner-close" id="winnerClose" aria-label="Dismiss">&times;</button>
      <span class="winner-kicker">${esc(kicker)}</span>
      <h2>${esc(title)}</h2>
      <p>${esc(handLine)}</p>
      <div class="winner-pots">${pots || `<span>${formatChips(result.pot)} chips</span>`}</div>`;
    r.winnerBanner.hidden = false;
    r.winnerClose = document.getElementById("winnerClose");
    r.winnerClose?.addEventListener("click", () => {
      this.dismissedResultKey = key;
      r.winnerBanner.hidden = true;
    });
    if (key !== this.lastAnimatedResult) {
      this.lastAnimatedResult = key;
      this.animateChips(winners);
    }
  }

  animateChips(winners) {
    const r = this.refs;
    if (!r.chipLayer || !winners?.length) return;
    const stage = r.game?.querySelector(".table-stage");
    if (!stage) return;
    const stageRect = stage.getBoundingClientRect();
    const potRect = r.potChips?.getBoundingClientRect();
    const fromX = potRect ? potRect.left + potRect.width / 2 - stageRect.left : stageRect.width / 2;
    const fromY = potRect ? potRect.top + potRect.height / 2 - stageRect.top : stageRect.height / 2;
    r.chipLayer.innerHTML = "";
    winners.forEach((winner, winnerIndex) => {
      const seat = r.seatsLayer?.querySelector(`.seat[data-seat="${winner.seat}"] .seat-plate`);
      if (!seat) return;
      const rect = seat.getBoundingClientRect();
      const toX = rect.left + rect.width / 2 - stageRect.left - fromX;
      const toY = rect.top + rect.height / 2 - stageRect.top - fromY;
      const count = winners.length > 1 ? 6 : 12;
      for (let index = 0; index < count; index += 1) {
        const chip = document.createElement("span");
        chip.className = "flying-chip";
        chip.style.setProperty("--from-x", `${fromX + (Math.random() - 0.5) * 38}px`);
        chip.style.setProperty("--from-y", `${fromY + (Math.random() - 0.5) * 22}px`);
        chip.style.setProperty("--to-x", `${toX + (Math.random() - 0.5) * 26}px`);
        chip.style.setProperty("--to-y", `${toY + (Math.random() - 0.5) * 20}px`);
        chip.style.setProperty("--delay", `${winnerIndex * 110 + index * 34}ms`);
        r.chipLayer.appendChild(chip);
      }
    });
    window.setTimeout(() => {
      if (r.chipLayer) r.chipLayer.innerHTML = "";
    }, 1900);
  }

  applyAudio(state) {
    const prev = this.previous;
    const top = state.action_log?.[0];
    const result = state.phase === "hand_over" ? state.result : null;
    if (!prev) {
      this.lastActionSeq = top?.seq ?? null;
      this.lastAudioResultKey = result ? `${state.hand_no}:${result.headline}` : null;
      return;
    }
    if (state.hand_no !== prev.hand_no) {
      this.lastActionSeq = top?.seq ?? null;
      if (state.seats.some((seat) => (seat.cards || []).length)) this.sound?.deal();
    } else if (top && top.seq !== this.lastActionSeq) {
      this.lastActionSeq = top.seq;
      const kind = top.kind;
      if (kind === "fold") this.sound?.fold();
      else if (kind === "check") this.sound?.check();
      else if (["call", "bet", "raise", "allin", "blind", "refund"].includes(kind)) this.sound?.chip();
      else if (["flop", "turn", "river", "showdown"].includes(kind)) this.sound?.flip();
    }
    if (result) {
      const key = `${state.hand_no}:${result.headline}`;
      if (this.lastAudioResultKey !== key) {
        this.lastAudioResultKey = key;
        this.sound?.win();
      }
    } else {
      this.lastAudioResultKey = null;
    }
  }
}

/* ============================================================ modal content */

export function cheatSheetHTML() {
  const rows = [
    ["Royal Flush", "A, K, Q, J, 10 — all one suit", ["A♠", "K♠", "Q♠", "J♠", "10♠"]],
    ["Straight Flush", "Five in sequence, same suit", ["9♥", "8♥", "7♥", "6♥", "5♥"]],
    ["Four of a Kind", "All four cards of one rank", ["7♠", "7♥", "7♦", "7♣", "A♠"]],
    ["Full House", "Three of a kind plus a pair", ["K♠", "K♥", "K♦", "8♣", "8♠"]],
    ["Flush", "Five cards of the same suit", ["A♣", "J♣", "9♣", "6♣", "3♣"]],
    ["Straight", "Five consecutive ranks (A low or high)", ["9♦", "8♣", "7♥", "6♠", "5♦"]],
    ["Three of a Kind", "Three cards of one rank", ["Q♠", "Q♥", "Q♦", "A♣", "4♠"]],
    ["Two Pair", "Two different pairs", ["J♠", "J♥", "6♦", "6♣", "K♠"]],
    ["One Pair", "Two cards of one rank", ["10♠", "10♥", "A♦", "K♣", "7♠"]],
    ["High Card", "Nothing else — highest cards win", ["A♠", "Q♦", "9♣", "7♥", "4♠"]],
  ];
  return `
    <div class="cheat-list">${rows.map(([name, description, cards], index) => `
      <div class="cheat-row${index === 0 ? " top" : ""}">
        <span class="cheat-rank">${index + 1}</span>
        <span class="cheat-name">${esc(name)}<small>${esc(description)}</small></span>
        <span class="cheat-example">${cards.map((card) =>
          `<span class="${/[\u2665\u2666]/.test(card) ? "red" : ""}">${esc(card)}</span>`).join("")}</span>
      </div>`).join("")}</div>
    <div class="cheat-note">
      Compare category first, then the relevant ranks and kickers. Suits never break a tie.
      The wheel <strong>A-2-3-4-5</strong> is the lowest straight; <strong>Q-K-A-2-3</strong> is not a straight.
      Every player is credited with their best five cards from any combination of hole and community cards.
    </div>`;
}

export function rulesHTML() {
  return `
  <div class="rules-scroll">
    <div class="rule-callout">
      <strong>Virtual chips only.</strong> Kashe Royale is a university data-structures project.
      No real-money gambling, deposits or prizes are involved anywhere in this game.
    </div>
    <h3>1. Objective</h3>
    <p>No-Limit Texas Hold'em. Each player gets two private cards and shares five community cards.
    Win chips by holding the best five-card hand at showdown, or by making every opponent fold.</p>
    <h3>2. Players &amp; blinds</h3>
    <p>Two to ten players (the web table seats up to six). The dealer button moves one seat clockwise per hand.
    With three or more players the next two seats post the small and big blinds. Heads-up, the dealer posts the
    small blind and acts first pre-flop. A player needs at least the big blind to be dealt in.</p>
    <h3>3. The deal</h3>
    <p>Each player receives two private cards, one at a time clockwise from the dealer. Private cards are visible
    only to their owner. One card is burned before the flop, turn and river. The flop is three cards; the turn and
    river add one each.</p>
    <h3>4. Betting rounds</h3>
    <p>Pre-flop, the first player clockwise from the big blind acts (the dealer in heads-up). Post-flop, the first
    active player clockwise from the dealer acts. The big blind has an option to check when nobody has raised.</p>
    <p><strong>Actions:</strong> Fold, Check (no bet outstanding), Call, Bet, Raise, All-in. A bet must be at least the
    big blind. A raise must normally be at least as large as the previous full bet or raise. A short all-in is legal,
    but it does not reopen the raising action for players who have already acted — they may only call or fold.
    No one may wager more chips than they hold.</p>
    <h3>5. Showdown &amp; hand rankings</h3>
    <p>All remaining players reveal their cards and are credited with their strongest five-card hand from their two
    hole cards plus the five board cards. Category beats category; then ranks and kickers decide. Suits never matter.
    Royal flush, straight flush, four of a kind, full house, flush, straight, three of a kind, two pair, one pair,
    high card. The wheel (A-2-3-4-5) is the lowest straight; Q-K-A-2-3 is not a straight.</p>
    <h3>6. Pots, side pots &amp; uncalled bets</h3>
    <p>All bets and blinds go into the pot. If players have different stack sizes and go all-in, the main pot is
    capped at the amount everyone can match; extra chips form one or more side pots. Each layer is evaluated
    separately and only players who contributed to that layer can win it. Folded players' chips stay in the pot
    but they cannot win any layer. If nobody matches part of a bet, that uncalled excess is returned. Identical
    best hands split the relevant pot. An odd chip goes to the first tied winner clockwise from the dealer button.</p>
    <h3>7. Timeouts &amp; disconnects</h3>
    <p>If a turn timer is enabled, the server automatically checks when possible and folds otherwise. A player who
    stops polling is marked disconnected and auto-checked/folded so the hand never freezes. Refreshing the page
    reconnects to the same seat through the saved table token. Sitting out takes effect on the next hand.</p>
    <h3>8. Table settings &amp; fair play</h3>
    <p>The host can change the table name, starting chips, blinds, minimum/maximum players, turn timer, late joining,
    spectators and privacy between hands. Demo mode enables undo and deck peek; normal tables never expose undealt
    or private cards. The deck is shuffled with the operating system's cryptographically secure random source, every
    card is unique, and the server validates every action. All player chip balances are server-side and the total
    chip count is checked after every hand.</p>
    <h3>Where the Stack lives</h3>
    <p>The deck is a stack (deal = pop), the burn pile is a stack, every action is pushed with an undo snapshot,
    completed hands are pushed onto a hand-history stack, and side-pot layers are pushed onto a pot stack and
    resolved top-down. Open the Stack Visualizer to watch the operations live.</p>
  </div>`;
}

function historyCardText(card) {
  const red = /[\u2665\u2666]/.test(card);
  return `<span class="board-chip${red ? " red" : ""}">${esc(card)}</span>`;
}

export function historyHTML(state) {
  const history = state?.hand_history || [];
  if (!history.length) {
    return `<div class="history-empty">No completed hands yet. The Stack is waiting for its first push.</div>`;
  }
  return `<div class="history-list">${history.map((hand) => {
    const winners = (hand.winners || []).map((winner) =>
      `${winner.name} (${formatChips(winner.amount)})`).join(", ");
    const reason = hand.reason === "fold" ? "Everyone folded" : (hand.hand_name || "Showdown");
    const time = hand.at ? new Date(hand.at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
    return `
      <div class="history-row">
        <span class="h-no">#${hand.hand_no}</span>
        <div class="h-main">
          <div class="h-title">${esc(winners)}</div>
          <div class="h-sub">${esc(reason)}${time ? ` · ${esc(time)}` : ""}${hand.board?.length ? ` · ${hand.board.map(esc).join(" ")}` : ""}</div>
        </div>
        <span class="h-amount">${formatChips(hand.amount)}</span>
      </div>`;
  }).join("")}</div>
  <div class="cheat-note">Newest hand first — the hand-history Stack popped top-first for this list.</div>`;
}

export function settingsHTML(state) {
  const table = state?.table || {};
  const maxSeats = Math.min(6, Number(table.max_players) || 6);
  const seatsOptions = [2, 3, 4, 5, 6].map((n) =>
    `<option value="${n}"${n === maxSeats ? " selected" : ""}>${n} players</option>`).join("");
  return `
  <form id="settingsForm" class="settings-form">
    <div class="settings-grid">
      <label class="field"><span>Table name</span><input name="name" maxlength="40" value="${esc(table.name || "Royal Table")}" /></label>
      <label class="field"><span>Starting chips (new players)</span><input name="starting_chips" type="number" min="100" max="1000000" step="100" value="${Number(table.starting_chips) || 1000}" /></label>
      <label class="field"><span>Small blind</span><input name="small_blind" type="number" min="1" max="100000" value="${Number(table.small_blind) || 5}" /></label>
      <label class="field"><span>Big blind</span><input name="big_blind" type="number" min="2" max="200000" value="${Number(table.big_blind) || 10}" /></label>
      <label class="field"><span>Turn timer (0 = off)</span><input name="turn_seconds" type="number" min="0" max="300" value="${Number(table.turn_seconds) || 0}" /></label>
      <label class="field"><span>Minimum players</span><input name="min_players" type="number" min="2" max="10" value="${Number(table.min_players) || 2}" /></label>
      <label class="field"><span>Maximum seats</span><select name="max_players">${seatsOptions}</select></label>
    </div>
    <div class="settings-checks">
      <label class="check"><input type="checkbox" name="late_join"${table.late_join ? " checked" : ""} /><span>Late joining</span></label>
      <label class="check"><input type="checkbox" name="spectators"${table.spectators ? " checked" : ""} /><span>Allow spectators</span></label>
      <label class="check"><input type="checkbox" name="private"${table.private ? " checked" : ""} /><span>Private table</span></label>
      <label class="check"><input type="checkbox" name="demo_mode"${table.demo_mode ? " checked" : ""} /><span>Demo mode (undo + peek)</span></label>
    </div>
    <div class="settings-note">
      Changes apply between hands. Starting chips only affects players who join after saving; blinds and
      the turn timer take effect on the next deal. Demo mode is always on for hot-seat practice.
    </div>
    ${["preflop", "flop", "turn", "river"].includes(state?.phase) ? '<div class="settings-note">A hand is in progress — finish it before saving.</div>' : ""}
    <div class="settings-actions">
      <button type="button" class="btn btn-outline" id="settingsCancel">Cancel</button>
      <button type="submit" class="btn btn-gold" ${["preflop", "flop", "turn", "river"].includes(state?.phase) ? "disabled" : ""}>Save settings</button>
    </div>
  </form>`;
}

export function inviteHTML(state) {
  const code = state?.room?.code || state?.invite_code || "";
  const link = `${window.location.origin}${window.location.pathname}?room=${encodeURIComponent(code)}`;
  return `
    <p>Share this five-letter code with friends on the same Wi-Fi. Each player opens Kashe Royale on their
    own device, joins with the code, and sees only their own hole cards.</p>
    <div class="invite-line"><span>CODE</span><code id="inviteCodeValue">${esc(code)}</code></div>
    <div class="invite-line"><span>LINK</span><code id="inviteLinkValue">${esc(link)}</code></div>
    <div class="settings-actions" style="justify-content:flex-start;margin-top:16px">
      <button class="btn btn-gold" id="copyCodeBtn" type="button">Copy code</button>
      <button class="btn btn-outline" id="copyLinkBtn" type="button">Copy invite link</button>
    </div>
    <div class="cheat-note">Second device on the same Wi-Fi: use the Network URL printed by <code>python run.py</code>
    and make sure the firewall allows Python. The host starts the game once both seats are filled.</div>`;
}

export function practiceHTML() {
  return `
    <form id="practiceForm" class="settings-form">
      <p>One screen, all cards visible, undo enabled. Perfect for demonstrating the Stack to a class.</p>
      <div class="settings-grid">
        <label class="field"><span>Hot-seat players</span>
          <select name="players">
            <option value="2">2 players</option>
            <option value="3" selected>3 players</option>
            <option value="4">4 players</option>
            <option value="5">5 players</option>
            <option value="6">6 players</option>
          </select>
        </label>
        <label class="field"><span>Starting chips</span>
          <input name="starting_chips" type="number" min="100" max="1000000" step="100" value="1000" />
        </label>
      </div>
      <div class="settings-note">Every seat is controlled from this one device. Use Undo · pop() to rewind decisions
      and Peek deck to show the top of the deck stack.</div>
      <div class="settings-actions">
        <button type="button" class="btn btn-outline" id="practiceCancel">Cancel</button>
        <button type="submit" class="btn btn-gold">Deal the practice hand</button>
      </div>
    </form>`;
}
