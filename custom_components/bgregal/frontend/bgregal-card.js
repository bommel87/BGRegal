/*
 * BGRegal – Dashboard-Kachel für ein Spiel.
 *   type: custom:bgregal-card
 *   bgg_id: 13        # optional; ohne: Spiel der Sitzung, sonst der aktuelle Vorschlag
 */
import { STRINGS, esc, fmtDate, location, playersText } from "./bgregal-common.js?v=0.2.0";

class BgRegalCard extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    this._t = STRINGS[(hass.language || "de").startsWith("de") ? "de" : "en"];
    if (first) this._connect();
  }

  getCardSize() { return 3; }

  static getStubConfig() { return {}; }

  disconnectedCallback() {
    if (this._unsub) this._unsub.then((u) => u()).catch(() => {});
    this._unsub = null;
    clearInterval(this._timer);
  }

  connectedCallback() {
    if (this._hass && !this._unsub) this._connect();
  }

  async _connect() {
    await this._load();
    this._unsub = this._hass.connection.subscribeMessage(() => this._load(), { type: "bgregal/subscribe" });
    clearInterval(this._timer);
    this._timer = setInterval(() => {
      const el = this.shadowRoot?.getElementById("elapsed");
      const s = this._data?.session;
      if (el && s?.state === "running") el.textContent = elapsed(s.started);
    }, 1000);
  }

  async _load() {
    try {
      this._data = await this._hass.callWS({ type: "bgregal/data" });
    } catch (_) {
      this._data = null;
    }
    this._render();
  }

  _game() {
    const d = this._data;
    if (!d) return null;
    const byId = (id) => d.games.find((g) => g.bgg_id === id) || null;
    if (this._config?.bgg_id) return byId(Number(this._config.bgg_id));
    if (d.session) return byId(d.session.bgg_id);
    if (d.suggestion?.game) return byId(d.suggestion.game.bgg_id);
    return null;
  }

  _render() {
    if (!this.shadowRoot || !this._t) return;
    const t = this._t, c = t.card, g = this._game(), s = this._data?.session;
    const running = s && s.state === "running";
    const mine = running && g && s.bgg_id === g.bgg_id;
    const body = !g
      ? `<div class="none">${c.none}</div><a class="open" href="/bgregal">${c.open}</a>`
      : `<div class="game">
          ${g.thumbnail ? `<img src="${esc(g.thumbnail)}" alt="">` : ""}
          <div class="info">
            <div class="name">${esc(g.name)}</div>
            <div class="facts"><span><b>${g.plays}</b> ${c.plays}</span>
              <span>${c.lastPlay}: <b>${g.last_play ? fmtDate(g.last_play) : "–"}</b></span></div>
            ${g.last_players.length ? `<div class="muted">${esc(playersText(g.last_players, this._data.me))}</div>` : ""}
            ${location(g, t) ? `<div class="muted">${esc(location(g, t))}</div>` : ""}
          </div>
        </div>
        <div class="actions">${mine
          ? `<span class="run">● ${c.running} <span id="elapsed">${elapsed(s.started)}</span></span>`
          : `<button data-id="${g.bgg_id}" ${running ? "disabled" : ""}>${c.start}</button>`}</div>`;
    this.shadowRoot.innerHTML = `<style>${CSS}</style><ha-card>${this._config?.title ? `<h1>${esc(this._config.title)}</h1>` : ""}${body}</ha-card>`;
    this.shadowRoot.querySelector("button[data-id]")?.addEventListener("click", (e) => {
      this._hass.callService("bgregal", "start_session", { bgg_id: Number(e.target.dataset.id) })
        .catch((err) => alert(err.message));
    });
  }
}

function elapsed(started) {
  const sec = Math.max(0, Math.floor((Date.now() - new Date(started)) / 1000));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

const CSS = `
  ha-card { padding: 16px; }
  h1 { font-size: 16px; font-weight: 500; margin: 0 0 12px; }
  .game { display: flex; gap: 14px; }
  img { width: 88px; height: 88px; object-fit: cover; border-radius: 10px; flex: none; }
  .name { font-size: 18px; font-weight: 500; margin-bottom: 4px; }
  .facts { display: flex; flex-wrap: wrap; gap: 12px; font-size: 14px; }
  .muted, .none { color: var(--secondary-text-color); font-size: 13px; margin-top: 2px; }
  .actions { display: flex; justify-content: flex-end; margin-top: 12px; }
  button { font: inherit; font-size: 14px; padding: 8px 16px; border-radius: 8px; border: 0; cursor: pointer;
           background: var(--primary-color); color: var(--text-primary-color, #fff); }
  button:disabled { opacity: .45; cursor: default; }
  .run { color: var(--success-color, #43a047); font-variant-numeric: tabular-nums; }
  .open { display: inline-block; margin-top: 8px; color: var(--primary-color); }
`;

customElements.define("bgregal-card", BgRegalCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "bgregal-card", name: "BGRegal", description: "Spiel mit Partien, letzter Partie und Start-Knopf" });
