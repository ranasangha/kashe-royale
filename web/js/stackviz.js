/* ============================================================
   Stack Visualizer: Deck, Burn, Action, Pot and Hand-history stacks.
   Every event arrives from the server; new push/pop operations animate.
   ============================================================ */

const OP_NAMES = {
  push: "push()",
  pop: "pop()",
  peek: "peek()",
  reset: "reset()",
  build: "build()",
};

const STACK_NAMES = {
  deck: "deck",
  burn: "burn",
  action: "action",
  pot: "pot",
  history: "history",
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export class StackVisualizer {
  constructor(root, { onToggle } = {}) {
    this.root = root;
    this.onToggle = onToggle || (() => {});
    this.open = false;
    this.seen = new Set();
    this.feedItems = [];
    this.initialized = false;
    this.last = {
      deck: -1,
      burn: -1,
      action: "",
      pots: "",
      history: -1,
    };
    this.dom = {
      deckSize: document.getElementById("vizDeckSize"),
      burnSize: document.getElementById("vizBurnSize"),
      actionSize: document.getElementById("vizActionSize"),
      potSize: document.getElementById("vizPotSize"),
      historySize: document.getElementById("vizHistorySize"),
      deckStack: document.getElementById("vizDeckStack"),
      burnStack: document.getElementById("vizBurnStack"),
      actionStack: document.getElementById("vizActionStack"),
      potStack: document.getElementById("vizPotStack"),
      feed: document.getElementById("vizFeed"),
      scrim: document.getElementById("vizScrim"),
      button: document.getElementById("stackVizBtn"),
      close: document.getElementById("stackVizClose"),
    };
    this.bind();
  }

  bind() {
    this.dom.button?.addEventListener("click", () => this.toggle());
    this.dom.close?.addEventListener("click", () => this.setOpen(false));
    this.dom.scrim?.addEventListener("click", () => this.setOpen(false));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && this.open) this.setOpen(false);
    });
  }

  setOpen(value) {
    this.open = Boolean(value);
    this.root.classList.toggle("open", this.open);
    this.root.setAttribute("aria-hidden", this.open ? "false" : "true");
    if (this.dom.scrim) this.dom.scrim.hidden = !this.open;
    if (this.dom.button) this.dom.button.setAttribute("aria-pressed", this.open ? "true" : "false");
    this.onToggle(this.open);
    if (this.open) this.dom.scrim?.removeAttribute("hidden");
  }

  toggle() {
    this.setOpen(!this.open);
  }

  close() {
    this.setOpen(false);
  }

  reset() {
    this.seen = new Set();
    this.feedItems = [];
    this.initialized = false;
    this.last = { deck: -1, burn: -1, action: "", pots: "", history: -1 };
    if (this.dom.feed) this.dom.feed.innerHTML = "";
    if (this.dom.actionStack) this.dom.actionStack.innerHTML = "";
    if (this.dom.potStack) this.dom.potStack.innerHTML = "";
    if (this.dom.deckStack) this.dom.deckStack.innerHTML = "";
    if (this.dom.burnStack) this.dom.burnStack.innerHTML = "";
  }

  buildStack(container, count, { max = 11, burn = false } = {}) {
    if (!container) return;
    container.innerHTML = "";
    if (count <= 0) {
      container.appendChild(el("div", "viz-empty", burn ? "nothing burned yet" : "empty"));
      return;
    }
    const layers = Math.max(1, Math.min(max, Math.ceil(count / 5)));
    for (let index = 0; index < layers; index += 1) {
      const back = el("div", "viz-back" + (index === layers - 1 ? " top" : ""));
      back.style.setProperty("--stack-y", `${-index * (burn ? 3 : 4)}px`);
      back.style.zIndex = String(index);
      container.appendChild(back);
    }
  }

  render(state) {
    if (!state || !state.viz) return;
    const viz = state.viz;
    const deckCount = viz.deck ? viz.deck.size : 0;
    const burnCount = viz.burn ? viz.burn.size : 0;
    if (this.dom.deckSize) this.dom.deckSize.textContent = deckCount;
    if (this.dom.burnSize) this.dom.burnSize.textContent = burnCount;
    if (this.dom.actionSize) this.dom.actionSize.textContent = viz.action ? viz.action.size : 0;
    if (this.dom.historySize) this.dom.historySize.textContent = viz.history ? viz.history.size : 0;

    if (this.last.deck !== deckCount) {
      this.buildStack(this.dom.deckStack, deckCount);
      this.annotateTop(this.dom.deckStack, viz.deck);
      this.last.deck = deckCount;
    }
    if (this.last.burn !== burnCount) {
      this.buildStack(this.dom.burnStack, burnCount, { max: 6, burn: true });
      this.annotateTop(this.dom.burnStack, viz.burn);
      this.last.burn = burnCount;
    }

    const actions = state.action_log || [];
    const signature = `${viz.action ? viz.action.size : 0}:${actions[0]?.seq || 0}`;
    if (signature !== this.last.action) {
      this.renderActions(actions);
      this.last.action = signature;
    }

    const layers = (state.pot?.resolved && state.pot.resolved.length)
      ? state.pot.resolved
      : (state.pot?.layers_top_first || []);
    const potSignature = layers.map((layer) => `${layer.label}:${layer.amount}:${layer.eligible?.length || 0}`).join("|");
    if (potSignature !== this.last.pots) {
      this.renderPots(layers);
      this.last.pots = potSignature;
    }

    const events = viz.events || [];
    let fresh;
    if (!this.initialized) {
      this.initialized = true;
      events.forEach((event) => this.seen.add(event.id));
      fresh = events.slice(-6);
    } else {
      fresh = events.filter((event) => !this.seen.has(event.id));
      fresh.forEach((event) => this.seen.add(event.id));
    }
    if (this.seen.size > 300) {
      const ids = Array.from(this.seen);
      this.seen = new Set(ids.slice(ids.length - 150));
    }
    if (fresh.length) this.addFeed(fresh);
    if ((viz.history?.size ?? 0) !== this.last.history) {
      this.last.history = viz.history?.size ?? 0;
    }
  }

  annotateTop(container, stack) {
    if (!container) return;
    const existing = container.parentElement?.querySelector(".viz-top-label");
    if (existing) existing.remove();
    if (!stack || !stack.top) return;
    const top = stack.top;
    const label = top.label || (top.rank_label && top.symbol ? `${top.rank_label}${top.symbol}` : null);
    if (!label) return;
    const node = el("div", "viz-top-label", `top \u2192 ${label}`);
    container.parentElement?.appendChild(node);
  }

  renderActions(actions) {
    if (!this.dom.actionStack) return;
    this.dom.actionStack.innerHTML = "";
    if (!actions.length) {
      this.dom.actionStack.appendChild(el("div", "viz-empty", "no actions this hand"));
      return;
    }
    actions.slice(0, 9).forEach((action, index) => {
      const row = el("div", "viz-act" + (index === 0 ? " top" : ""));
      row.appendChild(el("span", "va-kind", action.kind || "event"));
      row.appendChild(el("span", "va-label", action.label || ""));
      this.dom.actionStack.appendChild(row);
    });
  }

  renderPots(layers) {
    if (!this.dom.potStack) return;
    this.dom.potStack.innerHTML = "";
    if (this.dom.potSize) this.dom.potSize.textContent = layers.length;
    if (!layers.length) {
      this.dom.potStack.appendChild(el("div", "viz-empty", "no pot layers yet"));
      return;
    }
    layers.forEach((layer, index) => {
      const row = el("div", "viz-pot-layer");
      const left = el("span", "", index === 0 ? `${layer.label} \u00b7 top` : layer.label);
      const right = el("span", "pl-amount", `${layer.amount}`);
      row.appendChild(left);
      row.appendChild(right);
      this.dom.potStack.appendChild(row);
    });
  }

  addFeed(events) {
    if (!this.dom.feed) return;
    const ordered = [...events];
    ordered.forEach((event) => {
      const op = OP_NAMES[event.op] || `${event.op}()`;
      const stack = STACK_NAMES[event.stack] || event.stack;
      const row = el("div", `viz-feed-item ${event.op}`);
      row.appendChild(el("span", "op", `${stack}.${op}`));
      row.appendChild(el("span", "arrow", "\u2192"));
      const detail = event.hidden
        ? "back"
        : (event.detail || event.label || "");
      row.appendChild(el("span", "detail", detail));
      this.dom.feed.prepend(row);
    });
    while (this.dom.feed.children.length > 16) {
      this.dom.feed.lastElementChild.remove();
    }
  }
}
