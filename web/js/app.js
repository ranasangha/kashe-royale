/* ============================================================
   PokerStack application controller
   ============================================================ */

import {
  api,
  ApiError,
  clearSession,
  copyText,
  inviteLink,
  loadSession,
  removeRoomToken,
  roomFromUrl,
  saveSession,
  tokenForRoom,
} from "./api.js";
import { renderHeroCards } from "./cards.js";
import {
  Renderer,
  cheatSheetHTML,
  esc,
  formatChips,
  historyHTML,
  inviteHTML,
  practiceHTML,
  rulesHTML,
  settingsHTML,
} from "./render.js";
import { PokerSound } from "./sound.js";
import { StackVisualizer } from "./stackviz.js";

const sound = new PokerSound();
const renderer = new Renderer({
  sound,
  onAction: doAction,
  onCommand: handleCommand,
});
const stackViz = new StackVisualizer(document.getElementById("stackViz"), {
  onToggle: (open) => {
    if (open) stackViz.render(app.state);
  },
});

const app = {
  view: "lobby",
  code: null,
  token: null,
  practice: false,
  state: null,
  lastVersion: null,
  pollTimer: null,
  pollBusy: false,
  pollFailures: 0,
  busy: false,
  leaving: false,
  lobbyBusy: false,
  tablesBusy: false,
  connectionWarned: false,
};

const dom = {
  lobbyView: document.getElementById("lobbyView"),
  gameView: document.getElementById("gameView"),
  createForm: document.getElementById("createForm"),
  joinForm: document.getElementById("joinForm"),
  joinCode: document.getElementById("joinCode"),
  createPanel: document.getElementById("createPanel"),
  joinPanel: document.querySelector(".join-panel"),
  practiceBtn: document.getElementById("practiceBtn"),
  heroPracticeBtn: document.getElementById("heroPracticeBtn"),
  openTables: document.getElementById("openTables"),
  refreshTables: document.getElementById("refreshTables"),
  modalRoot: document.getElementById("modalRoot"),
  modalKicker: document.getElementById("modalKicker"),
  modalTitle: document.getElementById("modalTitle"),
  modalBody: document.getElementById("modalBody"),
  modalClose: document.getElementById("modalClose"),
  modalBackdrop: document.getElementById("modalBackdrop"),
  toasts: document.getElementById("toasts"),
  rankingsBtn: document.getElementById("rankingsBtn"),
  historyBtn: document.getElementById("historyBtn"),
  rulesBtn: document.getElementById("rulesBtn"),
  muteBtn: document.getElementById("muteBtn"),
  muteIcon: document.getElementById("muteIcon"),
  muteLabel: document.getElementById("muteLabel"),
  musicBtn: document.getElementById("musicBtn"),
  musicIcon: document.getElementById("musicIcon"),
  musicLabel: document.getElementById("musicLabel"),
  leaveBtn: document.getElementById("leaveBtn"),
};

/* ------------------------------------------------------------------ toast */
function toast(message, type = "info", duration = 3800) {
  if (!dom.toasts) return;
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  dom.toasts.appendChild(node);
  while (dom.toasts.children.length > 4) dom.toasts.firstElementChild?.remove();
  window.setTimeout(() => {
    node.classList.add("leaving");
    window.setTimeout(() => node.remove(), 280);
  }, duration);
}

function reportError(error) {
  const message = error instanceof ApiError
    ? error.message
    : (error?.message || "Something went wrong.");
  toast(message, "error");
  sound.error();
  if (error instanceof ApiError && (error.status === 401 || error.status === 404) && app.view === "game") {
    handleLostSeat(error);
  }
}

/* ------------------------------------------------------------------ lobby */
function showLobby({ prefillCode = null, message = null } = {}) {
  stopPolling();
  const code = prefillCode || app.code || "";
  app.view = "lobby";
  app.code = null;
  app.token = null;
  app.practice = false;
  app.state = null;
  app.lastVersion = null;
  app.busy = false;
  renderer.resetForGame();
  stackViz.reset();
  stackViz.close();
  closeModal();
  if (dom.lobbyView) dom.lobbyView.hidden = false;
  if (dom.gameView) dom.gameView.hidden = true;
  if (code && dom.joinCode) dom.joinCode.value = code;
  document.title = "Kashe Royale — Royal Texas Hold'em";
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (message) toast(message, "info");
  refreshOpenTables();
}

async function attemptResume(candidate) {
  try {
    const state = await api.state(candidate.code, candidate.token);
    enterGame(state, { code: candidate.code, token: candidate.token });
    return true;
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
      removeRoomToken(candidate.code);
      clearSession();
      showLobby({ prefillCode: candidate.code });
      toast(
        error.status === 404
          ? "That table is no longer open. Create a new one or join another code."
          : "Your seat expired. Join the table again.",
        "error",
      );
    } else {
      showLobby({ prefillCode: candidate.code });
      toast("Cannot reach the game server. Is python run.py still running?", "error");
    }
    return false;
  }
}

function enterGame(state, { code, token }) {
  if (!state || !code || !token) return;
  stopPolling();
  app.view = "game";
  app.code = code;
  app.token = token;
  app.practice = Boolean(state.practice);
  app.state = state;
  app.lastVersion = state.version;
  app.pollFailures = 0;
  app.connectionWarned = false;
  app.busy = false;
  app.leaving = false;
  saveSession({
    code,
    token,
    practice: Boolean(state.practice),
    name: state.room?.session_name || state.viewer?.name || "",
  });
  closeModal();
  renderer.resetForGame();
  stackViz.reset();
  if (dom.lobbyView) dom.lobbyView.hidden = true;
  if (dom.gameView) dom.gameView.hidden = false;
  renderer.render(state);
  stackViz.render(state);
  updateMuteUI();
  setRoomUrl(code);
  window.scrollTo({ top: 0, behavior: "auto" });
  startPolling();
}

function setRoomUrl(code) {
  try {
    const url = `${window.location.pathname}?room=${encodeURIComponent(code)}`;
    window.history.replaceState({ room: code }, "", url);
  } catch (error) {
    /* ignore */
  }
}

function clearRoomUrl() {
  try {
    window.history.replaceState({}, "", window.location.pathname);
  } catch (error) {
    /* ignore */
  }
}

function bindLobby() {
  dom.createForm?.addEventListener("submit", onCreateTable);
  dom.joinForm?.addEventListener("submit", onJoinTable);
  dom.practiceBtn?.addEventListener("click", openPracticeModal);
  dom.heroPracticeBtn?.addEventListener("click", openPracticeModal);
  dom.refreshTables?.addEventListener("click", () => refreshOpenTables(true));
  document.querySelectorAll("[data-scroll-to]").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById(button.dataset.scrollTo)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
  dom.openTables?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-join]");
    if (!button) return;
    const code = button.dataset.join;
    const storedToken = tokenForRoom(code);
    if (storedToken) {
      attemptResume({ code, token: storedToken });
      return;
    }
    if (dom.joinCode) {
      dom.joinCode.value = code;
      const nameField = dom.joinForm?.elements?.namedItem("name");
      dom.joinPanel?.scrollIntoView({ behavior: "smooth", block: "center" });
      window.setTimeout(() => nameField?.focus(), 450);
    }
  });
}

async function onCreateTable(event) {
  event.preventDefault();
  if (app.lobbyBusy) return;
  const form = dom.createForm;
  const fd = new FormData(form);
  const starting = Number(fd.get("starting_chips")) || 1000;
  const small = Number(fd.get("small_blind")) || 5;
  const big = Number(fd.get("big_blind")) || 10;
  if (big < small) {
    toast("The big blind must be at least the small blind.", "error");
    return;
  }
  if (starting < big * 2) {
    toast("Give every player at least two big blinds to play with.", "error");
    return;
  }
  const payload = {
    name: String(fd.get("name") || "").trim() || "Host",
    table_name: String(fd.get("table_name") || "").trim() || "Royal Table",
    max_players: Number(fd.get("max_players")) || 2,
    min_players: 2,
    starting_chips: starting,
    small_blind: small,
    big_blind: big,
    turn_seconds: Number(fd.get("turn_seconds")) || 0,
    late_join: fd.has("late_join"),
    spectators: fd.has("spectators"),
    private: fd.has("private"),
    demo_mode: fd.has("demo_mode"),
  };
  setFormBusy(form, true, "Opening…");
  app.lobbyBusy = true;
  try {
    const result = await api.createTable(payload);
    toast(`Table opened — room ${result.code}`, "success");
    enterGame(result.state, { code: result.code, token: result.token });
  } catch (error) {
    reportError(error);
  } finally {
    app.lobbyBusy = false;
    setFormBusy(form, false);
  }
}

async function onJoinTable(event) {
  event.preventDefault();
  if (app.lobbyBusy) return;
  const form = dom.joinForm;
  const fd = new FormData(form);
  const code = String(fd.get("code") || "").trim().toUpperCase();
  const name = String(fd.get("name") || "").trim();
  if (!code) {
    toast("Enter the five-letter room code.", "error");
    return;
  }
  if (!name) {
    toast("Enter a name so the table knows who you are.", "error");
    return;
  }
  if (dom.joinCode) dom.joinCode.value = code;
  setFormBusy(form, true, "Joining…");
  app.lobbyBusy = true;
  try {
    const result = await api.joinTable({
      code,
      name,
      spectator: fd.has("spectator"),
    });
    toast(fd.has("spectator") ? "Watching the table." : "Seat taken. Good luck.", "success");
    enterGame(result.state, { code: result.code, token: result.token });
  } catch (error) {
    reportError(error);
  } finally {
    app.lobbyBusy = false;
    setFormBusy(form, false);
  }
}

function setFormBusy(form, busy, label) {
  if (!form) return;
  const button = form.querySelector('button[type="submit"]');
  if (!button) return;
  if (busy) {
    button.dataset.original = button.innerHTML;
    button.disabled = true;
    button.textContent = label || "Working…";
  } else {
    button.disabled = false;
    if (button.dataset.original) button.innerHTML = button.dataset.original;
  }
}

async function refreshOpenTables(showErrors = false) {
  if (app.view !== "lobby" || app.tablesBusy) return;
  app.tablesBusy = true;
  try {
    const data = await api.openTables();
    renderOpenTables(data.tables || []);
  } catch (error) {
    if (showErrors) reportError(error);
    else if (dom.openTables) {
      dom.openTables.innerHTML = `<p class="empty-note">Cannot reach the table server. Start it with <strong>python run.py</strong>.</p>`;
    }
  } finally {
    app.tablesBusy = false;
  }
}

function renderOpenTables(tables) {
  if (!dom.openTables) return;
  if (!tables.length) {
    dom.openTables.innerHTML = `<p class="empty-note">No open tables yet. Create one, or ask the host for their room code.</p>`;
    return;
  }
  dom.openTables.innerHTML = tables.map((table) => {
    const stored = tokenForRoom(table.code);
    const status = table.started ? "In progress" : "Waiting";
    return `
      <article class="table-card">
        <div>
          <h3>${esc(table.name)}</h3>
          <p><span class="table-code">${esc(table.code)}</span> · ${table.players}/${table.max_players} seats · blinds ${formatChips(table.blinds[0])}/${formatChips(table.blinds[1])} · ${esc(status)}</p>
        </div>
        <div class="tc-side">
          <button class="btn btn-tiny ${stored ? "btn-gold" : "btn-ghost"}" data-join="${esc(table.code)}">${stored ? "Resume" : "Join"}</button>
        </div>
      </article>`;
  }).join("");
}

/* ------------------------------------------------------------------ polling */
function startPolling() {
  stopPolling();
  if (app.view !== "game") return;
  pollOnce();
  app.pollTimer = window.setInterval(pollOnce, 850);
}

function stopPolling() {
  if (app.pollTimer) {
    window.clearInterval(app.pollTimer);
    app.pollTimer = null;
  }
}

async function pollOnce() {
  if (app.view !== "game" || !app.code || !app.token || app.pollBusy) return;
  app.pollBusy = true;
  try {
    const state = await api.state(app.code, app.token);
    app.pollFailures = 0;
    app.connectionWarned = false;
    applyState(state);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
      handleLostSeat(error);
    } else {
      app.pollFailures += 1;
      if (app.pollFailures >= 2 && !app.connectionWarned) {
        app.connectionWarned = true;
        toast("Connection lost — retrying…", "error");
      }
    }
  } finally {
    app.pollBusy = false;
  }
}

function applyState(state, { force = false } = {}) {
  if (!state) return;
  if (app.view !== "game") return;
  if (!force && app.lastVersion !== null && state.version < app.lastVersion) return;
  app.state = state;
  if (force || state.version !== app.lastVersion) {
    app.lastVersion = state.version;
    renderer.render(state);
    stackViz.render(state);
  }
}

function handleLostSeat(error) {
  if (app.view !== "game") return;
  const code = app.code;
  stopPolling();
  clearSession();
  removeRoomToken(code);
  showLobby({ prefillCode: code });
  toast(
    error?.status === 404
      ? "The table closed or the server restarted."
      : "Your seat is no longer valid. Rejoin the table.",
    "error",
  );
}

/* ------------------------------------------------------------------ actions */
async function doAction(action, amount = null) {
  if (app.busy || app.view !== "game" || !app.state) return;
  if (!renderer.legal?.is_turn) {
    toast("It is not your turn yet.", "info");
    return;
  }
  app.busy = true;
  renderer.setBusy(true);
  const seat = app.state.practice ? app.state.current?.actor_seat : null;
  try {
    const state = await api.act(app.code, app.token, action, amount, seat);
    applyState(state, { force: true });
  } catch (error) {
    reportError(error);
    pollOnce();
  } finally {
    app.busy = false;
    renderer.setBusy(false);
  }
}

async function withGameRequest(task, onSuccess) {
  if (app.busy || app.view !== "game") return;
  app.busy = true;
  renderer.setBusy(true);
  try {
    const result = await task();
    const state = result?.state || result;
    applyState(state, { force: true });
    if (onSuccess) onSuccess(result);
  } catch (error) {
    reportError(error);
  } finally {
    app.busy = false;
    renderer.setBusy(false);
  }
}

function handleCommand(command) {
  if (!app.state) return;
  switch (command) {
    case "start":
      if (!app.state.can_start) {
        toast("Need enough seated players with chips to start.", "error");
        return;
      }
      withGameRequest(
        () => api.start(app.code, app.token),
        () => {
          sound.chip();
          toast("Cards are in the air.", "success");
        },
      );
      break;
    case "next":
      if (!app.state.can_next) {
        toast("The next hand needs at least two players with chips.", "error");
        return;
      }
      withGameRequest(
        () => api.nextHand(app.code, app.token),
        () => toast("New hand dealt — the button moved.", "success"),
      );
      break;
    case "sit":
      withGameRequest(
        () => api.sit(app.code, app.token, !app.state.viewer?.sitting_out),
        () => {
          const out = app.state.viewer?.sitting_out;
          toast(out ? "You will sit out from the next hand." : "You are back in the next hand.", "info");
        },
      );
      break;
    case "rebuy":
      withGameRequest(
        () => api.rebuy(app.code, app.token),
        () => toast("Fresh stack added.", "success"),
      );
      break;
    case "undo":
      withGameRequest(
        () => api.undo(app.code, app.token),
        () => {
          sound.chip();
          toast("Undo: Stack.pop() restored the previous state.", "success");
        },
      );
      break;
    case "peek":
      withGameRequest(
        () => api.peek(app.code, app.token),
        (result) => {
          if (result?.card) toast(`Top of the deck stack: ${result.card.label}`, "success", 6000);
        },
      );
      break;
    case "settings":
      openSettings();
      break;
    case "invite":
      openInvite();
      break;
    default:
      break;
  }
}

/* ------------------------------------------------------------------ modals */
function openModal({ kicker = "Kashe Royale", title, html, after = null }) {
  if (!dom.modalRoot) return;
  dom.modalKicker.textContent = kicker;
  dom.modalTitle.textContent = title;
  dom.modalBody.innerHTML = html;
  dom.modalRoot.hidden = false;
  document.body.style.overflow = "hidden";
  window.setTimeout(() => {
    const focusable = dom.modalBody.querySelector("input, select, button");
    (focusable || dom.modalClose)?.focus?.();
  }, 50);
  if (after) after(dom.modalBody);
}

function closeModal() {
  if (!dom.modalRoot) return;
  dom.modalRoot.hidden = true;
  dom.modalBody.innerHTML = "";
  document.body.style.overflow = "";
}

function bindModalBase() {
  dom.modalClose?.addEventListener("click", closeModal);
  dom.modalBackdrop?.addEventListener("click", closeModal);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !dom.modalRoot.hidden) {
      closeModal();
    }
  });
}

function openCheatSheet() {
  openModal({
    kicker: "Reference",
    title: "Hand rankings",
    html: cheatSheetHTML(),
  });
}

function openRules() {
  openModal({
    kicker: "How to play",
    title: "Kashe Royale rules",
    html: rulesHTML(),
  });
}

function openHistory() {
  if (!app.state) {
    toast("Join a table to see its hand history.", "info");
    return;
  }
  openModal({
    kicker: "Hand history · Stack",
    title: "Last hands first",
    html: historyHTML(app.state),
  });
}

function openSettings() {
  if (!app.state) return;
  if (!app.state.room?.is_host) {
    toast("Only the host can change table settings.", "error");
    return;
  }
  openModal({
    kicker: "Host controls",
    title: "Table settings",
    html: settingsHTML(app.state),
    after: (body) => {
      const form = body.querySelector("#settingsForm");
      body.querySelector("#settingsCancel")?.addEventListener("click", closeModal);
      form?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const fd = new FormData(form);
        const saveButton = form.querySelector('button[type="submit"]');
        const payload = {
          name: String(fd.get("name") || "").trim() || "Royal Table",
          starting_chips: Number(fd.get("starting_chips")) || 1000,
          small_blind: Number(fd.get("small_blind")) || 5,
          big_blind: Number(fd.get("big_blind")) || 10,
          turn_seconds: Number(fd.get("turn_seconds")) || 0,
          min_players: Number(fd.get("min_players")) || 2,
          max_players: Number(fd.get("max_players")) || 6,
          late_join: fd.has("late_join"),
          spectators: fd.has("spectators"),
          private: fd.has("private"),
          demo_mode: fd.has("demo_mode"),
        };
        if (payload.big_blind < payload.small_blind) {
          toast("Big blind must be at least the small blind.", "error");
          return;
        }
        if (saveButton) {
          saveButton.disabled = true;
          saveButton.textContent = "Saving…";
        }
        try {
          const state = await api.updateSettings(app.code, app.token, payload);
          closeModal();
          applyState(state, { force: true });
          toast("Table settings saved.", "success");
        } catch (error) {
          reportError(error);
          if (saveButton) {
            saveButton.disabled = false;
            saveButton.textContent = "Save settings";
          }
        }
      });
    },
  });
}

function openInvite() {
  if (!app.state) return;
  if (app.state.practice) {
    toast("Practice tables are single-device — share a normal table instead.", "info");
    return;
  }
  openModal({
    kicker: "Private table",
    title: "Invite players",
    html: inviteHTML(app.state),
    after: (body) => {
      body.querySelector("#copyCodeBtn")?.addEventListener("click", async () => {
        const code = app.state?.room?.code || app.state?.invite_code || "";
        const ok = await copyText(code);
        toast(ok ? `Room code ${code} copied.` : "Copy failed — select the code manually.", ok ? "success" : "error");
      });
      body.querySelector("#copyLinkBtn")?.addEventListener("click", async () => {
        const code = app.state?.room?.code || app.state?.invite_code || "";
        const ok = await copyText(inviteLink(code));
        toast(ok ? "Invite link copied." : "Copy failed — select the link manually.", ok ? "success" : "error");
      });
    },
  });
}

function openPracticeModal() {
  openModal({
    kicker: "Demo mode",
    title: "Hot-seat practice",
    html: practiceHTML(),
    after: (body) => {
      const form = body.querySelector("#practiceForm");
      body.querySelector("#practiceCancel")?.addEventListener("click", closeModal);
      form?.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (app.lobbyBusy) return;
        const fd = new FormData(form);
        const submit = form.querySelector('button[type="submit"]');
        app.lobbyBusy = true;
        if (submit) {
          submit.disabled = true;
          submit.textContent = "Dealing…";
        }
        try {
          const result = await api.createPractice({
            name: "Practice Table",
            players: Number(fd.get("players")) || 3,
            starting_chips: Number(fd.get("starting_chips")) || 1000,
          });
          closeModal();
          toast("Practice table ready — all cards visible, undo enabled.", "success");
          enterGame(result.state, { code: result.code, token: result.token });
        } catch (error) {
          reportError(error);
          if (submit) {
            submit.disabled = false;
            submit.textContent = "Deal the practice hand";
          }
        } finally {
          app.lobbyBusy = false;
        }
      });
    },
  });
}

function confirmLeave() {
  if (!app.state || app.leaving) return;
  const practicing = Boolean(app.state.practice);
  openModal({
    kicker: practicing ? "Practice" : "Leave table",
    title: practicing ? "End the practice session?" : "Leave the table?",
    html: `
      <p class="confirm-copy">
        ${practicing
          ? "This closes the hot-seat practice table. All virtual chips go back in the case."
          : "If a hand is running you will be folded, and your remaining chips leave the table. You can rejoin with the room code if the host still has the table open."}
      </p>
      <div class="confirm-actions">
        <button class="btn btn-outline" id="leaveCancel" type="button">Stay</button>
        <button class="btn btn-gold" id="leaveConfirm" type="button">${practicing ? "End practice" : "Leave table"}</button>
      </div>`,
    after: (body) => {
      body.querySelector("#leaveCancel")?.addEventListener("click", closeModal);
      body.querySelector("#leaveConfirm")?.addEventListener("click", async () => {
        const button = body.querySelector("#leaveConfirm");
        if (button) {
          button.disabled = true;
          button.textContent = "Leaving…";
        }
        app.leaving = true;
        try {
          await api.leave(app.code, app.token);
        } catch (error) {
          if (!(error instanceof ApiError) || (error.status !== 401 && error.status !== 404)) {
            reportError(error);
            app.leaving = false;
            if (button) {
              button.disabled = false;
              button.textContent = practicing ? "End practice" : "Leave table";
            }
            return;
          }
        }
        clearSession();
        removeRoomToken(app.code);
        app.leaving = false;
        closeModal();
        clearRoomUrl();
        app.code = null;
        app.token = null;
        showLobby({ message: "You left the table." });
      });
    },
  });
}

/* ------------------------------------------------------------------ header */
function bindHeader() {
  dom.rankingsBtn?.addEventListener("click", openCheatSheet);
  dom.historyBtn?.addEventListener("click", openHistory);
  dom.rulesBtn?.addEventListener("click", openRules);
  dom.leaveBtn?.addEventListener("click", confirmLeave);
  dom.muteBtn?.addEventListener("click", () => {
    const muted = sound.toggle();
    updateMuteUI();
    updateMusicUI();
    toast(muted ? "Sound muted." : "Sound on.", "info", 1600);
  });
  dom.musicBtn?.addEventListener("click", () => {
    const on = sound.toggleMusic();
    updateMusicUI();
    toast(on ? "Background music on." : "Background music off.", "info", 1600);
  });
  bindModalBase();
}

function updateMuteUI() {
  if (!dom.muteBtn) return;
  dom.muteBtn.setAttribute("aria-pressed", sound.muted ? "true" : "false");
  dom.muteBtn.title = sound.muted ? "Unmute sound" : "Mute sound";
  if (dom.muteIcon) dom.muteIcon.textContent = sound.muted ? "\u2715" : "\u266a";
  if (dom.muteLabel) dom.muteLabel.textContent = sound.muted ? "Muted" : "Sound";
}

function updateMusicUI() {
  if (!dom.musicBtn) return;
  dom.musicBtn.setAttribute("aria-pressed", sound.musicOn ? "true" : "false");
  dom.musicBtn.title = sound.musicOn ? "Turn background music off" : "Turn background music on";
  if (dom.musicIcon) dom.musicIcon.textContent = "\u266b";
  if (dom.musicLabel) dom.musicLabel.textContent = sound.musicOn ? "Music" : "Off";
}

/* ------------------------------------------------------------------ keyboard */
function bindKeyboard() {
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.repeat) return;
    if (app.view !== "game" || !app.state || app.busy) return;
    if (!dom.modalRoot.hidden) return;
    if (stackViz.open) return;
    const target = event.target;
    if (target && target.closest && target.closest("input, textarea, select, [contenteditable='true']")) return;
    const key = event.key.toLowerCase();
    const legal = renderer.legal;
    if (!legal?.is_turn) return;
    if (key === "f" && legal.fold?.allowed) {
      event.preventDefault();
      doAction("fold");
    } else if (key === "c") {
      event.preventDefault();
      if (legal.check?.allowed) doAction("check");
      else if (legal.call?.allowed) doAction("call");
    } else if (key === "r" && legal.wager?.allowed) {
      event.preventDefault();
      doAction(app.state.current?.current_bet ? "raise" : "bet", renderer.wagerAmount);
    }
  });
}

/* ------------------------------------------------------------------ boot */
function boot() {
  renderHeroCards(document.getElementById("heroCards"));
  bindLobby();
  bindHeader();
  bindKeyboard();
  updateMuteUI();
  updateMusicUI();
  document.addEventListener("pointerdown", () => sound.unlock(), { once: true });
  document.addEventListener("keydown", () => sound.unlock(), { once: true });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && app.view === "game") pollOnce();
  });
  window.setInterval(() => {
    if (app.view === "lobby" && !document.hidden) refreshOpenTables();
  }, 9000);

  const urlRoom = roomFromUrl();
  if (urlRoom && dom.joinCode) dom.joinCode.value = urlRoom;
  const session = loadSession();
  let candidate = null;

  if (urlRoom) {
    const token = tokenForRoom(urlRoom) || (session?.code === urlRoom ? session.token : null);
    if (token) candidate = { code: urlRoom, token, practice: Boolean(session?.practice) };
  } else if (session) {
    candidate = session;
  }

  if (candidate) {
    attemptResume(candidate);
  } else {
    showLobby({ prefillCode: urlRoom });
    if (urlRoom) {
      window.setTimeout(() => toast(`Room ${urlRoom} — enter your name to join.`, "info", 5000), 500);
    }
  }
}

boot();
