/* BGRegal – gemeinsame Texte (Deutsch/Englisch) und Hilfsfunktionen für Panel und Kachel. */

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function fmtDate(value, withTime = false) {
  if (!value) return "";
  const d = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  if (isNaN(d)) return value;
  const lang = document.documentElement.lang?.startsWith("de") ? "de-DE" : undefined;
  return withTime
    ? d.toLocaleString(lang, { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString(lang, { day: "2-digit", month: "2-digit", year: "2-digit" });
}

export function location(g, t) {
  if (!g) return "";
  const shelf = g.shelf || "", fach = g.compartment;
  if (shelf && fach) return `${shelf}, ${t.compartment} ${fach}`;
  return shelf || (fach ? `${t.compartment} ${fach}` : "");
}

export const naturalCompare = (a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });

/** „Susi 10 🏆, Anna 8“ – Spieler einer Partie, man selbst zuerst. */
export function playersText(players, me) {
  const mine = (p) => (p.username || "").toLowerCase() === (me || "").toLowerCase();
  return [...players].sort((a, b) => mine(b) - mine(a))
    .map((p) => `${p.name}${p.score ? ` ${p.score}` : ""}${p.win ? " 🏆" : ""}`).join(", ");
}

const MODES_DE = { cooperative: "Kooperativ", competitive: "Wettkampf", semi: "Semi-kooperativ" };
const MODES_EN = { cooperative: "Cooperative", competitive: "Competitive", semi: "Semi-cooperative" };
const TYPES_DE = { family: "Familie", strategy: "Strategie", party: "Party", abstract: "Abstrakt", thematic: "Thematisch", wargame: "Kriegsspiel", children: "Kinder" };
const TYPES_EN = { family: "Family", strategy: "Strategy", party: "Party", abstract: "Abstract", thematic: "Thematic", wargame: "Wargame", children: "Children" };

export const STRINGS = {
  de: {
    tabs: { shelf: "Regal", session: "Sitzung", suggest: "Vorschlag", evenings: "Spieleabende", players: "Mitspieler",
            stats: "Statistik", shame: "Pile of Shame", wishlist: "Wunschliste", loans: "Verliehen" },
    filters: { all: "Alle", lent: "Verliehen", nolocation: "Ohne Standort", expansions: "Erweiterungen" },
    modes: MODES_DE, types: TYPES_DE,
    monthsShort: ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
    loading: "Lädt …", lastSync: "Sync:", syncNow: "Jetzt synchronisieren", syncStarted: "Sync läuft …",
    search: "Spiel suchen …", noMatch: "Kein Spiel passt.", noGames: "Noch keine Spiele – der erste Sync läuft vermutlich noch.",
    neverPlayed: "nie gespielt", lentTo: "verliehen an", expansion: "Erweiterung", exp: "Erw.",
    shelf: "Regal", compartment: "Fach", emptyCompartment: "leer", noCompartment: "ohne Fach", noLocation: "Ohne Standort",
    players: "Spieler", min: "Min", weight: "Komplexität", rating: "Bewertung", since: "seit",
    giveBack: "Zurückgegeben", borrower: "An wen?", lend: "Verleihen", close: "Schließen", expands: "Erweitert",
    playsShort: "Partien", playOne: "Partie", games: "Spiele", lastPlay: "Letzte Partie", startSession: "Sitzung starten", manual: "Anleitung",
    assignments: "Zuordnungen", inBase: "Liegt im Basisspiel", inBaseShort: "im Basisspiel", nfc: "NFC-Tag",
    takeScanned: "Gescannten übernehmen", light: "Lichtprofil", sound: "Soundprofil (Spotify-Playlist)",
    noPlayerHint: "Für das Soundprofil in den Optionen der Integration ein Wiedergabegerät wählen.",
    save: "Speichern", saved: "Gespeichert", loan: "Verleih", expansions: "Erweiterungen", recentPlays: "Letzte Partien",
    copyLink: "Link kopieren", copied: "Link kopiert",
    noSession: "Gerade läuft keine Sitzung. Starte eine im Regal, per NFC-Tag oder über einen Vorschlag.",
    round: "Runde", turn: "Am Zug", nextPlayer: "Nächster Spieler", nextRound: "Nächste Runde",
    orderHint: "Tippe die Spieler in Zugreihenfolge an.", cancel: "Abbrechen", changeOrder: "Reihenfolge ändern",
    setOrder: "Reihenfolge festlegen", endSession: "Beenden", discard: "Verwerfen",
    finishedText: "Die Partie ist abgeschlossen. Übernimm sie per QR-Code in BG Stats.", showQr: "QR-Code zeigen", done: "Fertig",
    whoPlayed: "Wer hat mitgespielt?", me: "ich", name: "Name", add: "Hinzufügen", player: "Spieler", score: "Punkte",
    winner: "Gewinner", autoWinner: "Ohne Haken gewinnt die höchste Punktzahl.", note: "Notiz", finish: "Abschließen & QR-Code",
    toBgStats: "In BG Stats übernehmen", openBgStats: "In BG Stats öffnen",
    qrHint: "Mit dem Handy scannen: BG Stats öffnet die Partie zum Speichern. BG Stats überträgt sie zu BGG, beim nächsten Sync ist sie hier.",
    confirmDiscard: "Sitzung wirklich verwerfen?", confirmDelete: "Wirklich löschen?",
    mode: "Modus", any: "Egal", type: "Typ", maxTime: "Max. Dauer", attendees: "Wer spielt mit?", suggestBtn: "Vorschlagen",
    goGet: "Hol es aus dem Regal:", howAbout: "Wie wäre es mit", yes: "Ja", no: "Nein", more: "weitere", back: "Zurück",
    noSuggestion: "Kein (weiteres) Spiel passt zu den Filtern.",
    noGuests: "keine Gäste", remove: "Entfernen", addGame: "Spiel hinzufügen", voteLink: "Abstimm-Link & QR-Code", delete: "Löschen",
    newEvening: "Neuer Spieleabend", gameNight: "Spieleabend", title: "Titel", start: "Beginn", guests: "Gäste", create: "Anlegen",
    eveningHint: "BGRegal wählt passende Spiele zur Abstimmung aus. Gäste stimmen über den Link ab – ohne Home-Assistant-Konto.",
    openVote: "Abstimmseite öffnen",
    voteHint: "Den Link oder QR-Code an die Gäste geben. Im WLAN klappt das immer, von unterwegs nur, wenn Home Assistant von außen erreichbar ist.",
    noEvenings: "Noch keine Spieleabende geplant.",
    bggUser: "BGG-Benutzer", dislikes: "Mag nicht", noDislikes: "keine Abneigungen", edit: "Bearbeiten",
    newPlayer: "Neuer Mitspieler", playersHint: "Mitspieler aus deinen BGG-Partien erscheinen automatisch.", noPlayers: "Noch keine Mitspieler.",
    hide: "Ausblenden", unhide: "Einblenden", hiddenPlayers: "Ausgeblendete Mitspieler",
    hiddenHint: "Erscheinen nicht in Auswahllisten (Vorschlag, Spieleabend, Sitzung, Verleih). Partien und Statistik bleiben.",
    hiddenToast: "{name} ausgeblendet – unten unter „Ausgeblendete Mitspieler“ wieder einblenden.",
    playsTotal: "Partien gesamt", thisMonth: "diesen Monat", perMonth: "Partien pro Monat", top: "Meistgespielt",
    longUnplayed: "Lange nicht gespielt", longUnplayedHint: "Letzte Partie vor mindestens {n} Monaten.",
    shameLead: "{n} eigene Spiele wurden noch nie gespielt.", shameEmpty: "Kein Pile of Shame – alles gespielt!",
    newExpansions: "Neue Erweiterungen zu deinen Spielen", for: "für", seen: "Gesehen",
    prio1: "Muss ich haben", prio2: "Liebend gern", prio3: "Gern", prio4: "Überlege", prio5: "Lieber nicht",
    wishEmpty: "Die Wunschliste auf BGG ist leer.", days: "Tage",
    loansHint: "Nach {n} Tagen erinnert BGRegal an ein verliehenes Spiel.", noLoans: "Nichts verliehen.",
    card: { plays: "Partien", lastPlay: "Letzte Partie", start: "Starten", running: "läuft", none: "Kein Spiel gewählt", open: "BGRegal öffnen" },
  },
  en: {
    tabs: { shelf: "Shelf", session: "Session", suggest: "Suggest", evenings: "Game nights", players: "Players",
            stats: "Stats", shame: "Pile of Shame", wishlist: "Wishlist", loans: "Lent out" },
    filters: { all: "All", lent: "Lent out", nolocation: "No location", expansions: "Expansions" },
    modes: MODES_EN, types: TYPES_EN,
    monthsShort: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    loading: "Loading …", lastSync: "Sync:", syncNow: "Sync now", syncStarted: "Syncing …",
    search: "Search games …", noMatch: "No game matches.", noGames: "No games yet – the first sync is probably still running.",
    neverPlayed: "never played", lentTo: "lent to", expansion: "Expansion", exp: "exp.",
    shelf: "Shelf", compartment: "Compartment", emptyCompartment: "empty", noCompartment: "no compartment", noLocation: "No location",
    players: "players", min: "min", weight: "Weight", rating: "Rating", since: "since",
    giveBack: "Returned", borrower: "Lend to?", lend: "Lend", close: "Close", expands: "Expands",
    playsShort: "plays", playOne: "play", games: "Games", lastPlay: "Last play", startSession: "Start session", manual: "Rules",
    assignments: "Assignments", inBase: "Stored in base game", inBaseShort: "in base game", nfc: "NFC tag",
    takeScanned: "Use scanned tag", light: "Light profile", sound: "Sound profile (Spotify playlist)",
    noPlayerHint: "Choose a media player in the integration options to use sound profiles.",
    save: "Save", saved: "Saved", loan: "Loan", expansions: "Expansions", recentPlays: "Recent plays",
    copyLink: "Copy link", copied: "Link copied",
    noSession: "No session running. Start one from the shelf, with an NFC tag or from a suggestion.",
    round: "Round", turn: "Turn", nextPlayer: "Next player", nextRound: "Next round",
    orderHint: "Tap the players in turn order.", cancel: "Cancel", changeOrder: "Change order",
    setOrder: "Set turn order", endSession: "End", discard: "Discard",
    finishedText: "The play is complete. Import it into BG Stats with the QR code.", showQr: "Show QR code", done: "Done",
    whoPlayed: "Who played?", me: "me", name: "Name", add: "Add", player: "Player", score: "Score",
    winner: "Winner", autoWinner: "Without a tick, the highest score wins.", note: "Note", finish: "Complete & QR code",
    toBgStats: "Import into BG Stats", openBgStats: "Open in BG Stats",
    qrHint: "Scan with your phone: BG Stats opens the play for saving. BG Stats syncs it to BGG, and it appears here after the next sync.",
    confirmDiscard: "Really discard the session?", confirmDelete: "Really delete?",
    mode: "Mode", any: "Any", type: "Type", maxTime: "Max. time", attendees: "Who's playing?", suggestBtn: "Suggest",
    goGet: "Get it from the shelf:", howAbout: "How about", yes: "Yes", no: "No", more: "more", back: "Back",
    noSuggestion: "No (more) games match the filters.",
    noGuests: "no guests", remove: "Remove", addGame: "Add game", voteLink: "Voting link & QR code", delete: "Delete",
    newEvening: "New game night", gameNight: "Game night", title: "Title", start: "Start", guests: "Guests", create: "Create",
    eveningHint: "BGRegal picks matching games to vote on. Guests vote via the link – no Home Assistant account needed.",
    openVote: "Open voting page",
    voteHint: "Share the link or QR code with your guests. It always works on your Wi-Fi; from outside only if Home Assistant is reachable externally.",
    noEvenings: "No game nights planned yet.",
    bggUser: "BGG user", dislikes: "Dislikes", noDislikes: "no dislikes", edit: "Edit",
    newPlayer: "New player", playersHint: "Players from your BGG plays appear automatically.", noPlayers: "No players yet.",
    hide: "Hide", unhide: "Show again", hiddenPlayers: "Hidden players",
    hiddenHint: "Not offered in selection lists (suggestion, game night, session, loans). Plays and stats stay.",
    hiddenToast: "{name} hidden – show again below under “Hidden players”.",
    playsTotal: "Total plays", thisMonth: "this month", perMonth: "Plays per month", top: "Most played",
    longUnplayed: "Not played for a long time", longUnplayedHint: "Last play at least {n} months ago.",
    shameLead: "{n} of your games have never been played.", shameEmpty: "No pile of shame – everything played!",
    newExpansions: "New expansions for your games", for: "for", seen: "Seen",
    prio1: "Must have", prio2: "Love to have", prio3: "Like to have", prio4: "Thinking about it", prio5: "Don't buy",
    wishEmpty: "Your BGG wishlist is empty.", days: "days",
    loansHint: "BGRegal reminds you about a lent game after {n} days.", noLoans: "Nothing lent out.",
    card: { plays: "Plays", lastPlay: "Last play", start: "Start", running: "running", none: "No game selected", open: "Open BGRegal" },
  },
};
