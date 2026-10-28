/*
 * BGRegal – Panel in der Seitenleiste von Home Assistant.
 * Reines JavaScript ohne Build-Schritt. Daten kommen über den WebSocket-Befehl bgregal/data,
 * Änderungen laufen über die Dienste der Integration.
 */
import { STRINGS, esc, fmtDate, location, naturalCompare, playersText } from "./bgregal-common.js?v=0.6.0";

const TABS = ["shelf", "session", "suggest", "evenings", "players", "stats", "shame", "wishlist", "loans"];

class BgRegalPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "shelf";
    this._data = null;
    this._error = null;
    this._ui = {
      search: "", filter: "all", shelfEdit: null, game: null, gamePlays: null, edit: {}, lendTo: "",
      sug: { players: "", mode: "any", game_type: "any", max_playtime: "", attendees: [] },
      finish: null, qr: null, evening: null, eveningQr: null, newPlayer: "", playerEdit: {},
      order: null,
    };
    this._toast = "";
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    this._t = STRINGS[(hass.language || "de").startsWith("de") ? "de" : "en"];
    if (first) this._connect();
  }

  set narrow(value) {
    this._narrow = value;
    if (this._data) this._render();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    if (this._scan) this._closeScan();
    if (this._unsub) this._unsub.then((u) => u()).catch(() => {});
    this._unsub = null;
  }

  connectedCallback() {
    if (this._hass && !this._unsub) this._connect();
  }

  // ---- Daten -------------------------------------------------------------------
  async _connect() {
    await this._load();
    this._unsub = this._hass.connection.subscribeMessage(() => this._scheduleLoad(), { type: "bgregal/subscribe" });
    clearInterval(this._timer);
    this._timer = setInterval(() => this._tick(), 1000);
  }

  _scheduleLoad() {
    clearTimeout(this._loadTimer);
    this._loadTimer = setTimeout(() => this._load(), 150);
  }

  async _load() {
    try {
      this._data = await this._hass.callWS({ type: "bgregal/data" });
      this._error = null;
      this._games = new Map(this._data.games.map((g) => [g.bgg_id, g]));
      // Inventur: Liste aktualisieren, auch wenn der Scan per NFC-Tag aus der HA-App kam
      if (this._scan?.mode === "inventory") this._renderScan();
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._render();
  }

  async _call(service, data = {}, response = false) {
    try {
      if (response) {
        const res = await this._hass.callWS({
          type: "call_service", domain: "bgregal", service, service_data: data, return_response: true,
        });
        return res.response;
      }
      await this._hass.callService("bgregal", service, data);
      return true;
    } catch (err) {
      this._showToast(err.message || String(err));
      return null;
    }
  }

  _showToast(text) {
    this._toast = text;
    this._render();
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => { this._toast = ""; this._render(); }, 5000);
  }

  _tick() {
    const el = this.shadowRoot.getElementById("elapsed");
    const s = this._data?.session;
    if (el && s && s.state === "running") el.textContent = elapsed(s.started);
  }

  // ---- Rendern -----------------------------------------------------------------
  _render() {
    const t = this._t;
    if (!t) return;
    // Fokus und Cursor über das Neuzeichnen retten
    const active = this.shadowRoot.activeElement;
    const focusKey = active?.dataset?.k;
    const caret = active && "selectionStart" in active ? active.selectionStart : null;

    let body;
    if (this._error) body = `<div class="empty">${esc(this._error)}</div>`;
    else if (!this._data) body = `<div class="empty">${t.loading}</div>`;
    else body = this[`_view_${this._tab}`]();

    const session = this._data?.session;
    const badge = (tab) => {
      if (tab === "session" && session) return `<span class="dot ${session.state}"></span>`;
      if (tab === "loans" && this._data?.loans.length) return `<span class="count">${this._data.loans.length}</span>`;
      if (tab === "wishlist" && this._data?.new_expansions.length) return `<span class="count">${this._data.new_expansions.length}</span>`;
      return "";
    };
    // Der Scanner (Kamera) liegt außerhalb von #app, damit Neuzeichnen das Video nicht abbricht
    if (!this._app) {
      this.shadowRoot.innerHTML = `<style>${CSS}</style><div id="app"></div><div id="scan"></div>`;
      this._app = this.shadowRoot.getElementById("app");
    }
    this._app.innerHTML = `
      <header>
        ${this._narrow ? `<button class="icon menu" data-a="menu" aria-label="Menu">☰</button>` : ""}
        <h1>BGRegal</h1>
        <span class="sync muted">${this._data?.last_sync ? `${t.lastSync} ${fmtDate(this._data.last_sync, true)}` : ""}</span>
        <button class="icon" data-a="scan" title="${t.scan}" aria-label="${t.scan}">${BARCODE_ICON}</button>
        <button class="icon" data-a="sync" title="${t.syncNow}" aria-label="${t.syncNow}">⟳</button>
      </header>
      <nav>${TABS.map((tab) => `<button class="tab ${tab === this._tab ? "on" : ""}" data-a="tab" data-v="${tab}">${t.tabs[tab]}${badge(tab)}</button>`).join("")}</nav>
      <main>${body}</main>
      ${this._ui.game ? this._gameDialog() : ""}
      ${this._ui.shelfEdit ? this._shelfDialog() : ""}
      ${this._ui.qr ? this._qrDialog() : ""}
      ${this._toast ? `<div class="toast">${esc(this._toast)}</div>` : ""}`;

    if (!this._bound) {
      this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
      this.shadowRoot.addEventListener("input", (e) => this._onInput(e));
      this.shadowRoot.addEventListener("change", (e) => this._onInput(e));
      this.shadowRoot.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && e.target.dataset?.k === "scan.code") {
          // Barcode-Scanner tippen den Code und drücken Enter
          const code = e.target.value;
          e.target.value = "";
          this._onCode(code);
          return;
        }
        if (e.key !== "Escape") return;
        if (this._scan) { this._closeScan(); return; }
        if (this._ui.game || this._ui.qr || this._ui.shelfEdit) {
          this._ui.game = null; this._ui.qr = null; this._ui.shelfEdit = null; this._render();
        }
      });
      this._bound = true;
    }
    if (focusKey) {
      const el = this.shadowRoot.querySelector(`[data-k="${focusKey}"]`);
      if (el) {
        el.focus();
        if (caret !== null && "setSelectionRange" in el) try { el.setSelectionRange(caret, caret); } catch (_) { /* Zahlenfelder */ }
      }
    }
  }

  _tile(g, extra = "", cls = "") {
    const t = this._t;
    const exps = this._data.games.filter((e) => e.expansion && e.in_base && e.base_ids.includes(g.bgg_id)).length;
    const facts = [];
    facts.push(g.plays ? `${g.plays}×` : t.neverPlayed);
    if (g.last_play) facts.push(fmtDate(g.last_play));
    return `<button class="tile ${cls} ${g.loan ? "lent" : ""} ${g.plays ? "" : "shame"}" data-a="open" data-v="${g.bgg_id}">
      ${g.thumbnail ? `<img src="${esc(g.thumbnail)}" alt="" loading="lazy">` : `<div class="noimg">🎲</div>`}
      <div class="tname">${esc(g.name)}</div>
      <div class="tfacts">${facts.join(" · ")}</div>
      <div class="tags">
        ${g.loan ? `<span class="tag warn">${t.lentTo} ${esc(g.loan.borrower)}</span>` : ""}
        ${g.expansion ? `<span class="tag">${t.expansion}</span>` : ""}
        ${exps ? `<span class="tag">+${exps} ${t.exp}</span>` : ""}
        ${g.nfc_tag ? `<span class="tag" title="NFC">NFC</span>` : ""}
        ${g.ean ? `<span class="tag" title="EAN ${esc(g.ean)}">EAN</span>` : ""}
      </div>${extra}</button>`;
  }

  // ---- Regal ------------------------------------------------------------------
  /** Spiele, die im Regal sichtbar stehen (Erweiterungen im Basisspiel zählen nicht extra). */
  _shelfGames() {
    return this._data.games.filter((g) => !(g.expansion && g.in_base));
  }

  _areaName(areaId) {
    return (areaId && this._hass.areas?.[areaId]?.name) || "";
  }

  /** Bereichs-IDs der Räume in Anzeige-Reihenfolge ("" = ohne Raum, standardmäßig zuletzt). */
  _roomOrder() {
    const present = [...new Set(this._data.shelves.map((s) => s.area_id || ""))];
    const saved = (this._data.room_order || []).filter((a) => present.includes(a));
    const rest = present.filter((a) => !saved.includes(a))
      .sort((a, b) => (a ? 0 : 1) - (b ? 0 : 1) || naturalCompare(this._areaName(a), this._areaName(b)));
    return [...saved, ...rest];
  }

  /** Spiele eines Fachs in der eingestellten Reihenfolge des Regals. */
  _sortGames(list, shelf) {
    const byName = (a, b) => naturalCompare(a.name, b.name);
    const sorters = {
      name: byName,
      plays: (a, b) => (b.plays || 0) - (a.plays || 0) || byName(a, b),
      last_play: (a, b) => (b.last_play || "").localeCompare(a.last_play || "") || byName(a, b),
      manual: (a, b) => (a.position ?? 1e9) - (b.position ?? 1e9) || byName(a, b),
    };
    return [...list].sort(sorters[shelf?.game_sort] || byName);
  }

  _gamesInCompartment(shelfName, compartment) {
    const shelf = this._data.shelves.find((s) => s.name.toLowerCase() === shelfName.toLowerCase());
    const list = this._shelfGames().filter((g) => g.shelf.toLowerCase() === shelfName.toLowerCase() && (g.compartment || null) === (compartment || null));
    return this._sortGames(list, shelf);
  }

  async _move(kind, id, step) {
    if (kind === "room") {
      const order = this._roomOrder();
      const i = order.indexOf(id), j = i + step;
      if (i < 0 || j < 0 || j >= order.length) return;
      [order[i], order[j]] = [order[j], order[i]];
      await this._call("set_sort_order", { kind: "rooms", order });
    } else if (kind === "shelf") {
      const names = this._data.shelves.map((s) => s.name);
      const me = this._data.shelves.find((s) => s.name === id);
      const sameRoom = this._data.shelves.filter((s) => (s.area_id || "") === (me.area_id || "")).map((s) => s.name);
      const k = sameRoom.indexOf(id), other = sameRoom[k + step];
      if (!other) return;
      const a = names.indexOf(id), b = names.indexOf(other);
      [names[a], names[b]] = [names[b], names[a]];
      await this._call("set_sort_order", { kind: "shelves", order: names });
    } else {
      const g = this._games.get(Number(id));
      const ids = this._gamesInCompartment(g.shelf, g.compartment).map((x) => x.bgg_id);
      const i = ids.indexOf(g.bgg_id), j = i + step;
      if (j < 0 || j >= ids.length) return;
      [ids[i], ids[j]] = [ids[j], ids[i]];
      await this._call("set_sort_order", { kind: "games", order: ids.map(String) });
    }
  }

  /** IDs der Spiele, die zu Suche und Filter passen; null = nichts hervorheben. */
  _hits() {
    const ui = this._ui;
    const q = ui.search.trim().toLowerCase();
    if (!q && ui.filter === "all") return null;
    return new Set(this._shelfGames().filter((g) => {
      if (q && !g.name.toLowerCase().includes(q)) return false;
      if (ui.filter === "lent") return !!g.loan;
      if (ui.filter === "nolocation") return !g.shelf;
      if (ui.filter === "expansions") return g.expansion;
      return true;
    }).map((g) => g.bgg_id));
  }

  // Regal: nach Räumen gruppiert; Suche und Filter heben Treffer hervor, statt Spiele auszublenden
  _view_shelf() {
    const t = this._t, ui = this._ui;
    const filters = ["all", "lent", "nolocation", "expansions"].map((f) =>
      `<button class="chip ${ui.filter === f ? "on" : ""}" data-a="filter" data-v="${f}">${t.filters[f]}</button>`).join("");
    const hits = this._hits();
    const toolbar = `<div class="toolbar">
        <input type="search" placeholder="${t.search}" value="${esc(ui.search)}" data-k="search">
        <div class="chips">${filters}</div>
        <button class="chip ${ui.sorting ? "on" : ""}" data-a="sorttoggle">⇅ ${ui.sorting ? t.sortDone : t.sortMode}</button>
        ${hits ? `<span class="hitcount ${hits.size ? "" : "none"}">${hits.size ? `${hits.size} ${hits.size === 1 ? t.hit : t.hitsWord}` : t.noMatch}</span>` : ""}
      </div>`;
    if (!this._data.games.length) return toolbar + `<div class="empty">${t.noGames}</div>`;

    const games = this._shelfGames();
    const sorting = ui.sorting;
    const arrows = (kind, id, a = "▲", b = "▼", labels = [t.moveUp, t.moveDown]) => sorting
      ? `<span class="moves"><button class="icon small" data-a="move" data-v="${kind}|${esc(id)}|-1" title="${labels[0]}">${a}</button><button class="icon small" data-a="move" data-v="${kind}|${esc(id)}|1" title="${labels[1]}">${b}</button></span>` : "";
    const tileFor = (shelf) => (g) => {
      const html = this._tile(g, "", hits ? (hits.has(g.bgg_id) ? "hit" : "dim") : "");
      return sorting && shelf?.game_sort === "manual"
        ? `<div class="tilewrap">${html}${arrows("game", g.bgg_id, "◀", "▶", [t.moveLeft, t.moveRight])}</div>` : html;
    };
    const rooms = new Map();
    for (const shelf of this._data.shelves) {
      const key = shelf.area_id || "";
      if (!rooms.has(key)) rooms.set(key, []);
      rooms.get(key).push(shelf);
    }
    const shelfHtml = (shelf) => {
      const inShelf = games.filter((g) => g.shelf.toLowerCase() === shelf.name.toLowerCase());
      const tile = tileFor(shelf);
      const rows = [];
      const numbers = Array.from({ length: shelf.compartments }, (_, i) => i + 1);
      if (shelf.reversed) numbers.reverse(); // Fach 1 unten
      for (const n of numbers) {
        const list = this._sortGames(inShelf.filter((g) => g.compartment === n), shelf);
        rows.push(`<div class="fach"><div class="fnum">${t.compartment} ${n}</div><div class="boxes">${list.map(tile).join("") || `<span class="muted small">${t.emptyCompartment}</span>`}</div></div>`);
      }
      const loose = this._sortGames(inShelf.filter((g) => !g.compartment), shelf);
      if (loose.length) rows.push(`<div class="fach"><div class="fnum">${t.noCompartment}</div><div class="boxes">${loose.map(tile).join("")}</div></div>`);
      const hint = sorting && shelf.game_sort !== "manual" ? `<span class="muted small">${t.manualHint}</span>` : "";
      return `<section class="billy"><div class="shead"><h2>${esc(shelf.name)}</h2>${arrows("shelf", shelf.name)}
        <button class="link" data-a="editshelf" data-v="${esc(shelf.name)}">${t.shelfSettings}</button>${hint}</div>${rows.join("")}</section>`;
    };
    const unplaced = this._sortGames(games.filter((g) => !g.shelf));
    return toolbar
      + this._roomOrder().map((key) => `<section class="room"><h2 class="roomname">${esc(this._areaName(key) || t.noRoom)}${arrows("room", key)}</h2>${rooms.get(key).map(shelfHtml).join("")}</section>`).join("")
      + (unplaced.length ? `<section class="billy loose"><h2>${t.noLocation}</h2><div class="boxes">${unplaced.map(tileFor(null)).join("")}</div></section>` : "")
      + `<div class="row"><button data-a="newshelf">+ ${t.newShelf}</button>
          <button data-a="inventory">${BARCODE_ICON} ${this._data.inventory ? t.invContinue : t.inventory}</button></div>`;
  }

  /** Ersten Treffer sichtbar machen, ohne das Suchfeld zu verlassen. */
  _scrollToHit() {
    const hit = this.shadowRoot.querySelector(".tile.hit");
    if (!hit) return;
    const r = hit.getBoundingClientRect();
    if (r.top < 120 || r.bottom > window.innerHeight) hit.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  _shelfDialog() {
    const t = this._t, e = this._ui.shelfEdit;
    const areas = Object.values(this._hass.areas || {}).sort((a, b) => naturalCompare(a.name, b.name));
    const empty = e.original && !this._shelfGames().some((g) => g.shelf.toLowerCase() === e.original.toLowerCase());
    return `<div class="overlay" data-a="closeshelfedit"><div class="dialog small-dialog" role="dialog" aria-modal="true" data-stop="1">
      <button class="icon close" data-a="closeshelfedit" aria-label="${t.close}">✕</button>
      <h2>${e.original ? esc(e.original) : t.newShelf}</h2>
      <div class="form">
        <label>${t.name}<input value="${esc(e.name)}" data-k="sh.name"></label>
        <label>${t.room}<select data-k="sh.area_id"><option value="">${t.noRoom}</option>${areas.map((a) =>
          `<option value="${esc(a.area_id)}" ${a.area_id === e.area_id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></label>
        <label>${t.compartments}<input type="number" min="1" max="50" value="${esc(e.compartments)}" data-k="sh.compartments"></label>
        <label>${t.compartmentOrder}<select data-k="sh.reversed">
          <option value="false" ${e.reversed ? "" : "selected"}>${t.compartment1Top}</option>
          <option value="true" ${e.reversed ? "selected" : ""}>${t.compartment1Bottom}</option></select></label>
        <label>${t.gameSort}<select data-k="sh.game_sort">${["name", "plays", "last_play", "manual"].map((k) =>
          `<option value="${k}" ${e.game_sort === k ? "selected" : ""}>${t.gameSorts[k]}</option>`).join("")}</select></label>
      </div>
      <p class="muted small">${t.shelfHint}</p>
      <div class="row"><button class="primary" data-a="saveshelf" ${e.name.trim() ? "" : "disabled"}>${t.save}</button>
        ${empty ? `<button class="danger" data-a="removeshelf" data-v="${esc(e.original)}">${t.delete}</button>` : ""}</div>
    </div></div>`;
  }

  _gameDialog() {
    const t = this._t, ui = this._ui;
    const g = this._games.get(ui.game);
    if (!g) return "";
    const e = ui.edit;
    const session = this._data.session;
    const expansions = this._data.games.filter((x) => x.expansion && x.base_ids.includes(g.bgg_id));
    const bases = g.base_ids.map((id) => this._games.get(id)).filter(Boolean);
    const shelves = this._data.shelves.map((s) => s.name);
    const profiles = Object.keys(this._hass.states).filter((id) => id.startsWith("scene.") || id.startsWith("script.")).sort();
    const rulebooks = this._rulebooks(g.bgg_id);
    const facts = [];
    if (g.min_players && g.max_players) facts.push(g.min_players === g.max_players ? `${g.min_players} ${t.players}` : `${g.min_players}–${g.max_players} ${t.players}`);
    if (g.playing_time) facts.push(`${g.playing_time} ${t.min}`);
    if (g.mode) facts.push(t.modes[g.mode] || g.mode);
    for (const type of g.game_types) facts.push(t.types[type] || type);
    if (g.weight) facts.push(`${t.weight} ${g.weight.toFixed(1)}`);
    if (g.user_rating) facts.push(`${t.rating} ${g.user_rating}`);
    if (g.version_name) facts.push(g.version_name);
    else if (g.languages.length) facts.push(g.languages.join(", "));

    const plays = ui.gamePlays === null ? `<div class="muted">${t.loading}</div>`
      : ui.gamePlays.length ? `<ul class="plays">${ui.gamePlays.map((p) => `<li><b>${fmtDate(p.date)}</b>${p.quantity > 1 ? ` (${p.quantity}×)` : ""} ${esc(playersText(p.players, this._data.me))}${p.comments ? ` – <i>${esc(p.comments)}</i>` : ""}</li>`).join("")}</ul>`
      : `<div class="muted">${t.neverPlayed}</div>`;

    const loan = g.loan
      ? `<p>${t.lentTo} <b>${esc(g.loan.borrower)}</b> ${t.since} ${fmtDate(g.loan.since)}</p><button data-a="return" data-v="${g.bgg_id}">${t.giveBack}</button>`
      : `<div class="row"><input list="bgr-players" placeholder="${t.borrower}" value="${esc(ui.lendTo)}" data-k="lendTo"><button data-a="lend" data-v="${g.bgg_id}" ${ui.lendTo.trim() ? "" : "disabled"}>${t.lend}</button></div>
         <datalist id="bgr-players">${this._activePlayers().map((p) => `<option value="${esc(p.name)}">`).join("")}</datalist>`;

    return `<div class="overlay" data-a="close"><div class="dialog" role="dialog" aria-modal="true" data-stop="1">
      <button class="icon close" data-a="close" aria-label="${t.close}">✕</button>
      <div class="ghead">
        ${g.image || g.thumbnail ? `<img src="${esc(g.image || g.thumbnail)}" alt="">` : ""}
        <div>
          <h2>${esc(g.name)} ${g.year ? `<span class="muted">(${g.year})</span>` : ""}</h2>
          <div class="muted">${esc(facts.join(" · "))}</div>
          ${bases.length ? `<div class="small">${t.expands}: ${bases.map((b) => `<a href="#" data-a="open" data-v="${b.bgg_id}">${esc(b.name)}</a>`).join(", ")}</div>` : ""}
          <div class="kpis small"><span><b>${g.plays}</b> ${g.plays === 1 ? t.playOne : t.playsShort}</span><span>${t.lastPlay}: <b>${g.last_play ? fmtDate(g.last_play) : "–"}</b></span>
            ${g.last_players.length ? `<span>${esc(playersText(g.last_players, this._data.me))}</span>` : ""}</div>
          <div class="row">
            <button class="primary" data-a="start" data-v="${g.bgg_id}" ${session && session.state === "running" ? "disabled" : ""}>${t.startSession}</button>
            ${g.manual_url ? `<a class="button" href="${esc(g.manual_url)}" target="_blank" rel="noreferrer">${t.manual}</a>` : ""}
            <a class="button" href="https://boardgamegeek.com/boardgame/${g.bgg_id}" target="_blank" rel="noreferrer">BGG</a>
          </div>
        </div>
      </div>

      <h3>${t.assignments}</h3>
      <div class="form">
        <label>${t.shelf}<input list="bgr-shelves" value="${esc(e.shelf)}" data-k="edit.shelf"></label>
        <datalist id="bgr-shelves">${shelves.map((s) => `<option value="${esc(s)}">`).join("")}</datalist>
        <label>${t.compartment}<input type="number" min="0" max="50" value="${esc(e.compartment)}" data-k="edit.compartment"></label>
        ${g.expansion ? `<label class="check"><input type="checkbox" ${e.in_base ? "checked" : ""} data-k="edit.in_base">${t.inBase}</label>` : ""}
        <label>${t.nfc}<span class="row"><input value="${esc(e.nfc_tag)}" data-k="edit.nfc_tag"><button data-a="scanned" data-v="${g.bgg_id}">${t.takeScanned}</button></span></label>
        <label>${t.ean}<span class="row"><input inputmode="numeric" placeholder="4002051693602" value="${esc(e.ean)}" data-k="edit.ean"><button data-a="scanean" title="${t.scanEan}">${BARCODE_ICON}</button></span></label>
        <label>${t.light}<select data-k="edit.light_profile"><option value="">–</option>${profiles.map((p) => `<option value="${esc(p)}" ${p === e.light_profile ? "selected" : ""}>${esc(this._hass.states[p].attributes.friendly_name || p)}</option>`).join("")}</select></label>
        <label>${t.sound}<input placeholder="https://open.spotify.com/playlist/…" value="${esc(e.playlist)}" data-k="edit.playlist"></label>
        <label>${t.manual}<input type="url" placeholder="https://…" value="${esc(e.manual_url)}" data-k="edit.manual_url"></label>
      </div>
      ${this._data.options.media_player ? "" : `<p class="muted small">${t.noPlayerHint}</p>`}
      <div class="row"><button class="primary" data-a="save" data-v="${g.bgg_id}">${t.save}</button></div>

      <h3>${t.rulebooks}</h3>
      ${rulebooks.length ? `<ul class="plain">${rulebooks.map((n) => `<li><a href="#" data-a="rbopen" data-v="${g.bgg_id}|${esc(n)}">${esc(n.slice(0, -4))}</a>
        <button class="link" data-a="rbdel" data-v="${g.bgg_id}|${esc(n)}">${t.delete}</button></li>`).join("")}</ul>` : `<div class="muted small">${t.noRulebooks}</div>`}
      <div class="row"><label class="button ${ui.rbUploading ? "disabled" : ""}">${ui.rbUploading ? t.uploading : t.uploadPdf}<input type="file" accept="application/pdf,.pdf" multiple hidden data-upload="${g.bgg_id}" ${ui.rbUploading ? "disabled" : ""}></label></div>
      <p class="muted small">${t.rulebooksHint}</p>
      ${g.links.length ? `<div class="row">${g.links.map((l) => `<a class="button" href="${esc(l.url)}" target="_blank" rel="noreferrer">${esc(l.title)}</a>`).join("")}</div>` : ""}
      <div class="links">${e.links.map((l, i) => `<div class="row">
        <input placeholder="${t.linkTitle}" value="${esc(l.title)}" data-k="link.${i}.title">
        <input type="url" placeholder="https://…" value="${esc(l.url)}" data-k="link.${i}.url">
        <button class="link" data-a="linkdel" data-v="${i}">${t.remove}</button></div>`).join("")}</div>
      <div class="row"><button data-a="linkadd">${t.addLink}</button><button class="primary" data-a="save" data-v="${g.bgg_id}">${t.save}</button></div>
      <p class="muted small">${t.linksHint}</p>

      <h3>${t.loan}</h3>${loan}
      ${expansions.length ? `<h3>${t.expansions}</h3><ul class="plain">${expansions.map((x) => `<li><a href="#" data-a="open" data-v="${x.bgg_id}">${esc(x.name)}</a> <span class="muted small">${x.in_base ? t.inBaseShort : esc(location(x, t))}</span></li>`).join("")}</ul>` : ""}
      <h3>${t.recentPlays}</h3>${plays}
    </div></div>`;
  }

  _qrDialog() {
    const t = this._t, qr = this._ui.qr;
    return `<div class="overlay" data-a="closeqr"><div class="dialog qr" data-stop="1">
      <button class="icon close" data-a="closeqr" aria-label="${t.close}">✕</button>
      <h2>${esc(qr.title)}</h2>
      <div class="qrbox">${qr.svg}</div>
      <p class="muted small">${esc(qr.hint || "")}</p>
      <div class="row"><a class="button primary" href="${esc(qr.url)}" target="_blank" rel="noreferrer">${esc(qr.open)}</a>
      <button data-a="copy" data-v="${esc(qr.url)}">${t.copyLink}</button></div>
    </div></div>`;
  }

  // Sitzung: Spielhilfe während der Partie, danach Abschluss für BG Stats
  _view_session() {
    const t = this._t, s = this._data.session;
    if (!s) {
      return `<div class="empty">${t.noSession}<div class="row center"><button data-a="tab" data-v="suggest">${t.tabs.suggest}</button><button data-a="tab" data-v="shelf">${t.tabs.shelf}</button></div></div>`;
    }
    const g = this._games.get(s.bgg_id) || {};
    if (s.state === "running") {
      const order = s.order || [];
      const current = order.length ? order[s.turn % order.length] : null;
      const pool = [this._data.me, ...this._activePlayers().map((p) => p.name)];
      const editing = this._ui.order;
      return `<section class="card session">
        ${g.thumbnail ? `<img class="cover" src="${esc(g.thumbnail)}" alt="">` : ""}
        <h2>${esc(s.name)}</h2>
        <div class="big" id="elapsed">${elapsed(s.started)}</div>
        <div class="kpis"><span>${t.round} <b>${s.round}</b></span>${current ? `<span>${t.turn}: <b>${esc(current)}</b></span>` : ""}</div>
        <div class="row center">
          <button class="primary big-btn" data-a="next_player" ${order.length ? "" : "disabled"}>${t.nextPlayer}</button>
          <button class="big-btn" data-a="next_round">${t.nextRound}</button>
        </div>
        ${order.length ? `<div class="order">${order.map((n, i) => `<span class="chip ${i === s.turn % order.length ? "on" : ""}">${i + 1}. ${esc(n)}</span>`).join("")}</div>` : ""}
        ${editing ? `<div class="pick"><p class="muted small">${t.orderHint}</p><div class="chips center">${pool.map((n) => {
          const i = editing.indexOf(n);
          return `<button class="chip ${i >= 0 ? "on" : ""}" data-a="orderpick" data-v="${esc(n)}">${i >= 0 ? `${i + 1}. ` : ""}${esc(n)}</button>`;
        }).join("")}</div><div class="row center"><button class="primary" data-a="ordersave">${t.save}</button><button data-a="ordercancel">${t.cancel}</button></div></div>`
          : `<button class="link" data-a="orderedit">${order.length ? t.changeOrder : t.setOrder}</button>`}
        <div class="row center">
          ${g.manual_url ? `<a class="button" href="${esc(g.manual_url)}" target="_blank" rel="noreferrer">${t.manual}</a>` : ""}
          ${this._rulebooks(s.bgg_id).map((n) => `<button data-a="rbopen" data-v="${s.bgg_id}|${esc(n)}">${esc(n.slice(0, -4))}</button>`).join("")}
          ${(g.links || []).map((l) => `<a class="button" href="${esc(l.url)}" target="_blank" rel="noreferrer">${esc(l.title)}</a>`).join("")}
          <button class="primary" data-a="end">${t.endSession}</button>
          <button class="danger" data-a="cancel">${t.discard}</button>
        </div>
      </section>`;
    }
    // Beendet
    if (s.result) {
      return `<section class="card session"><h2>${esc(s.name)}</h2>
        <p>${t.finishedText}</p>
        <div class="row center"><button class="primary" data-a="showqr">${t.showQr}</button><button data-a="cancel">${t.done}</button></div></section>`;
    }
    const f = this._ensureFinish(s);
    const pool = [this._data.me, ...this._activePlayers().map((p) => p.name)];
    for (const n of f.players) if (!pool.some((p) => p.toLowerCase() === n.toLowerCase())) pool.push(n);
    return `<section class="card session"><h2>${esc(s.name)}</h2>
      <div class="muted">${fmtDate(s.started, true)} · ${duration(s.started, s.ended)} ${t.min}</div>
      <h3>${t.whoPlayed}</h3>
      <div class="chips">${pool.map((n) => `<button class="chip ${f.players.includes(n) ? "on" : ""}" data-a="finpick" data-v="${esc(n)}">${esc(n)}${n === this._data.me ? ` (${t.me})` : ""}</button>`).join("")}</div>
      <div class="row"><input placeholder="+ ${t.name}" value="${esc(f.newName)}" data-k="fin.newName"><button data-a="finadd" ${f.newName.trim() ? "" : "disabled"}>${t.add}</button></div>
      ${f.players.length ? `<table class="scores"><tr><th>${t.player}</th><th>${t.score}</th><th>${t.winner}</th></tr>${f.players.map((n) => `<tr><td>${esc(n)}</td>
        <td><input inputmode="decimal" value="${esc(f.scores[n] ?? "")}" data-k="fin.score.${esc(n)}"></td>
        <td><input type="checkbox" ${f.winners.includes(n) ? "checked" : ""} data-k="fin.win.${esc(n)}"></td></tr>`).join("")}</table>
        <p class="muted small">${t.autoWinner}</p>` : ""}
      <label class="block">${t.note}<textarea rows="2" data-k="fin.note">${esc(f.note)}</textarea></label>
      <div class="row center"><button class="primary" data-a="finish">${t.finish}</button><button class="danger" data-a="cancel">${t.discard}</button></div>
    </section>`;
  }

  _ensureFinish(s) {
    const key = `${s.bgg_id}-${s.started}`;
    if (!this._ui.finish || this._ui.finish.key !== key) {
      this._ui.finish = { key, players: [...(s.order || [])], scores: {}, winners: [], note: "", newName: "" };
    }
    return this._ui.finish;
  }

  _view_suggest() {
    const t = this._t, f = this._ui.sug, sug = this._data.suggestion;
    const sel = (key, options, labels) => `<select data-k="sug.${key}">${options.map((o) => `<option value="${o}" ${String(f[key]) === String(o) ? "selected" : ""}>${labels[o]}</option>`).join("")}</select>`;
    const form = `<section class="card">
      <div class="form">
        <label>${t.players}<input type="number" min="1" max="20" value="${esc(f.players)}" data-k="sug.players"></label>
        <label>${t.mode}${sel("mode", ["any", "cooperative", "competitive"], { any: t.any, ...t.modes })}</label>
        <label>${t.type}${sel("game_type", ["any", "family", "strategy", "party", "abstract", "thematic", "wargame", "children"], { any: t.any, ...t.types })}</label>
        <label>${t.maxTime}${sel("max_playtime", ["", "30", "45", "60", "90", "120", "180"], { "": t.any, 30: "30 min", 45: "45 min", 60: "60 min", 90: "90 min", 120: "2 h", 180: "3 h" })}</label>
      </div>
      ${this._activePlayers().length ? `<h3>${t.attendees}</h3><div class="chips">${this._activePlayers().map((p) => `<button class="chip ${f.attendees.includes(p.name) ? "on" : ""}" data-a="att" data-v="${esc(p.name)}">${esc(p.name)}</button>`).join("")}</div>` : ""}
      <div class="row"><button class="primary" data-a="suggest">${t.suggestBtn}</button></div></section>`;
    let result = "";
    if (sug.phase === "suggested" || sug.phase === "accepted") {
      const g = this._games.get(sug.game.bgg_id) || sug.game;
      const accepted = sug.phase === "accepted";
      result = `<section class="card suggestion">
        ${g.thumbnail ? `<img class="cover" src="${esc(g.thumbnail)}" alt="">` : ""}
        <div><div class="muted">${accepted ? t.goGet : t.howAbout}</div><h2>${esc(g.name)}</h2>
        <div class="muted">${g.plays ? `${g.plays}× · ${t.lastPlay} ${fmtDate(g.last_play)}` : t.neverPlayed}</div>
        ${accepted ? `<div class="big">${esc(location(g, this._t) || t.noLocation)}</div>` : ""}
        <div class="row">${accepted
          ? `<button class="primary" data-a="start" data-v="${g.bgg_id}">${t.startSession}</button><button data-a="sugreset">${t.back}</button>`
          : `<button class="primary" data-a="sugaccept">${t.yes}</button><button data-a="sugreject">${t.no}</button><span class="muted small">${sug.remaining} ${t.more}</span>`}</div></div></section>`;
    } else if (sug.phase === "none") {
      result = `<section class="card"><p>${t.noSuggestion}</p><button data-a="sugreset">${t.back}</button></section>`;
    }
    return result + form;
  }

  _view_evenings() {
    const t = this._t, ev = this._ui.evening;
    const now = new Date();
    const list = [...this._data.evenings].sort((a, b) => a.start.localeCompare(b.start));
    const cards = list.map((e) => {
      const counts = {};
      for (const ids of Object.values(e.votes)) for (const id of ids) counts[id] = (counts[id] || 0) + 1;
      const ranked = [...e.candidates].sort((a, b) => (counts[b] || 0) - (counts[a] || 0));
      const past = new Date(e.start) < new Date(now.getTime() - 86400000);
      const addable = this._data.games.filter((g) => !g.expansion && !e.candidates.includes(g.bgg_id));
      return `<section class="card ${past ? "past" : ""}">
        <h2>${esc(e.title)}</h2>
        <div class="muted">${fmtDate(e.start, true)} · ${e.guests.length ? esc(e.guests.join(", ")) : t.noGuests}${e.max_playtime ? ` · ≤ ${e.max_playtime} ${t.min}` : ""}</div>
        <ol class="ranking">${ranked.map((id) => {
          const g = this._games.get(id);
          const voters = Object.entries(e.votes).filter(([, ids]) => ids.includes(id)).map(([v]) => v);
          return `<li><span>${esc(g ? g.name : id)}</span><span class="muted small">${voters.length ? esc(voters.join(", ")) : ""}</span><b>${counts[id] || 0}</b><button class="icon small" data-a="candremove" data-v="${e.id}:${id}" title="${t.remove}">✕</button></li>`;
        }).join("")}</ol>
        <div class="row"><select data-k="cand.${e.id}"><option value="">+ ${t.addGame}</option>${addable.map((g) => `<option value="${g.bgg_id}">${esc(g.name)}</option>`).join("")}</select></div>
        <div class="row"><button class="primary" data-a="eveqr" data-v="${e.id}">${t.voteLink}</button><button class="danger" data-a="everemove" data-v="${e.id}">${t.delete}</button></div>
      </section>`;
    }).join("");
    const form = ev ? `<section class="card"><h2>${t.newEvening}</h2><div class="form">
        <label>${t.title}<input value="${esc(ev.title)}" data-k="ev.title"></label>
        <label>${t.start}<input type="datetime-local" value="${esc(ev.start)}" data-k="ev.start"></label>
        <label>${t.maxTime}<input type="number" min="0" placeholder="${t.any}" value="${esc(ev.max_playtime)}" data-k="ev.max_playtime"></label></div>
        <h3>${t.guests}</h3><div class="chips">${this._activePlayers().map((p) => `<button class="chip ${ev.guests.includes(p.name) ? "on" : ""}" data-a="evguest" data-v="${esc(p.name)}">${esc(p.name)}</button>`).join("")}</div>
        <div class="row"><input placeholder="+ ${t.name}" value="${esc(ev.newGuest)}" data-k="ev.newGuest"><button data-a="evaddguest" ${ev.newGuest.trim() ? "" : "disabled"}>${t.add}</button></div>
        <p class="muted small">${t.eveningHint}</p>
        <div class="row"><button class="primary" data-a="evcreate" ${ev.start ? "" : "disabled"}>${t.create}</button><button data-a="evcancel">${t.cancel}</button></div></section>`
      : `<div class="row"><button class="primary" data-a="evnew">+ ${t.newEvening}</button></div>`;
    return form + (cards || `<div class="empty">${t.noEvenings}</div>`);
  }

  /** Mitspieler für Auswahllisten: ausgeblendete fehlen dort. */
  _activePlayers() {
    return this._data.players.filter((p) => !p.hidden);
  }

  _view_players() {
    const t = this._t, edits = this._ui.playerEdit;
    const hidden = this._data.players.filter((p) => p.hidden);
    const hiddenHtml = hidden.length ? `<details class="card hidden-players" ${this._ui.hiddenOpen ? "open" : ""}><summary data-a="hiddentoggle">${t.hiddenPlayers} (${hidden.length})</summary>
      <p class="muted small">${t.hiddenHint}</p>
      <ul class="hidden-list">${hidden.map((p) => `<li><span>${esc(p.name)}</span><span class="muted small">${p.plays} ${p.plays === 1 ? t.playOne : t.playsShort}</span>
        <button data-a="plunhide" data-v="${esc(p.name)}">${t.unhide}</button></li>`).join("")}</ul></details>` : "";
    const rows = this._activePlayers().map((p) => {
      const e = edits[p.name];
      const dislikes = (e ? e.dislikes : p.dislikes);
      return `<section class="card player">
        <div class="phead"><h2>${esc(p.name)}</h2><span class="muted">${p.plays} ${p.plays === 1 ? t.playOne : t.playsShort}</span>
          ${p.bgg_username ? `<a class="small" href="https://boardgamegeek.com/user/${encodeURIComponent(p.bgg_username)}" target="_blank" rel="noreferrer">BGG: ${esc(p.bgg_username)}</a>` : ""}</div>
        ${e ? `<div class="form"><label>${t.bggUser}<input value="${esc(e.bgg_username)}" data-k="pl.${esc(p.name)}.bgg_username"></label></div>
          <h3>${t.dislikes}</h3><div class="chips">${this._data.dislike_options.map((d) => `<button class="chip ${dislikes.includes(d) ? "on" : ""}" data-a="pldis" data-v="${esc(p.name)}|${d}">${t.modes[d] || t.types[d]}</button>`).join("")}</div>
          <div class="row"><button class="primary" data-a="plsave" data-v="${esc(p.name)}">${t.save}</button><button data-a="plcancel" data-v="${esc(p.name)}">${t.cancel}</button>
          ${p.from_bgg ? "" : `<button class="danger" data-a="plremove" data-v="${esc(p.name)}">${t.remove}</button>`}</div>`
        : `<div>${dislikes.length ? `${t.dislikes}: ${dislikes.map((d) => esc(t.modes[d] || t.types[d])).join(", ")}` : `<span class="muted small">${t.noDislikes}</span>`}</div>
          <div class="row"><button class="link" data-a="pledit" data-v="${esc(p.name)}">${t.edit}</button>
          <button class="link muted" data-a="plhide" data-v="${esc(p.name)}">${t.hide}</button></div>`}
      </section>`;
    }).join("");
    return `<section class="card"><div class="row"><input placeholder="${t.newPlayer}" value="${esc(this._ui.newPlayer)}" data-k="newPlayer">
      <button class="primary" data-a="pladd" ${this._ui.newPlayer.trim() ? "" : "disabled"}>${t.add}</button></div>
      <p class="muted small">${t.playersHint}</p></section>${rows || `<div class="empty">${t.noPlayers}</div>`}${hiddenHtml}`;
  }

  _view_stats() {
    const t = this._t, s = this._data.stats;
    const max = Math.max(1, ...s.per_month.map((m) => m.plays));
    const kpi = (v, label) => `<div class="kpi"><b>${v}</b><span>${label}</span></div>`;
    const list = (ids, extra) => ids.map((id) => this._games.get(id)).filter(Boolean)
      .map((g) => `<li><a href="#" data-a="open" data-v="${g.bgg_id}">${esc(g.name)}</a> <span class="muted small">${extra(g)}</span></li>`).join("");
    return `<div class="kpis tiles">
        ${kpi(s.games, t.games)}${kpi(s.expansions, t.expansions)}${kpi(s.plays_total, t.playsTotal)}
        ${kpi(s.plays_this_month, t.thisMonth)}${kpi(s.h_index, "H-Index")}${kpi(s.pile_of_shame.length, "Pile of Shame")}</div>
      <section class="card"><h2>${t.perMonth}</h2>
        <div class="bars" role="img" aria-label="${t.perMonth}">${s.per_month.map((m) => `<div class="bar" title="${m.month}: ${m.plays}">
          <span class="val">${m.plays || ""}</span><span class="fill" style="height:${(m.plays / max) * 100}%"></span><span class="lbl">${monthLabel(m.month, this._t)}</span></div>`).join("")}</div></section>
      <section class="card"><h2>${t.top}</h2><ol class="plain">${list(s.top, (g) => `${g.plays}×`)}</ol></section>
      <section class="card"><h2>${t.longUnplayed} (${s.long_unplayed.length})</h2>
        <p class="muted small">${t.longUnplayedHint.replace("{n}", this._data.options.long_months)}</p>
        <ul class="plain">${list(s.long_unplayed, (g) => fmtDate(g.last_play)) || `<li class="muted">–</li>`}</ul></section>`;
  }

  _view_shame() {
    const t = this._t;
    const games = this._data.stats.pile_of_shame.map((id) => this._games.get(id)).filter(Boolean);
    return `<p class="lead">${t.shameLead.replace("{n}", games.length)}</p>
      <div class="boxes">${games.map((g) => this._tile(g)).join("")}</div>
      ${games.length ? "" : `<div class="empty">${t.shameEmpty}</div>`}`;
  }

  _view_wishlist() {
    const t = this._t;
    const fresh = this._data.new_expansions;
    const news = fresh.length ? `<section class="card"><h2>${t.newExpansions}</h2><ul class="plain">${fresh.map((e) =>
      `<li><a href="https://boardgamegeek.com/boardgameexpansion/${e.bgg_id}" target="_blank" rel="noreferrer">${esc(e.name)}</a> <span class="muted small">${t.for} ${esc(e.base_name)}</span></li>`).join("")}</ul>
      <button data-a="dismissexp">${t.seen}</button></section>` : "";
    const prio = { 1: t.prio1, 2: t.prio2, 3: t.prio3, 4: t.prio4, 5: t.prio5 };
    const wish = this._data.wishlist.map((w) => `<li>${w.thumbnail ? `<img src="${esc(w.thumbnail)}" alt="" loading="lazy">` : ""}
      <a href="https://boardgamegeek.com/boardgame/${w.bgg_id}" target="_blank" rel="noreferrer">${esc(w.name)}</a>
      ${w.year ? `<span class="muted small">(${w.year})</span>` : ""} ${w.priority ? `<span class="tag">${prio[w.priority] || w.priority}</span>` : ""}</li>`).join("");
    return news + `<section class="card"><h2>${t.tabs.wishlist}</h2>${wish ? `<ul class="wish">${wish}</ul>` : `<div class="muted">${t.wishEmpty}</div>`}</section>`;
  }

  _view_loans() {
    const t = this._t, limit = this._data.options.loan_days;
    const today = new Date();
    const rows = this._data.loans.map((l) => {
      const days = Math.floor((today - new Date(l.since)) / 86400000);
      return `<li class="${days >= limit ? "overdue" : ""}"><a href="#" data-a="open" data-v="${l.bgg_id}">${esc(l.name || l.bgg_id)}</a>
        <span>${esc(l.borrower)}</span><span class="muted">${fmtDate(l.since)} · ${days} ${t.days}</span>
        <button data-a="return" data-v="${l.bgg_id}">${t.giveBack}</button></li>`;
    }).join("");
    return `<section class="card"><p class="muted small">${t.loansHint.replace("{n}", limit)}</p>
      ${rows ? `<ul class="loans">${rows}</ul>` : `<div class="muted">${t.noLoans}</div>`}</section>`;
  }

  // ---- Eingaben ----------------------------------------------------------------
  _onInput(e) {
    if (e.target.dataset?.upload) {
      if (e.type === "change") this._uploadRules(Number(e.target.dataset.upload), [...e.target.files]);
      return;
    }
    const k = e.target.dataset?.k;
    if (!k) return;
    const v = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    const ui = this._ui;
    const [head, ...rest] = k.split(".");
    if (k === "search") { ui.search = v; this._render(); this._scrollToHit(); return; }
    if (k === "lendTo") { ui.lendTo = v; this._render(); return; }
    if (k === "newPlayer") { ui.newPlayer = v; this._render(); return; }
    if (head === "edit") { ui.edit[rest[0]] = v; return; }
    if (head === "link") { ui.edit.links[Number(rest[0])][rest[1]] = v; return; }
    if (head === "sh") { ui.shelfEdit[rest[0]] = v; if (rest[0] === "name") this._render(); return; }
    if (k.startsWith("scan.form.") && this._scan) {
      this._scan.form[k.slice(10)] = v;
      const btn = this.shadowRoot.querySelector('[data-a="invbegin"]');
      if (btn) btn.disabled = !String(this._scan.form.shelf).trim();
      return;
    }
    if (k === "scan.addName" && this._scan) {
      this._scan.addName = v;
      const btn = this.shadowRoot.querySelector('[data-a="invadd"]');
      if (btn) btn.disabled = !v.trim();
      return;
    }
    if (k === "scan.assign" && this._scan) {
      this._scan.assign = v;
      const btn = this.shadowRoot.querySelector('[data-a="scanassign"]');
      if (btn) btn.disabled = !v.trim();
      return;
    }
    if (head === "sug") { ui.sug[rest[0]] = v; return; }
    if (head === "ev") { ui.evening[rest[0]] = v; if (rest[0] === "newGuest" || rest[0] === "start") this._render(); return; }
    if (head === "pl") { const name = rest.slice(0, -1).join("."); ui.playerEdit[name][rest.at(-1)] = v; return; }
    if (head === "cand" && e.type === "change" && v) {
      const evening = this._data.evenings.find((x) => x.id === Number(rest[0]));
      this._call("set_candidates", { evening_id: evening.id, candidates: [...evening.candidates, Number(v)] });
      return;
    }
    if (head === "fin") {
      const f = ui.finish;
      if (rest[0] === "note") f.note = v;
      else if (rest[0] === "newName") { f.newName = v; this._render(); }
      else if (rest[0] === "score") f.scores[rest.slice(1).join(".")] = v;
      else if (rest[0] === "win") {
        const n = rest.slice(1).join(".");
        f.winners = v ? [...f.winners, n] : f.winners.filter((w) => w !== n);
      }
    }
  }

  async _onClick(e) {
    const target = e.target.closest("[data-a]");
    if (!target) return;
    // Klick in den Dialog schließt ihn nicht
    if (["close", "closeqr", "closeshelfedit"].includes(target.dataset.a) && e.target.closest("[data-stop]") && !e.target.closest(".close")) return;
    e.preventDefault();
    const a = target.dataset.a, v = target.dataset.v;
    const ui = this._ui, t = this._t;
    switch (a) {
      case "menu": this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true })); return;
      case "tab": this._tab = v; ui.game = null; break;
      case "sync": if (await this._call("sync_now")) this._showToast(t.syncStarted); return;
      case "filter": ui.filter = v; this._render(); this._scrollToHit(); return;
      case "sorttoggle": ui.sorting = !ui.sorting; break;
      case "move": { const [kind, id, step] = v.split("|"); await this._move(kind, id, Number(step)); return; }
      case "newshelf": ui.shelfEdit = { original: "", name: "", area_id: "", compartments: 6, reversed: false, game_sort: "name" }; break;
      case "editshelf": {
        const s = this._data.shelves.find((x) => x.name === v);
        ui.shelfEdit = { original: s.name, name: s.name, area_id: s.area_id, compartments: s.compartments,
                         reversed: s.reversed, game_sort: s.game_sort };
        break;
      }
      case "closeshelfedit": ui.shelfEdit = null; break;
      case "saveshelf": {
        const e = ui.shelfEdit, name = e.name.trim();
        const data = { name: e.original || name, area_id: e.area_id, compartments: Number(e.compartments) || 0,
                       compartment_1_bottom: String(e.reversed) === "true", game_sort: e.game_sort };
        if (e.original && name !== e.original) data.new_name = name;
        if (await this._call("set_shelf", data)) { ui.shelfEdit = null; this._showToast(t.saved); }
        return;
      }
      case "removeshelf":
        if (confirm(t.confirmDelete) && await this._call("remove_shelf", { name: v })) ui.shelfEdit = null;
        return;
      case "scan": this._openScan("session"); return;
      case "scanean": this._openScan("ean"); return;
      case "scanclose":
        // Schließen während der Inventur = Fertig (mit Nachfrage zu nicht gescannten Spielen)
        if (this._scan?.mode === "inventory" && this._data.inventory) await this._inventoryAction("done");
        else this._closeScan();
        return;
      case "inventory": this._openScan("inventory"); return;
      case "invbegin": case "invadd": case "invundo": case "invnext": case "invdone":
        await this._inventoryAction(a.slice(3)); return;
      case "scanassign": await this._assignScanned(); return;
      case "open": return this._openGame(Number(v));
      case "linkadd": ui.edit.links.push({ title: "", url: "" }); break;
      case "linkdel": ui.edit.links.splice(Number(v), 1); break;
      case "rbopen": { const [id, name] = v.split("|"); return this._openRules(Number(id), name); }
      case "rbdel": {
        const [id, name] = v.split("|");
        if (confirm(t.confirmDelete)) await this._rulesRequest(Number(id), name, "DELETE");
        return;
      }
      case "close": ui.game = null; break;
      case "closeqr": ui.qr = null; break;
      case "copy": try { await navigator.clipboard.writeText(v); this._showToast(t.copied); } catch (_) { this._showToast(v); } return;
      case "save": {
        const ed = ui.edit;
        const ok = await this._call("set_game", {
          bgg_id: Number(v), shelf: ed.shelf, compartment: ed.compartment === "" ? 0 : Number(ed.compartment),
          in_base: !!ed.in_base, nfc_tag: ed.nfc_tag, light_profile: ed.light_profile, playlist: ed.playlist,
          manual_url: ed.manual_url, ean: ed.ean,
          links: ed.links.filter((l) => l.url.trim()).map((l) => ({ title: l.title.trim(), url: l.url.trim() })),
        });
        if (ok) this._showToast(t.saved);
        return;
      }
      case "scanned": {
        const res = await this._call("assign_scanned_tag", { bgg_id: Number(v) }, true);
        if (res) { ui.edit.nfc_tag = res.nfc_tag; this._showToast(t.saved); }
        return;
      }
      case "lend": if (await this._call("lend_game", { bgg_id: Number(v), borrower: ui.lendTo })) ui.lendTo = ""; return;
      case "return": await this._call("return_game", { bgg_id: Number(v) }); return;
      case "start":
        if (await this._call("start_session", { bgg_id: Number(v) })) { ui.game = null; this._tab = "session"; }
        break;
      case "next_player": case "next_round": await this._call(a); return;
      case "end": await this._call("end_session"); return;
      case "cancel": if (confirm(t.confirmDiscard)) { await this._call("cancel_session"); ui.finish = null; } return;
      case "orderedit": ui.order = [...(this._data.session.order || [])]; break;
      case "orderpick": ui.order = ui.order.includes(v) ? ui.order.filter((n) => n !== v) : [...ui.order, v]; break;
      case "ordercancel": ui.order = null; break;
      case "ordersave": if (await this._call("set_order", { order: ui.order })) ui.order = null; return;
      case "finpick": { const f = ui.finish; f.players = f.players.includes(v) ? f.players.filter((n) => n !== v) : [...f.players, v]; break; }
      case "finadd": { const f = ui.finish; const n = f.newName.trim(); if (n && !f.players.includes(n)) f.players.push(n); f.newName = ""; break; }
      case "finish": {
        const f = ui.finish;
        const players = f.players.map((n) => ({ name: n, score: f.scores[n] ?? "", winner: f.winners.includes(n) }));
        const res = await this._call("finish_session", { players, note: f.note }, true);
        if (res) ui.qr = { title: t.toBgStats, svg: res.qr_svg, url: res.url, open: t.openBgStats, hint: t.qrHint };
        break;
      }
      case "showqr": {
        const res = await this._call("session_qr", {}, true);
        if (res) ui.qr = { title: t.toBgStats, svg: res.qr_svg, url: res.url, open: t.openBgStats, hint: t.qrHint };
        break;
      }
      case "att": { const f = ui.sug; f.attendees = f.attendees.includes(v) ? f.attendees.filter((n) => n !== v) : [...f.attendees, v]; break; }
      case "suggest": {
        const f = ui.sug, data = { mode: f.mode, game_type: f.game_type };
        if (f.players) data.players = Number(f.players);
        if (f.max_playtime) data.max_playtime = Number(f.max_playtime);
        if (f.attendees.length) { data.attendees = f.attendees; if (!f.players) data.players = f.attendees.length + 1; }
        await this._call("suggest", data, true);
        return;
      }
      case "sugaccept": await this._call("accept_suggestion", {}, true); return;
      case "sugreject": await this._call("reject_suggestion", {}, true); return;
      case "sugreset": await this._call("reset_suggestion"); return;
      case "evnew": ui.evening = { title: t.gameNight, start: nextFriday(), max_playtime: "", guests: [], newGuest: "" }; break;
      case "evcancel": ui.evening = null; break;
      case "evguest": { const ev = ui.evening; ev.guests = ev.guests.includes(v) ? ev.guests.filter((n) => n !== v) : [...ev.guests, v]; break; }
      case "evaddguest": { const ev = ui.evening; const n = ev.newGuest.trim(); if (n && !ev.guests.includes(n)) ev.guests.push(n); ev.newGuest = ""; break; }
      case "evcreate": {
        const ev = ui.evening, data = { title: ev.title, start: ev.start.replace("T", " ") + ":00", guests: ev.guests, base_url: location.origin };
        if (ev.max_playtime) data.max_playtime = Number(ev.max_playtime);
        const res = await this._call("plan_evening", data, true);
        if (res) { ui.evening = null; ui.qr = { title: t.voteLink, svg: res.qr_svg, url: res.vote_url, open: t.openVote, hint: t.voteHint }; }
        break;
      }
      case "eveqr": {
        const res = await this._call("evening_qr", { evening_id: Number(v), base_url: location.origin }, true);
        if (res) ui.qr = { title: t.voteLink, svg: res.qr_svg, url: res.vote_url, open: t.openVote, hint: t.voteHint };
        break;
      }
      case "everemove": if (confirm(t.confirmDelete)) await this._call("remove_evening", { evening_id: Number(v) }); return;
      case "candremove": {
        const [eid, gid] = v.split(":").map(Number);
        const evening = this._data.evenings.find((x) => x.id === eid);
        await this._call("set_candidates", { evening_id: eid, candidates: evening.candidates.filter((c) => c !== gid) });
        return;
      }
      case "pladd": if (await this._call("set_player", { name: ui.newPlayer.trim() })) ui.newPlayer = ""; return;
      case "pledit": { const p = this._data.players.find((x) => x.name === v); ui.playerEdit[v] = { bgg_username: p.bgg_username || "", dislikes: [...p.dislikes] }; break; }
      case "plcancel": delete ui.playerEdit[v]; break;
      case "pldis": {
        const [name, d] = v.split("|");
        const pe = ui.playerEdit[name];
        pe.dislikes = pe.dislikes.includes(d) ? pe.dislikes.filter((x) => x !== d) : [...pe.dislikes, d];
        break;
      }
      case "plsave": {
        const pe = ui.playerEdit[v];
        if (await this._call("set_player", { name: v, bgg_username: pe.bgg_username.trim(), dislikes: pe.dislikes })) delete ui.playerEdit[v];
        return;
      }
      case "hiddentoggle": ui.hiddenOpen = !ui.hiddenOpen; break;
      case "plhide": case "plunhide":
        await this._call("set_player", { name: v, hidden: a === "plhide" });
        if (a === "plhide") this._showToast(t.hiddenToast.replace("{name}", v));
        return;
      case "plremove": if (confirm(t.confirmDelete)) { await this._call("remove_player", { name: v }); delete ui.playerEdit[v]; } return;
      case "dismissexp": await this._call("dismiss_expansions"); return;
      default: return;
    }
    this._render();
  }

  // ---- Scanner: Kamera (BarcodeDetector) oder Barcode-Scanner (tippt wie eine Tastatur) ----
  /** mode "session": Code wie NFC-Tag behandeln; "ean": EAN ins Spiel-Fenster übernehmen;
   *  "inventory": Regal Fach für Fach durchscannen (Scans setzen den Standort). */
  _openScan(mode) {
    const t = this._t;
    if (mode === "session" && this._data?.inventory) mode = "inventory"; // laufende Inventur weiterführen
    const firstShelf = this._data?.shelves[0]?.name || "";
    this._scan = { mode, result: null, assign: "", addName: "", last: "", lastAt: 0,
                   form: { shelf: firstShelf, compartment: 1 } };
    const title = { ean: t.scanEan, inventory: t.inventory }[mode] || t.scan;
    const box = this.shadowRoot.getElementById("scan");
    box.innerHTML = `<div class="overlay scan-overlay"><div class="dialog small-dialog" role="dialog" aria-modal="true">
      <button class="icon close" data-a="scanclose" aria-label="${t.close}">✕</button>
      <h2>${title}</h2>
      <div class="scanvideo" hidden><video playsinline muted></video><div class="aim"></div></div>
      <div id="scanbody"></div></div></div>`;
    this._renderScan();
    if (this._cameraSupported()) this._startCamera();
  }

  _cameraSupported() {
    return "BarcodeDetector" in window && !!navigator.mediaDevices?.getUserMedia;
  }

  _renderScan() {
    const t = this._t, s = this._scan;
    const body = this.shadowRoot.getElementById("scanbody");
    if (!s || !body) return;
    // Fokus merken: ein Barcode-Scanner tippt immer ins Code-Feld, außer man tippt gerade woanders
    const focused = this.shadowRoot.activeElement?.dataset?.k;
    let result = "";
    const r = s.result;
    if (r?.result === "placed") result = `<p class="ok">✓ ${esc(r.name)} → ${esc(r.shelf)}, ${t.compartment} ${r.compartment}</p>`;
    else if (r?.result === "already") result = `<p class="muted">${t.invAlready.replace("{name}", esc(r.name))}</p>`;
    else if (r?.result === "started") result = `<p class="ok">▶ ${esc(r.name)} – ${t.scanStarted}</p>`;
    else if (r?.result === "ended") result = `<p class="ok">■ ${esc(r.name)} – ${t.scanEnded}</p>`;
    else if (r?.result === "busy") result = `<p class="warn">${t.scanBusy.replace("{name}", esc(r.running || ""))}</p>`;
    else if (r?.result === "assigned") result = `<p class="ok">${t.scanAssigned.replace("{name}", esc(r.name))}</p>`;
    else if (r?.result === "unknown") {
      result = `<p>${t.scanUnknown.replace("{code}", esc(r.code))}</p>
        <div class="row"><input list="bgr-allgames" placeholder="${t.search}" value="${esc(s.assign)}" data-k="scan.assign">
        <button class="primary" data-a="scanassign" ${s.assign.trim() ? "" : "disabled"}>${t.assign}</button></div>
        <datalist id="bgr-allgames">${this._data.games.filter((g) => !g.ean).map((g) => `<option value="${esc(g.name)}">`).join("")}</datalist>`;
    } else if (r?.error) result = `<p class="warn">${esc(r.error)}</p>`;
    const codeField = `<label class="block">${t.scanCode}<input inputmode="numeric" autocomplete="off" data-k="scan.code" placeholder="${t.scanCodePlaceholder}"></label>`;
    const hint = `<p class="muted small">${this._cameraSupported() ? t.scanHintCamera : t.scanHintNoCamera}</p>`;
    const inv = this._data.inventory;

    if (s.mode === "inventory" && !inv) {
      // Startformular: Regal (auch neu) und Startfach
      this._toggleVideo(false);
      body.innerHTML = `<p class="muted small">${t.invIntro}</p>
        <div class="form"><label>${t.shelf}<input list="bgr-inv-shelves" value="${esc(s.form.shelf)}" data-k="scan.form.shelf"></label>
        <label>${t.invStartCompartment}<input type="number" min="1" max="50" value="${esc(s.form.compartment)}" data-k="scan.form.compartment"></label></div>
        <datalist id="bgr-inv-shelves">${this._data.shelves.map((x) => `<option value="${esc(x.name)}">`).join("")}</datalist>
        <div class="row"><button class="primary" data-a="invbegin" ${s.form.shelf.trim() ? "" : "disabled"}>${t.invBegin}</button></div>`;
      return;
    }
    if (s.mode === "inventory") {
      this._toggleVideo(true);
      const placed = inv.placed.map((g, i) => `<li>${i + 1}. ${esc(g.name)}</li>`).join("");
      body.innerHTML = `<div class="invhead">${esc(inv.shelf)} · ${t.compartment} ${inv.compartment}</div>
        ${hint}${codeField}${result}
        <h3>${t.invPlaced.replace("{n}", inv.placed.length)}</h3>
        ${placed ? `<ol class="invlist">${placed}</ol>` : `<p class="muted small">${t.invNothingYet}</p>`}
        ${inv.missing.length ? `<p class="muted small">${t.invStillHere}: ${esc(inv.missing.map((g) => g.name).join(", "))}</p>` : ""}
        <div class="row"><input list="bgr-inv-games" placeholder="${t.invAddByName}" value="${esc(s.addName)}" data-k="scan.addName">
          <button data-a="invadd" ${s.addName.trim() ? "" : "disabled"}>${t.add}</button></div>
        <datalist id="bgr-inv-games">${this._shelfGames().map((g) => `<option value="${esc(g.name)}">`).join("")}</datalist>
        <div class="row"><button data-a="invundo" ${inv.placed.length ? "" : "disabled"}>${t.invUndo}</button>
          <button class="primary" data-a="invnext">${t.invNext}</button>
          <button data-a="invdone">${t.invDone}</button></div>`;
    } else {
      body.innerHTML = `${hint}${codeField}${result}`;
    }
    const keep = focused && focused !== "scan.code" ? this.shadowRoot.querySelector(`[data-k="${focused}"]`) : null;
    (keep || this.shadowRoot.querySelector('[data-k="scan.code"]'))?.focus();
  }

  /** Kamerabild nur zeigen, wenn gerade gescannt wird (nicht im Startformular der Inventur). */
  _toggleVideo(show) {
    const wrap = this.shadowRoot.querySelector(".scanvideo");
    if (wrap && this._stream) wrap.hidden = !show;
  }

  /** Nicht gescannte Spiele im aktuellen Fach: nachfragen, ob sie „ohne Standort“ werden. */
  _askClearMissing() {
    const inv = this._data.inventory;
    if (!inv?.missing.length) return false;
    const names = inv.missing.map((g) => g.name).join(", ");
    return confirm(this._t.invAskClear.replace("{n}", inv.missing.length).replace("{names}", names));
  }

  async _inventoryAction(action) {
    const s = this._scan, t = this._t;
    if (action === "begin") {
      const state = await this._call("start_inventory", { shelf: s.form.shelf.trim(), compartment: Number(s.form.compartment) || 1 }, true);
      if (state) { s.result = null; await this._load(); }
    } else if (action === "add") {
      const game = this._shelfGames().find((g) => g.name.toLowerCase() === s.addName.trim().toLowerCase());
      if (!game) { s.result = { error: t.noMatch }; this._renderScan(); return; }
      const res = await this._call("inventory_place", { bgg_id: game.bgg_id }, true);
      if (res) { s.result = res; s.addName = ""; }
    } else if (action === "undo") {
      await this._call("inventory_undo", {}, true);
      s.result = null;
    } else if (action === "next") {
      const res = await this._call("inventory_next", { clear_missing: this._askClearMissing() }, true);
      if (res) { s.result = null; if (res.cleared.length) this._showToast(t.invCleared.replace("{n}", res.cleared.length)); }
    } else if (action === "done") {
      const res = await this._call("stop_inventory", { clear_missing: this._askClearMissing() }, true);
      if (res) { this._closeScan(); this._showToast(t.invFinished); }
      return;
    }
    await this._load(); // zeigt Fach und Liste sofort aktuell
  }

  async _startCamera() {
    const wrap = this.shadowRoot.querySelector(".scanvideo");
    const video = wrap?.querySelector("video");
    if (!video) return;
    try {
      const wanted = ["ean_13", "ean_8", "upc_a", "upc_e"];
      const formats = (await BarcodeDetector.getSupportedFormats()).filter((f) => wanted.includes(f));
      if (!formats.length) return;
      this._stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      if (!this._scan) { this._stopCamera(); return; }
      video.srcObject = this._stream;
      await video.play();
      wrap.hidden = false;
      const detector = new BarcodeDetector({ formats });
      this._scanTimer = setInterval(async () => {
        if (!this._scan || video.readyState < 2) return;
        try {
          const codes = await detector.detect(video);
          if (codes.length) this._onCode(codes[0].rawValue, true);
        } catch (_) { /* einzelne Bilder dürfen scheitern */ }
      }, 250);
    } catch (err) {
      if (this._scan) { this._scan.result = { error: `${this._t.cameraError} (${err.name || err.message})` }; this._renderScan(); }
    }
  }

  _stopCamera() {
    clearInterval(this._scanTimer);
    this._scanTimer = null;
    this._stream?.getTracks().forEach((track) => track.stop());
    this._stream = null;
  }

  _closeScan() {
    this._stopCamera();
    this._scan = null;
    this.shadowRoot.getElementById("scan").innerHTML = "";
  }

  async _onCode(raw, fromCamera = false) {
    const s = this._scan, code = String(raw || "").trim();
    if (!s || !code) return;
    // Kamera liefert denselben Code mehrmals hintereinander -> nur einmal je 3 Sekunden
    if (code === s.last && Date.now() - s.lastAt < 3000) return;
    s.last = code; s.lastAt = Date.now();
    if (fromCamera) navigator.vibrate?.(60); // kurze Rückmeldung am Handy
    if (s.mode === "ean") {
      this._ui.edit.ean = code;
      this._closeScan();
      this._render();
      return;
    }
    const res = await this._call("scan_code", { code }, true);
    if (!this._scan) return;
    s.result = res || null;
    s.assign = "";
    if (s.mode === "inventory") await this._load();
    else this._renderScan();
  }

  async _assignScanned() {
    const s = this._scan, t = this._t;
    const game = this._data.games.find((g) => g.name.toLowerCase() === s.assign.trim().toLowerCase());
    if (!game) { s.result = { ...s.result, error: t.noMatch }; this._renderScan(); return; }
    if (await this._call("set_game", { bgg_id: game.bgg_id, ean: s.result.code })) {
      // In der Inventur kommt das Spiel nach dem Zuordnen gleich ins Fach
      s.result = s.mode === "inventory" && this._data.inventory
        ? await this._call("inventory_place", { bgg_id: game.bgg_id }, true)
        : { result: "assigned", name: game.name };
      s.assign = "";
      this._renderScan();
    }
  }

  // ---- Anleitungen (PDF) ----------------------------------------------------
  _rulebooks(bggId) {
    return (this._data.rulebooks || {})[bggId] || [];
  }

  async _rulesRequest(bggId, name, method, body) {
    const url = `/api/bgregal/rules/${bggId}${name ? `/${encodeURIComponent(name)}` : ""}`;
    try {
      const res = await this._hass.fetchWithAuth(url, { method, body });
      if (res.ok) return res;
      const err = await res.json().catch(() => ({}));
      this._showToast(err.message || `${res.status} ${res.statusText}`);
    } catch (err) {
      this._showToast(err.message || String(err));
    }
    return null;
  }

  async _uploadRules(bggId, files) {
    if (!files.length) return;
    const body = new FormData();
    for (const f of files) body.append("file", f, f.name);
    this._ui.rbUploading = true;
    this._render();
    const res = await this._rulesRequest(bggId, null, "POST", body);
    this._ui.rbUploading = false;
    if (res) this._showToast(this._t.uploaded);
    else this._render();
  }

  async _openRules(bggId, name) {
    // Fenster sofort öffnen (sonst blockiert der Browser das Popup), PDF mit Anmeldung nachladen
    const win = window.open("", "_blank");
    const res = await this._rulesRequest(bggId, name, "GET");
    if (!res) { win?.close(); return; }
    const url = URL.createObjectURL(await res.blob());
    if (win) win.location.href = url;
    else window.location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 5 * 60 * 1000);
  }

  async _openGame(bggId) {
    const g = this._games.get(bggId);
    if (!g) return;
    this._ui.game = bggId;
    this._ui.gamePlays = null;
    this._ui.lendTo = "";
    this._ui.edit = {
      shelf: g.shelf, compartment: g.compartment ?? "", in_base: g.in_base, nfc_tag: g.nfc_tag,
      light_profile: g.light_profile, playlist: g.playlist, manual_url: g.manual_url, ean: g.ean,
      links: g.links.map((l) => ({ ...l })),
    };
    this._render();
    try {
      const res = await this._hass.callWS({ type: "bgregal/game", bgg_id: bggId });
      if (this._ui.game === bggId) { this._ui.gamePlays = res.plays; this._render(); }
    } catch (_) {
      this._ui.gamePlays = [];
      this._render();
    }
  }
}

const BARCODE_ICON = `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor"
  d="M2 5h2v14H2zm3 0h1v14H5zm2 0h3v14H7zm4 0h1v14h-1zm3 0h2v14h-2zm3 0h1v14h-1zm2 0h3v14h-3z"/></svg>`;

function elapsed(started) {
  const sec = Math.max(0, Math.floor((Date.now() - new Date(started)) / 1000));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function duration(start, end) {
  return Math.max(0, Math.round((new Date(end || Date.now()) - new Date(start)) / 60000));
}

function monthLabel(key, t) {
  const [y, m] = key.split("-").map(Number);
  return `${t.monthsShort[m - 1]}${m === 1 ? ` ${String(y).slice(2)}` : ""}`;
}

function nextFriday() {
  const d = new Date();
  d.setDate(d.getDate() + ((5 - d.getDay() + 7) % 7 || 7));
  d.setHours(19, 0, 0, 0);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const CSS = `
  :host { display: block; min-height: 100vh; background: var(--primary-background-color); color: var(--primary-text-color);
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); --wood: #c8a26a; --radius: 12px; }
  * { box-sizing: border-box; }
  header { display: flex; align-items: center; gap: 12px; height: 56px; padding: 0 16px;
           background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); }
  header h1 { font-size: 20px; font-weight: 500; margin: 0; }
  header .sync { margin-left: auto; font-size: 12px; color: inherit; opacity: .8; }
  header .icon { color: inherit; }
  nav { display: flex; gap: 4px; overflow-x: auto; padding: 8px 12px; background: var(--card-background-color);
        border-bottom: 1px solid var(--divider-color); scrollbar-width: thin; }
  main { max-width: 1200px; margin: 0 auto; padding: 16px; }
  button, .button { font: inherit; font-size: 14px; border-radius: 8px; padding: 8px 14px; cursor: pointer;
           border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color);
           text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
  button:disabled { opacity: .45; cursor: default; }
  .button.disabled { opacity: .5; pointer-events: none; }
  button.primary, .button.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  button.danger { color: var(--error-color); }
  button.icon { border: 0; background: none; font-size: 20px; padding: 6px; }
  button.icon.small { font-size: 12px; padding: 2px 6px; }
  button.link { border: 0; background: none; color: var(--primary-color); padding: 4px 0; }
  .tab { border: 0; background: none; white-space: nowrap; border-radius: 20px; }
  .tab.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success-color, #43a047); }
  .dot.finished { background: var(--warning-color, #ffa000); }
  .count { font-size: 11px; background: var(--error-color); color: #fff; border-radius: 10px; padding: 0 6px; }
  input, select, textarea { font: inherit; font-size: 14px; padding: 8px 10px; border-radius: 8px; width: 100%;
           border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
  input[type=checkbox] { width: auto; }
  .toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 16px; }
  .toolbar input { max-width: 320px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chips.center, .session .chips { justify-content: center; }
  .chip { border-radius: 16px; padding: 4px 12px; font-size: 13px; }
  .chip.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .muted { color: var(--secondary-text-color); }
  .small { font-size: 12px; }
  .empty { text-align: center; padding: 48px 16px; color: var(--secondary-text-color); }
  .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0; }
  .row.center { justify-content: center; }
  .row input { flex: 1; min-width: 140px; width: auto; }
  .card { background: var(--card-background-color); border-radius: var(--radius); padding: 16px; margin-bottom: 16px;
          box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12)); }
  .card h2, .billy h2 { font-size: 18px; margin: 0 0 8px; }
  h3 { font-size: 15px; margin: 20px 0 8px; }
  .form { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
  .form label, label.block { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
  label.check { flex-direction: row; align-items: center; gap: 8px; }
  .billy { margin-bottom: 24px; }
  .room { margin-bottom: 8px; }
  h2.roomname { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em;
                color: var(--secondary-text-color); margin: 24px 0 8px; padding-bottom: 4px; border-bottom: 1px solid var(--divider-color); }
  .shead { display: flex; flex-wrap: wrap; gap: 12px; align-items: baseline; }
  .shead h2 { margin: 0 0 8px; }
  .tile.hit { outline: 3px solid var(--accent-color, #ff9800); outline-offset: 1px;
              background: color-mix(in srgb, var(--accent-color, #ff9800) 14%, var(--card-background-color)); }
  .tile.dim, .tile.dim.lent { opacity: .3; }
  .tile.dim:hover, .tile.dim.lent:hover { opacity: .8; }
  .moves { display: inline-flex; gap: 2px; margin-left: 6px; vertical-align: middle; }
  .moves button { border: 1px solid var(--divider-color); border-radius: 6px; padding: 2px 7px; font-size: 12px;
                  color: var(--primary-color); background: var(--card-background-color); }
  .tilewrap { display: flex; flex-direction: column; gap: 4px; }
  .tilewrap .moves { margin: 0; justify-content: center; }
  h2.roomname .moves { text-transform: none; letter-spacing: 0; }
  .hitcount { font-size: 13px; font-weight: 500; color: var(--accent-color, #ff9800); }
  .hitcount.none { color: var(--error-color); }
  .small-dialog { width: min(480px, 100%); }
  .scanvideo { position: relative; margin: 8px 0; border-radius: 10px; overflow: hidden; background: #000; }
  .scanvideo video { width: 100%; display: block; max-height: 50vh; object-fit: cover; }
  .scanvideo .aim { position: absolute; left: 12%; right: 12%; top: 42%; height: 16%; border: 2px solid rgba(255,255,255,.8); border-radius: 6px; }
  .scan-overlay { z-index: 15; }
  p.ok { color: var(--success-color, #43a047); font-weight: 500; }
  p.warn { color: var(--error-color); }
  .invhead { font-size: 22px; font-weight: 500; margin: 4px 0 8px; }
  ol.invlist { margin: 0; padding-left: 0; list-style: none; max-height: 30vh; overflow-y: auto; }
  ol.invlist li { padding: 3px 0; border-bottom: 1px solid var(--divider-color); font-size: 14px; }
  .fach { border-bottom: 6px solid var(--wood); padding: 8px 0 4px; margin-bottom: 8px; }
  .fnum { font-size: 12px; color: var(--secondary-text-color); margin-bottom: 6px; }
  .boxes { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 10px; }
  .tile { flex-direction: column; align-items: stretch; text-align: left; padding: 8px; gap: 4px; border-radius: 10px; height: 100%; }
  .tile img, .tile .noimg { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; background: var(--divider-color);
                            display: grid; place-items: center; font-size: 32px; }
  .tile.lent { opacity: .6; }
  .tname { font-weight: 500; font-size: 13px; line-height: 1.25; }
  .tfacts { font-size: 12px; color: var(--secondary-text-color); }
  .tags { display: flex; flex-wrap: wrap; gap: 4px; }
  .tag { font-size: 11px; padding: 1px 6px; border-radius: 6px; background: var(--divider-color); }
  .tag.warn { background: var(--warning-color, #ffa000); color: #000; }
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: flex-start; justify-content: center;
             overflow-y: auto; padding: 32px 12px; z-index: 10; }
  .dialog { position: relative; background: var(--card-background-color); border-radius: var(--radius); padding: 20px;
            width: min(760px, 100%); }
  .dialog.qr { width: min(420px, 100%); text-align: center; }
  .dialog .close { position: absolute; top: 8px; right: 8px; }
  .ghead { display: flex; gap: 16px; flex-wrap: wrap; }
  .ghead img { width: 140px; height: 140px; object-fit: cover; border-radius: 10px; }
  .ghead > div { flex: 1; min-width: 220px; }
  .kpis { display: flex; flex-wrap: wrap; gap: 16px; margin: 8px 0; }
  .kpis.tiles { margin: 0 0 16px; }
  .kpi { background: var(--card-background-color); border-radius: var(--radius); padding: 12px 16px; min-width: 120px; flex: 1;
         display: flex; flex-direction: column; box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12)); }
  .kpi b { font-size: 26px; }
  .kpi span { font-size: 12px; color: var(--secondary-text-color); }
  ul.plain, ol.plain { padding-left: 20px; margin: 0; }
  ul.plain li, ol.plain li, ul.plays li { margin: 4px 0; }
  ul.plays { padding-left: 18px; margin: 0; font-size: 13px; }
  a { color: var(--primary-color); }
  .session { text-align: center; }
  .session .cover, .suggestion .cover { width: 120px; height: 120px; object-fit: cover; border-radius: 10px; }
  .big { font-size: 40px; font-weight: 300; font-variant-numeric: tabular-nums; margin: 8px 0; }
  .suggestion { display: flex; gap: 16px; flex-wrap: wrap; align-items: center; }
  .suggestion .big { font-size: 24px; font-weight: 500; }
  .big-btn { font-size: 18px; padding: 14px 24px; }
  .order { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin: 8px 0; }
  .pick { margin: 12px 0; }
  .kpis { justify-content: inherit; }
  .session .kpis { justify-content: center; font-size: 18px; }
  table.scores { width: 100%; border-collapse: collapse; margin: 12px 0; text-align: left; }
  table.scores td, table.scores th { padding: 6px; border-bottom: 1px solid var(--divider-color); }
  table.scores th { font-size: 12px; color: var(--secondary-text-color); font-weight: 500; }
  table.scores input[inputmode] { max-width: 100px; }
  .qrbox svg { width: 100%; max-width: 320px; height: auto; background: #fff; border-radius: 8px; }
  ol.ranking { padding-left: 20px; }
  ol.ranking li { margin: 4px 0; }
  ol.ranking li > * { margin-right: 8px; }
  .past { opacity: .6; }
  .phead { display: flex; flex-wrap: wrap; gap: 12px; align-items: baseline; }
  .player .row { margin: 4px 0 0; gap: 16px; }
  button.link.muted { color: var(--secondary-text-color); }
  .hidden-players summary { cursor: pointer; font-weight: 500; }
  ul.hidden-list { list-style: none; padding: 0; margin: 8px 0 0; }
  ul.hidden-list li { display: flex; gap: 12px; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--divider-color); }
  ul.hidden-list li span:first-child { flex: 1; }
  .bars { display: flex; gap: 6px; align-items: flex-end; height: 180px; padding-top: 16px; }
  .bar { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; }
  .bar .fill { width: 100%; max-width: 36px; background: var(--primary-color); border-radius: 4px 4px 0 0; min-height: 1px; }
  .bar .val { font-size: 11px; color: var(--secondary-text-color); }
  .bar .lbl { font-size: 11px; color: var(--secondary-text-color); margin-top: 4px; white-space: nowrap; }
  ul.wish { list-style: none; padding: 0; margin: 0; }
  ul.wish li { display: flex; gap: 10px; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--divider-color); }
  ul.wish img { width: 40px; height: 40px; object-fit: cover; border-radius: 6px; }
  ul.loans { list-style: none; padding: 0; margin: 0; }
  ul.loans li { display: grid; grid-template-columns: 2fr 1fr 1.5fr auto; gap: 8px; align-items: center; padding: 8px 0;
                border-bottom: 1px solid var(--divider-color); }
  ul.loans li.overdue span:first-of-type { color: var(--error-color); font-weight: 500; }
  .lead { font-size: 15px; }
  .toast { position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%); background: #323232; color: #fff;
           padding: 12px 20px; border-radius: 8px; z-index: 20; max-width: 90vw; }
  @media (max-width: 600px) {
    main { padding: 12px; }
    .boxes { grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); }
    ul.loans li { grid-template-columns: 1fr 1fr; }
    .big { font-size: 32px; }
  }
`;

customElements.define("bgregal-panel", BgRegalPanel);
