"use strict";
(() => {
  const labels = {
    en: {
      eyebrow: "YOUR LOCAL PRODUCT MIRROR",
      records: "Published records", recordHint: "All available datasets · metadata count", storage: "MongoDB storage", storageHint: "Data + indexes, including ongoing imports",
      nextCheck: "Next synchronization", datasets: "Available datasets", live: "LIVE STATUS", activity: "Synchronization", transfer: "Download", datasetHeading: "Your datasets", refresh: "Refresh display",
      lookupEyebrow: "LOCAL LOOKUP", lookup: "Find a product", lookupHint: "Search by EAN across all four datasets. Leading zeros are preserved. No data is changed.",
      eanLabel: "EAN / barcode", scope: "Dataset", all: "All datasets", food: "Food", beauty: "Beauty", petfood: "Pet food", product: "Other products", search: "Search", brand: "Brand", quantity: "Package quantity",
      ready: "Ready", pending: "Pending", full_import: "Full import", delta_import: "Delta import", error: "Source error", connected: "Connected", disconnected: "Unavailable",
      fullAt: "Last full import", checkedAt: "Last delta check", sourceAt: "Source export", nextFull: "Full refresh due", noDate: "Not yet recorded", firstImport: "First import pending",
      countHint: "Published dataset · metadata count", noCode: "Without barcode at full import", allCurrent: "Latest checks successful", incomplete: "Some datasets are still missing", sourceErrors: "At least one check failed", syncInProgress: "Synchronization in progress",
      idle: "The service is waiting for its next synchronization.", running: "Synchronizing: {name}", stopped: "Synchronization is stopped.", unknown: "No schedule recorded yet. The worker records it on its next run.", stale: "The worker has not reported back on time. Check the service logs.",
      afterCycle: "Scheduled after this cycle finishes", noSchedule: "Not scheduled", overdue: "Due now", inTime: "In {time}", days: "d", hours: "h", minutes: "min", seconds: "s",
      processed: "{count} records processed", rate: "{count} records/s", unknownSize: "Total size unknown", finishing: "Download complete · finishing processing", updated: "Updated {time}",
      lookupBusy: "Searching the local datasets…", notFound: "No product found in the selected datasets.", notReady: "Not all selected datasets are available yet. Try a specific imported dataset.", databaseError: "The database is currently unavailable.", invalid: "Enter a barcode using digits only.", requestError: "The request failed. Please try again.",
      foundTime: "Local lookup: {ms} ms", noName: "Product without a name", noValue: "Not specified", connectionError: "Status could not be refreshed. Previously loaded values may be out of date.", loading: "Connecting…"
    },
    de: {
      eyebrow: "DEIN LOKALER PRODUKTBESTAND",
      records: "Veröffentlichte Datensätze", recordHint: "Alle verfügbaren Bestände · Metadatenzählung", storage: "MongoDB-Speicher", storageHint: "Daten + Indizes, inklusive laufender Importe",
      nextCheck: "Nächster Abgleich", datasets: "Verfügbare Bestände", live: "LIVE-STATUS", activity: "Synchronisierung", transfer: "Download", datasetHeading: "Deine Datenbestände", refresh: "Anzeige aktualisieren",
      lookupEyebrow: "LOKALE ABFRAGE", lookup: "Produkt finden", lookupHint: "Per EAN in allen vier Beständen suchen. Führende Nullen bleiben erhalten. Es werden keine Daten verändert.",
      eanLabel: "EAN / Barcode", scope: "Datenbestand", all: "Alle Bestände", food: "Lebensmittel", beauty: "Kosmetik", petfood: "Tiernahrung", product: "Sonstige Produkte", search: "Suchen", brand: "Marke", quantity: "Packungsmenge",
      ready: "Bereit", pending: "Ausstehend", full_import: "Vollimport", delta_import: "Delta-Import", error: "Quellenfehler", connected: "Verbunden", disconnected: "Nicht erreichbar",
      fullAt: "Letzter Vollimport", checkedAt: "Letzte Delta-Prüfung", sourceAt: "Stand des Exports", nextFull: "Vollabgleich fällig", noDate: "Noch nicht erfasst", firstImport: "Erstimport ausstehend",
      countHint: "Veröffentlichter Bestand · Metadatenzählung", noCode: "Ohne Barcode beim Vollimport", allCurrent: "Letzte Prüfungen erfolgreich", incomplete: "Einzelne Bestände fehlen noch", sourceErrors: "Mindestens eine Prüfung fehlgeschlagen", syncInProgress: "Synchronisierung läuft",
      idle: "Der Dienst wartet auf den nächsten Abgleich.", running: "Abgleich läuft: {name}", stopped: "Die Synchronisierung ist angehalten.", unknown: "Noch kein Termin gespeichert. Der Hintergrunddienst erfasst ihn beim nächsten Lauf.", stale: "Der Hintergrunddienst hat sich nicht rechtzeitig zurückgemeldet. Bitte die Dienst-Logs prüfen.",
      afterCycle: "Wird nach diesem Durchlauf geplant", noSchedule: "Nicht geplant", overdue: "Jetzt fällig", inTime: "In {time}", days: "T", hours: "Std.", minutes: "Min.", seconds: "Sek.",
      processed: "{count} Datensätze verarbeitet", rate: "{count} Datensätze/s", unknownSize: "Gesamtgröße unbekannt", finishing: "Download vollständig · Verarbeitung wird abgeschlossen", updated: "Aktualisiert {time}",
      lookupBusy: "Die lokalen Bestände werden durchsucht…", notFound: "Kein Produkt in den ausgewählten Beständen gefunden.", notReady: "Noch nicht alle ausgewählten Bestände sind verfügbar. Versuche einen bestimmten bereits importierten Bestand.", databaseError: "Die Datenbank ist momentan nicht erreichbar.", invalid: "Bitte einen Barcode nur aus Ziffern eingeben.", requestError: "Die Anfrage ist fehlgeschlagen. Bitte erneut versuchen.",
      foundTime: "Lokale Abfrage: {ms} ms", noName: "Produkt ohne Namen", noValue: "Nicht angegeben", connectionError: "Der Status konnte nicht aktualisiert werden. Die zuletzt geladenen Werte können veraltet sein.", loading: "Verbinde…"
    }
  };
  Object.assign(labels.en, {
    syncNow: "Synchronize now", settings: "Settings", save: "Save", cancel: "Cancel",
    gapPolicy: "When delta coverage is incomplete", gapContinue: "Apply available deltas", gapPause: "Pause the affected dataset",
    gapHelp: "Existing products remain available. Continuing applies newer changes but cannot recover missing changes. A returning delta can close the gap; otherwise a full import is needed.",
    fullPolicy: "Full imports", fullConfirm: "Only after confirmation (default)", fullAutomatic: "Allow automatic full imports",
    fullInterval: "Regular full refresh interval in days (0 = disabled)",
    fullHelp: "0 disables regular full refreshes. An optional refresh reconciles deletions not included in deltas. With confirmation enabled, a due date is shown; it does not start an import.",
    settingsIntro: "Choose how your product datasets stay up to date.", close: "Close",
    policyHelp: "By default, every full import needs your confirmation, including the first import. Delta checks continue automatically. Automatic full imports require explicit consent.",
    fullIntro: "Rebuild one dataset while keeping it available.",
    importDownload: "Download and import", importDownloadHelp: "The download is decompressed as it arrives and written to a separate new dataset. The current dataset remains readable.",
    importVerify: "Verify the complete import", importVerifyHelp: "The new dataset is published only after the download and all database writes succeed and integrity checks pass.",
    importSwitch: "Switch, then remove the old dataset", importSwitchHelp: "The API switches to the new dataset first. Only then is the old copy removed. Other datasets remain unchanged.",
    autoConsent: "I allow full imports without asking for initial datasets, delta gaps and enabled intervals. They can take hours and temporarily require space for two copies.",
    fullTitle: "Confirm full import", fullWarning: "This can take hours and temporarily needs space for both datasets. If the import fails before the switch, the old dataset is retained.",
    fullStart: "Start full import", fullButton: "Full import…", noFullSchedule: "Regular full refresh disabled",
    needs_full_import: "Approval needed", partial: "Delta gap", gap_paused: "Updates paused",
    gapWarning: "Missing coverage: {ranges}. Existing data remains available.", gapContinuing: "Available deltas continue to be applied.", gapIsPaused: "Newer deltas are paused for this dataset.",
    fullRequired: "Full import awaits confirmation: {reasons}.", initial: "initial import", gap: "delta gap", scheduled: "refresh interval reached",
    queued: "Queued", runningJob: "Running", syncQueued: "Synchronization requested. The background worker will process it.",
    fullQueued: "Full import confirmed and queued.", saved: "Settings saved. They apply on the next dataset check.", controlError: "Request failed. Refresh the display and try again.",
    gapOverview: "Available, with incomplete delta coverage", jobFailed: "Last request failed: {error}"
  });
  Object.assign(labels.de, {
    syncNow: "Daten jetzt abgleichen", settings: "Einstellungen", save: "Speichern", cancel: "Abbrechen",
    gapPolicy: "Bei einer Delta-Lücke", gapContinue: "Verfügbare Deltas fortsetzen", gapPause: "Betroffenen Bestand pausieren",
    gapHelp: "Vorhandene Produkte bleiben abfragbar. Beim Fortsetzen werden neuere Änderungen übernommen; fehlende Änderungen bleiben offen. Eine wieder verfügbare Delta-Datei kann die Lücke schließen, andernfalls ist ein Vollimport nötig.",
    fullPolicy: "Vollimporte", fullConfirm: "Nur nach Bestätigung (Standard)", fullAutomatic: "Automatische Vollimporte erlauben",
    fullInterval: "Regelmäßiger Vollabgleich in Tagen (0 = deaktiviert)",
    fullHelp: "0 deaktiviert regelmäßige Vollabgleiche. Ein optionaler Vollabgleich übernimmt Löschungen, die in Deltas fehlen. Bei Bestätigungspflicht wird die Fälligkeit nur angezeigt; ein Import startet dadurch nicht.",
    settingsIntro: "Lege fest, wie deine Produktbestände aktuell bleiben.", close: "Schließen",
    policyHelp: "Standardmäßig benötigt jeder Vollimport deine Bestätigung, auch der Erstimport. Delta-Prüfungen laufen automatisch weiter. Automatische Vollimporte erfordern eine ausdrückliche Zustimmung.",
    fullIntro: "Einen Bestand neu aufbauen und weiter abfragen können.",
    importDownload: "Herunterladen und importieren", importDownloadHelp: "Der Download wird laufend entpackt und in einen separaten neuen Bestand geschrieben. Der bisherige Bestand bleibt abfragbar.",
    importVerify: "Vollständigen Import prüfen", importVerifyHelp: "Erst wenn Download und alle Datenbankzugriffe erfolgreich abgeschlossen sind und die Integritätsprüfungen bestehen, wird der neue Bestand freigegeben.",
    importSwitch: "Umschalten, dann alten Bestand entfernen", importSwitchHelp: "Zuerst nutzt die API den neuen Bestand. Erst danach wird die alte Kopie entfernt. Die anderen Bestände bleiben unverändert.",
    autoConsent: "Ich erlaube Vollimporte ohne Rückfrage bei Erstimporten, Delta-Lücken und aktivierten Intervallen. Sie können Stunden dauern und vorübergehend Platz für zwei Bestände benötigen.",
    fullTitle: "Vollimport bestätigen", fullWarning: "Das kann Stunden dauern und benötigt vorübergehend Platz für beide Bestände. Scheitert der Import vor dem Umschalten, bleibt der alte Bestand erhalten.",
    fullStart: "Vollimport starten", fullButton: "Vollimport …", noFullSchedule: "Regelmäßiger Vollabgleich deaktiviert",
    needs_full_import: "Bestätigung erforderlich", partial: "Delta-Lücke", gap_paused: "Aktualisierung pausiert",
    gapWarning: "Fehlender Zeitraum: {ranges}. Vorhandene Daten bleiben verfügbar.", gapContinuing: "Verfügbare Deltas werden weiter eingespielt.", gapIsPaused: "Neuere Deltas sind für diesen Bestand pausiert.",
    fullRequired: "Vollimport wartet auf Bestätigung: {reasons}.", initial: "Erstimport", gap: "Delta-Lücke", scheduled: "Intervall erreicht",
    queued: "Vorgemerkt", runningJob: "Läuft", syncQueued: "Datenabgleich angefordert. Der Hintergrunddienst übernimmt ihn.",
    fullQueued: "Vollimport bestätigt und vorgemerkt.", saved: "Einstellungen gespeichert. Sie gelten ab der nächsten Bestandsprüfung.", controlError: "Anfrage fehlgeschlagen. Bitte die Anzeige aktualisieren und erneut versuchen.",
    gapOverview: "Verfügbar, mit unvollständiger Delta-Abdeckung", jobFailed: "Letzte Anforderung fehlgeschlagen: {error}"
  });
  Object.assign(labels.en, {
    protectedAccess: "PROTECTED ACCESS", loginTitle: "Welcome back", loginHelp: "Sign in with your administrator password.",
    setupHelp: "The dashboard is locked. Set your password in the server terminal:", password: "Password", login: "Sign in", logout: "Sign out",
    invalid_password: "Incorrect password.", login_limited: "Too many attempts. Wait five minutes and try again.", password_not_configured: "Please set a password in the server terminal first.",
    sessionExpired: "Your session ended. Please sign in again.", access: "Access & API", accessHelp: "Manage sessions, your password and product API access.",
    sessionDuration: "Sign out after inactivity", session30: "30 minutes", session480: "8 hours", sessionNever: "Stay signed in", sessionCustom: "Custom duration…", idleMinutes: "Minutes",
    sessionHelp: "Automatic status polling does not extend your session. Changes apply to all sessions. A password change signs out every session.", logoutAll: "Sign out all sessions",
    apiRequired: "Require an API key", apiPolicyHelp: "Applies only to product API lookups. Dashboard, statistics, settings and imports always require sign-in.",
    publicApiConsent: "I allow product API requests without a key. Anyone who can reach this server can query products.",
    apiKey: "API key", keyHelp: "Leave unchanged to keep the current key. Use the eye to reveal it or copy it while hidden. A new key takes effect when saved.", copy: "Copy", copied: "Copied", generate: "Generate new key",
    keyChangeConsent: "Connected applications must use the new key after saving. The old key stops working immediately.",
    changePassword: "Change password", currentPassword: "Current password", newPassword: "New password", repeatPassword: "Repeat new password", passwordHelp: "Use 8–256 characters. All sessions will be signed out.",
    passwordMismatch: "The new passwords do not match or contain fewer than 8 characters.", showSecret: "Show", hideSecret: "Hide", accessSaved: "Access settings saved.", storedKey: "Stored key", copyFailed: "Copy failed. Reveal the key and copy it manually."
  });
  Object.assign(labels.de, {
    protectedAccess: "GESCHÜTZTER ZUGRIFF", loginTitle: "Willkommen zurück", loginHelp: "Melde dich mit deinem Administrator-Passwort an.",
    setupHelp: "Die Oberfläche ist gesperrt. Lege dein Passwort im Terminal des Servers fest:", password: "Passwort", login: "Anmelden", logout: "Abmelden",
    invalid_password: "Das Passwort ist falsch.", login_limited: "Zu viele Versuche. Bitte fünf Minuten warten und erneut versuchen.", password_not_configured: "Bitte zuerst im Server-Terminal ein Passwort festlegen.",
    sessionExpired: "Deine Sitzung ist beendet. Bitte erneut anmelden.", access: "Zugriff & API", accessHelp: "Verwalte Sitzungen, dein Passwort und den Zugriff auf die Produkt-API.",
    sessionDuration: "Nach Inaktivität abmelden", session30: "30 Minuten", session480: "8 Stunden", sessionNever: "Angemeldet bleiben", sessionCustom: "Eigene Dauer …", idleMinutes: "Minuten",
    sessionHelp: "Automatische Statusabfragen verlängern die Sitzung nicht. Änderungen gelten für alle Sitzungen. Eine Passwortänderung meldet alle Sitzungen ab.", logoutAll: "Alle Sitzungen abmelden",
    apiRequired: "API-Schlüssel erforderlich", apiPolicyHelp: "Gilt nur für Produktabfragen über die API. Oberfläche, Statistiken, Einstellungen und Importe erfordern immer eine Anmeldung.",
    publicApiConsent: "Ich erlaube Produktabfragen ohne Schlüssel. Jeder, der diesen Server erreicht, kann Produkte abfragen.",
    apiKey: "API-Schlüssel", keyHelp: "Unverändert lassen, um den bisherigen Schlüssel zu behalten. Mit dem Auge anzeigen oder verdeckt kopieren. Ein neuer Schlüssel gilt erst nach dem Speichern.", copy: "Kopieren", copied: "Kopiert", generate: "Neuen Schlüssel generieren",
    keyChangeConsent: "Angeschlossene Anwendungen benötigen nach dem Speichern den neuen Schlüssel. Der alte funktioniert dann sofort nicht mehr.",
    changePassword: "Passwort ändern", currentPassword: "Aktuelles Passwort", newPassword: "Neues Passwort", repeatPassword: "Neues Passwort wiederholen", passwordHelp: "8–256 Zeichen verwenden. Alle Sitzungen werden abgemeldet.",
    passwordMismatch: "Die neuen Passwörter stimmen nicht überein oder enthalten weniger als 8 Zeichen.", showSecret: "Anzeigen", hideSecret: "Verbergen", accessSaved: "Zugriffseinstellungen gespeichert.", storedKey: "Gespeicherter Schlüssel", copyFailed: "Kopieren fehlgeschlagen. Bitte Schlüssel einblenden und manuell kopieren."
  });
  const kinds = ["food", "beauty", "petfood", "product"];
  const $ = id => document.getElementById(id);
  let language = navigator.language.toLowerCase().startsWith("de") ? "de" : "en";
  try { const saved = localStorage.getItem("off-proxy-language"); if (saved === "de" || saved === "en") language = saved; } catch (_) {}
  let sessionGeneration = 0;
  let authenticated = false, authNonce = "", accessOptions = null, apiKeyDirty = false, lastActivity = 0;
  let controlBusy = false, controlNotice = null, fullKind = null;
  Object.assign(labels.en, {
    components: "Components", componentsTitle: "Program & components", manualOnly: "MANUAL UPDATES ONLY",
    componentsHelp: "Nothing is checked or installed automatically. A check only looks for compatible component updates.",
    componentsCheck: "Check for updates", componentsUpdate: "Update components…", componentsStart: "Start update now",
    componentsConfirmTitle: "Confirm component update",
    componentsConfirmText: "Refresh Python/Linux, Gunicorn 27.x and MongoDB 8.0.x. Services restart briefly. Your data, settings and keys are retained. No full import is requested.",
    componentsScope: "Host Debian, Docker, your reverse proxy and application code are not updated by this action.",
    component_agent_unavailable: "The host service is unavailable. In the server terminal, run: off-proxy host-agent install",
    component_import_active: "An import is active. Wait for it to finish, then start the update again.",
    componentPython: "Python & Linux base", componentGunicorn: "Gunicorn web server", componentMongo: "MongoDB",
    componentInstalled: "Installed", componentAvailable: "Update available", componentCurrent: "Up to date", componentUnknown: "Could not determine update status",
    componentNever: "Not checked yet", componentChecked: "Last check: {time}", componentIdle: "No update running.",
    componentPending: "Request queued. The host service will process it.", componentChecking: "Checking published component versions…",
    componentSuccess: "Completed successfully.", componentFailed: "The action failed or the check was incomplete. No further update will be started automatically.",
    componentDeferred: "Update deferred because synchronization started. Please start it again when synchronization has finished.",
    componentInterrupted: "The previous action was interrupted. Check the service and start a new action if needed.",
    componentExpired: "The request expired without being started. Please request it again.",
    componentPreparing: "Preparing update…", componentDownloading: "Downloading component images…", componentBuilding: "Building the replacement image…",
    componentRestarting: "Restarting services. The connection may be briefly interrupted…", componentVerifying: "Checking the API after restart…"
  });
  Object.assign(labels.de, {
    components: "Komponenten", componentsTitle: "Programm & Komponenten", manualOnly: "NUR MANUELLE UPDATES",
    componentsHelp: "Es wird nichts automatisch geprüft oder installiert. Eine Prüfung sucht nur nach passenden Komponenten-Updates.",
    componentsCheck: "Nach Updates suchen", componentsUpdate: "Komponenten aktualisieren …", componentsStart: "Update jetzt starten",
    componentsConfirmTitle: "Komponenten-Update bestätigen",
    componentsConfirmText: "Python-/Linux-Basis, Gunicorn 27.x und MongoDB 8.0.x erneuern. Die Dienste werden kurz neu gestartet. Daten, Einstellungen und Schlüssel bleiben erhalten. Es wird kein Vollimport angefordert.",
    componentsScope: "Debian und Docker auf dem Host, ein eigener Reverse Proxy und unser Programmcode werden dabei nicht aktualisiert.",
    component_agent_unavailable: "Der Host-Dienst ist nicht erreichbar. Im Server-Terminal ausführen: off-proxy host-agent install",
    component_import_active: "Ein Import läuft. Bitte sein Ende abwarten und das Update erneut starten.",
    componentPython: "Python- & Linux-Basis", componentGunicorn: "Gunicorn-Webserver", componentMongo: "MongoDB",
    componentInstalled: "Installiert", componentAvailable: "Update verfügbar", componentCurrent: "Aktuell", componentUnknown: "Update-Status nicht ermittelbar",
    componentNever: "Noch nicht geprüft", componentChecked: "Letzte Prüfung: {time}", componentIdle: "Es läuft kein Update.",
    componentPending: "Anforderung vorgemerkt. Der Host-Dienst übernimmt sie.", componentChecking: "Veröffentlichte Komponentenversionen werden geprüft …",
    componentSuccess: "Erfolgreich abgeschlossen.", componentFailed: "Die Aktion ist fehlgeschlagen oder die Prüfung war unvollständig. Es wird kein weiteres Update automatisch gestartet.",
    componentDeferred: "Update zurückgestellt, weil ein Abgleich gestartet ist. Nach dessen Ende bitte erneut starten.",
    componentInterrupted: "Die vorherige Aktion wurde unterbrochen. Bitte den Dienst prüfen und bei Bedarf eine neue Aktion starten.",
    componentExpired: "Die Anforderung ist abgelaufen, ohne gestartet zu werden. Bitte erneut anfordern.",
    componentPreparing: "Update wird vorbereitet …", componentDownloading: "Komponenten-Images werden geladen …", componentBuilding: "Neues Image wird gebaut …",
    componentRestarting: "Dienste werden neu gestartet. Die Verbindung kann kurz unterbrochen sein …", componentVerifying: "API wird nach dem Neustart geprüft …"
  });
  let componentState = null;
  function renderComponents() {
    const state = componentState || {}, busy = ["pending", "running"].includes(state.status);
    $("components").disabled = !connected;
    $("components-agent").hidden = !!state.agent_available;
    $("components-check").disabled = !connected || !state.agent_available || busy || controlBusy;
    $("components-update").disabled = $("components-check").disabled || snapshot?.scheduler?.phase === "running";
    const phases = {preparing:"componentPreparing",downloading:"componentDownloading",building:"componentBuilding",restarting:"componentRestarting",verifying:"componentVerifying"};
    const message = state.status === "pending" ? "componentPending" : state.status === "running" ? (state.action === "check" ? "componentChecking" : phases[state.phase] || "componentPreparing") : state.result === "interrupted" ? "componentInterrupted" : state.result === "expired" ? "componentExpired" : state.status === "success" ? "componentSuccess" : state.status === "failed" ? "componentFailed" : state.status === "deferred" ? "componentDeferred" : "componentIdle";
    setText("components-state", t(message));
    setText("components-checked", state.checked_at ? t("componentChecked", {time:date(state.checked_at)}) : t("componentNever"));
    const grid = $("components-rows");
    for (const name of ["python","gunicorn","mongo"]) {
      let item = document.getElementById(`component-${name}`);
      if (!item) { item = document.createElement("article"); item.id = `component-${name}`; item.className="component-row"; item.innerHTML='<h3></h3><p class="muted"></p><span class="badge neutral"></span>'; grid.append(item); }
      const row = (state.rows || []).find(r=>r.name===name) || {}, installed = state.installed?.[name]?.version || row.installed || "—";
      item.querySelector("h3").textContent = t({python:"componentPython",gunicorn:"componentGunicorn",mongo:"componentMongo"}[name]);
      item.querySelector("p").textContent = `${t("componentInstalled")}: ${installed}${name === "gunicorn" && row.available ? ` → ${row.available}` : ""}`;
      badge(item.querySelector("span"), t(row.state === "available" ? "componentAvailable" : row.state === "current" ? "componentCurrent" : "componentUnknown"), row.state === "current" ? "good" : row.state === "available" ? "busy" : "neutral");
    }
  }
  let snapshot = null, lookupResult = null, lookupNotice = null, polling = false, lookupSequence = 0, lookupController = null, offset = 0, connected = false, attemptedConnection = false;
  const t = (key, vars = {}) => Object.entries(vars).reduce((s, [name, value]) => s.replaceAll(`{${name}}`, String(value)), labels[language][key] || key);
  const locale = () => language === "de" ? "de-DE" : "en-GB";
  const number = value => typeof value === "number" && Number.isFinite(value) ? new Intl.NumberFormat(locale(), {maximumFractionDigits: 0}).format(value) : "—";
  const date = value => {
    if (!value) return t("noDate");
    const d = new Date(typeof value === "number" ? value * 1000 : value);
    return Number.isNaN(d.getTime()) ? t("noDate") : new Intl.DateTimeFormat(locale(), {dateStyle: "medium", timeStyle: "short"}).format(d);
  };
  const bytes = value => {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    let n = value, index = 0;
    while (n >= 1024 && index < units.length - 1) { n /= 1024; index++; }
    return `${new Intl.NumberFormat(locale(), {maximumFractionDigits: index ? 1 : 0}).format(n)} ${units[index]}`;
  };
  const setText = (id, value) => { $(id).textContent = value; };
  const badge = (element, text, type) => { element.textContent = text; element.className = `badge ${type}`; };

  for (const [index, kind] of kinds.entries()) {
    const card = document.createElement("article");
    card.className = "dataset-card"; card.dataset.kind = kind;
    card.innerHTML = `<div class="dataset-top"><span class="dataset-icon" aria-hidden="true">${["F", "B", "P", "O"][index]}</span><span id="${kind}-badge" class="badge neutral"></span></div><h3 data-i18n="${kind}"></h3><div class="dataset-count" id="${kind}-count">—</div><p class="dataset-subtitle" data-i18n="countHint"></p><dl><div><dt data-i18n="fullAt"></dt><dd id="${kind}-full">—</dd></div><div><dt data-i18n="checkedAt"></dt><dd id="${kind}-checked">—</dd></div><div><dt data-i18n="sourceAt"></dt><dd id="${kind}-source">—</dd></div><div><dt data-i18n="nextFull"></dt><dd id="${kind}-next">—</dd></div><div><dt data-i18n="noCode"></dt><dd id="${kind}-unindexed">—</dd></div></dl><p id="${kind}-error" class="dataset-error" hidden></p><p id="${kind}-gap" class="dataset-warning" hidden></p><p id="${kind}-required" class="dataset-warning" hidden></p><p id="${kind}-job" class="dataset-error" hidden></p><button type="button" class="secondary full-button" disabled data-kind="${kind}" id="${kind}-import" data-i18n="fullButton"></button>`;
    $("dataset-grid").append(card);
    $(`${kind}-import`).addEventListener("click", () => { fullKind = kind; $("full-error").hidden = true; setText("full-dataset", t(kind)); $("full-dialog").showModal(); });
  }

  function updateCountdown() {
    if (!snapshot) return;
    const schedule = snapshot.scheduler;
    setText("next-check", schedule.next_check_epoch ? date(schedule.next_check_epoch) : schedule.phase === "running" ? t("afterCycle") : t("noSchedule"));
    if (!schedule.next_check_epoch) { setText("next-check-relative", "—"); return; }
    const remaining = Math.ceil(schedule.next_check_epoch - (Date.now() / 1000 + offset));
    if (remaining <= 0) { setText("next-check-relative", t("overdue")); return; }
    const days = Math.floor(remaining / 86400), hours = Math.floor(remaining % 86400 / 3600), minutes = Math.floor(remaining % 3600 / 60);
    const parts = days ? `${days} ${t("days")} ${hours} ${t("hours")}` : hours ? `${hours} ${t("hours")} ${minutes} ${t("minutes")}` : `${Math.max(1, minutes)} ${t("minutes")}`;
    setText("next-check-relative", t("inTime", {time: parts}));
  }

  function renderStatus() {
    badge($("connection"), t(!attemptedConnection ? "loading" : connected ? "connected" : "disconnected"), !attemptedConnection ? "neutral" : connected ? "good" : "error");
    if (!snapshot) return;
    setText("version", snapshot.version);
    setText("total-records", number(snapshot.statistics.records));
    setText("storage", bytes(snapshot.statistics.database_bytes));
    setText("ready-count", `${kinds.filter(k => snapshot.datasets[k].ready).length} / 4`);
    setText("overview-state", t(snapshot.all_synced ? "allCurrent" : kinds.some(k => snapshot.datasets[k].phase === "error") ? "sourceErrors" : kinds.some(k => ["full_import", "delta_import"].includes(snapshot.datasets[k].phase)) ? "syncInProgress" : "incomplete"));
    if (kinds.some(k => snapshot.datasets[k].delta_gaps?.length)) setText("overview-state", t("gapOverview"));
    const syncJob = snapshot.requests?.sync?.status;
    $("sync").disabled = controlBusy || !connected || ["pending", "running"].includes(syncJob);
    setText("sync", t(syncJob === "pending" ? "queued" : syncJob === "running" ? "runningJob" : "syncNow"));
    $("settings").disabled = !connected || controlBusy;
    $("access").disabled = !connected || controlBusy;
    $("control-message").hidden = !controlNotice;
    if (controlNotice) setText("control-message", t(controlNotice));
    for (const kind of kinds) {
      const state = snapshot.datasets[kind], phase = state.phase;
      badge($(`${kind}-badge`), t(phase), phase === "ready" ? "good" : phase === "error" ? "error" : phase.endsWith("import") ? "busy" : "neutral");
      setText(`${kind}-count`, number(state.records));
      setText(`${kind}-full`, date(state.full_at));
      setText(`${kind}-checked`, date(state.checked_at));
      setText(`${kind}-source`, date(state.source_modified));
      setText(`${kind}-next`, state.next_full_epoch ? date(state.next_full_epoch) : t(state.ready ? "noFullSchedule" : "firstImport"));
      setText(`${kind}-unindexed`, number(state.unindexed_records));
      $(`${kind}-error`).hidden = !(phase === "error" && state.error);
      setText(`${kind}-error`, state.error || "");
      const gaps = state.delta_gaps || [], reasons = state.full_reasons || [], job = snapshot.requests?.[`full:${kind}`];
      $(`${kind}-gap`).hidden = !gaps.length;
      setText(`${kind}-gap`, gaps.length ? `${t("gapWarning", {ranges: gaps.map(([a, b]) => `${date(a)} – ${date(b)}`).join("; ")})} ${t(snapshot.settings.delta_gap_policy === "pause" ? "gapIsPaused" : "gapContinuing")}` : "");
      $(`${kind}-required`).hidden = !reasons.length || snapshot.settings.full_import_policy !== "confirm";
      setText(`${kind}-required`, t("fullRequired", {reasons: reasons.map(r => t(r)).join(", ")}));
      $(`${kind}-job`).hidden = job?.status !== "failed";
      setText(`${kind}-job`, t("jobFailed", {error: job?.error || ""}));
      $(`${kind}-import`).disabled = controlBusy || !connected || phase === "full_import" || ["pending", "running"].includes(job?.status);
      setText(`${kind}-import`, t(job?.status === "pending" ? "queued" : job?.status === "running" || phase === "full_import" ? "runningJob" : "fullButton"));
    }
    const schedule = snapshot.scheduler, state = snapshot.datasets[schedule.active_kind], progress = state?.progress;
    setText("activity-text", schedule.stale ? t("stale") : schedule.phase === "running" ? t("running", {name: t(schedule.active_kind || "activity")}) : t(schedule.phase === "stopped" ? "stopped" : schedule.phase === "waiting" || schedule.phase === "idle" ? "idle" : "unknown"));
    const showProgress = schedule.phase === "running" && !schedule.stale && state && ["full_import", "delta_import"].includes(state.phase) && progress;
    $("activity-progress").hidden = !showProgress;
    if (showProgress) {
      const total = progress.total_bytes, downloaded = progress.downloaded_bytes || 0;
      if (total > 0) {
        const percent = Math.min(100, downloaded / total * 100);
        $("job-progress").value = percent;
        setText("job-percent", `${Math.floor(percent)} % · ${bytes(downloaded)} / ${bytes(total)}`);
      } else {
        $("job-progress").removeAttribute("value");
        setText("job-percent", t("unknownSize"));
      }
      setText("job-detail", `${t("processed", {count: number(progress.records)})} · ${progress.finished ? t("finishing") : t("rate", {count: number(progress.records_per_second || 0)})}`);
    }
    renderComponents();
    updateCountdown();
    setText("updated", t("updated", {time: date(snapshot.server_epoch)}));
  }

  function renderLookup() {
    $("lookup-message").hidden = !lookupNotice;
    if (lookupNotice) setText("lookup-message", t(lookupNotice));
    $("lookup-result").hidden = !lookupResult;
    if (!lookupResult) return;
    const p = lookupResult.product;
    setText("product-name", (language === "de" ? p.product_name_de : p.product_name_en) || p.product_name_en || p.product_name || t("noName"));
    setText("lookup-source", t(p.product_type));
    setText("product-code", p.code || lookupResult.code);
    setText("product-brand", p.brands || t("noValue"));
    setText("product-quantity", p.quantity || (p.product_quantity != null && p.product_quantity_unit ? `${p.product_quantity} ${p.product_quantity_unit}` : t("noValue")));
    setText("product-time", t("foundTime", {ms: new Intl.NumberFormat(locale(), {maximumFractionDigits: 2}).format(lookupResult.elapsed_ms)}));
    const image = $("product-image"), url = p.image_front_thumb_url;
    const allowed = typeof url === "string" && /^https:\/\/images\.(?:openfoodfacts|openbeautyfacts|openpetfoodfacts|openproductsfacts)\.org\//.test(url);
    if (allowed) { if (image.getAttribute("src") !== url) image.src = url; image.hidden = false; }
    else { image.hidden = true; image.removeAttribute("src"); }
  }

  function translate() {
    document.documentElement.lang = language;
    $("language").value = language;
    for (const element of document.querySelectorAll("[data-i18n]")) element.textContent = t(element.dataset.i18n);
    for (const button of document.querySelectorAll(".dialog-close")) button.setAttribute("aria-label", t("close"));
    for (const id of ["login-eye", "api-eye"]) $(id).setAttribute("aria-label", t($(id === "api-eye" ? "api-key" : "login-password").type === "password" ? "showSecret" : "hideSecret"));
    $("api-key").placeholder = t("storedKey");
    renderStatus(); renderLookup();
    if (fullKind) setText("full-dataset", t(fullKind));
    if (!$("connection-error").hidden) setText("connection-error", t("connectionError"));
  }
  async function pollStatus() {
    if (!authenticated) { await checkAuth(); return; }
    if (polling) return;
    polling = true;
    const generation = sessionGeneration;
    try {
      const response = await fetch("/ui/status", {cache: "no-store", signal: AbortSignal.timeout(12000)});
      if (response.status === 401) { lockGui("sessionExpired"); return; }
      if (!response.ok) throw new Error("status unavailable");
      const data = await response.json();
      if (!authenticated || generation !== sessionGeneration) return;
      const componentResponse = await fetch("/ui/components", {cache:"no-store", signal:AbortSignal.timeout(12000)});
      if (componentResponse.status === 401) { lockGui("sessionExpired"); return; }
      if (componentResponse.ok) {
        const componentData = await componentResponse.json();
        if (!authenticated || generation !== sessionGeneration) return;
        componentState = componentData;
      }
      snapshot = data; offset = data.server_epoch - Date.now() / 1000; connected = true;
      $("connection-error").hidden = true;
    } catch (_) {
      connected = false; $("connection-error").hidden = false;
      setText("connection-error", t("connectionError"));
    } finally { polling = false; attemptedConnection = true; renderStatus(); }
  }
  const eye = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
  $("login-eye").innerHTML = eye; $("api-eye").innerHTML = eye;
  function lockGui(message) {
    sessionGeneration++; lookupSequence++; lookupController?.abort();
    authenticated = false; snapshot = null; componentState = null; connected = false; lookupResult = null;
    $("dashboard-content").hidden = true; $("login-panel").hidden = false; $("logout").hidden = true;
    for (const dialog of document.querySelectorAll("dialog[open]")) dialog.close();
    for (const id of ["api-key", "current-password", "new-password", "repeat-password", "login-password"]) $(id).value = "";
    $("api-key").type = "password"; $("login-password").type = "password";
    for (const id of ["api-eye", "login-eye"]) $(id).setAttribute("aria-label", t("showSecret"));
    $("login-error").hidden = !message; if (message) setText("login-error", t(message));
  }
  async function checkAuth() {
    const generation = sessionGeneration;
    try {
      const response = await fetch("/auth/status", {cache:"no-store", signal:AbortSignal.timeout(12000)});
      if (!response.ok) throw new Error("auth unavailable");
      const data = await response.json();
      if (generation !== sessionGeneration) return;
      authNonce = data.control_nonce;
      $("setup-help").hidden = $("setup-command").hidden = data.configured;
      $("login-form").hidden = !data.configured; $("login-help").hidden = !data.configured;
      if (data.authenticated) {
        authenticated = true; $("dashboard-content").hidden = false; $("login-panel").hidden = true; $("logout").hidden = false;
        await pollStatus();
      } else if (authenticated) lockGui("sessionExpired");
    } catch (_) { $("login-error").hidden = false; setText("login-error", t("connectionError")); }
  }
  async function authPost(path, values = {}) {
    const generation = sessionGeneration;
    const response = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json", "X-Off-Proxy-Control":authNonce}, body:JSON.stringify(values), signal:AbortSignal.timeout(12000)});
    const data = await response.json();
    if (generation !== sessionGeneration) throw new Error("stale_session");
    if (!response.ok) { if (response.status === 401 && data.error === "authentication_required") lockGui("sessionExpired"); const error = new Error(data.error || "controlError"); error.status = response.status; throw error; }
    return data;
  }
  $("login-eye").addEventListener("click", () => {
    $("login-password").type = $("login-password").type === "password" ? "text" : "password"; translate();
  });
  $("login-form").addEventListener("submit", async event => {
    event.preventDefault(); $("login-submit").disabled = true; $("login-error").hidden = true;
    try { const status = await (await fetch("/auth/status", {cache:"no-store"})).json(); if (status.authenticated) { await checkAuth(); return; } authNonce = status.control_nonce; await authPost("/auth/login", {password:$("login-password").value}); $("login-password").value = ""; lastActivity = Date.now(); await checkAuth(); }
    catch (error) { $("login-error").hidden = false; setText("login-error", t(labels[language][error.message] ? error.message : "controlError")); }
    finally { $("login-submit").disabled = false; }
  });
  $("logout").addEventListener("click", async () => {
    try { await authPost("/auth/logout"); lockGui(); await checkAuth(); }
    catch (_) { controlNotice = "controlError"; renderStatus(); }
  });
  async function activity() {
    if (!authenticated || Date.now()-lastActivity < 30000) return;
    lastActivity = Date.now();
    try { await authPost("/auth/activity"); } catch (error) { if (error.status === 401) lockGui("sessionExpired"); }
  }
  for (const event of ["pointerdown", "keydown", "wheel", "touchstart"]) document.addEventListener(event, activity, {passive:true});
  function accessMessage(key) { $("access-message").hidden = false; setText("access-message", t(key)); }
  function updateSessionInput() {
    const custom = $("session-duration").value === "custom";
    $("idle-minutes").hidden = $("idle-label").hidden = !custom; $("idle-minutes").required = custom;
    $("idle-minutes").disabled = !custom;
  }
  $("session-duration").addEventListener("change", updateSessionInput);
  $("access").addEventListener("click", async () => {
    const generation = sessionGeneration;
    try {
      const response = await fetch("/ui/security", {cache:"no-store"});
      if (response.status === 401) { lockGui("sessionExpired"); return; }
      if (!response.ok) throw new Error("access failed");
      accessOptions = await response.json();
      if (!authenticated || generation !== sessionGeneration) return;
      const minutes = String(accessOptions.idle_minutes);
      $("session-duration").value = ["0","30","480"].includes(minutes) ? minutes : "custom";
      $("idle-minutes").value = minutes === "0" ? "30" : minutes; updateSessionInput();
      $("api-required").checked = accessOptions.api_auth_required;
      $("public-api-consent").hidden = true; $("confirm-public-api").checked = false; $("confirm-public-api").required = false;
      $("key-change-consent").hidden = true; $("confirm-key-change").checked = false; $("confirm-key-change").required = false;
      for (const id of ["api-key","current-password","new-password","repeat-password"]) $(id).value = "";
      $("api-key").type = "password"; apiKeyDirty = false; $("access-message").hidden = true; $("api-copy").textContent = t("copy");
      $("access-dialog").showModal(); translate();
    } catch (_) { controlNotice = "controlError"; renderStatus(); }
  });
  $("api-required").addEventListener("change", () => {
    const consent = !$("api-required").checked && accessOptions.api_auth_required;
    $("public-api-consent").hidden = !consent; $("confirm-public-api").required = consent;
  });
  function keyChanged() {
    apiKeyDirty = true; $("key-change-consent").hidden = false; $("confirm-key-change").required = true;
  }
  $("api-key").addEventListener("input", keyChanged);
  async function currentKey() {
    const generation = sessionGeneration;
    const response = await fetch("/ui/api-key", {headers:{"X-Off-Proxy-Control":authNonce}, cache:"no-store"});
    if (response.status === 401) { lockGui("sessionExpired"); throw new Error("expired"); }
    if (!response.ok) throw new Error("key failed");
    const data = await response.json();
    if (!authenticated || generation !== sessionGeneration) throw new Error("stale_session");
    return data.api_token;
  }
  $("api-eye").addEventListener("click", async () => {
    try { if (!$("api-key").value) $("api-key").value = await currentKey(); $("api-key").type = $("api-key").type === "password" ? "text" : "password"; translate(); }
    catch (_) { accessMessage("controlError"); }
  });
  $("api-copy").addEventListener("click", async () => {
    try {
      const value = $("api-key").value || await currentKey();
      if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(value);
      else {
        const area=document.createElement("textarea"); area.value=value; area.className="clipboard-helper"; $("access-dialog").append(area); area.select();
        const copied=document.execCommand("copy"); area.remove(); if (!copied) throw new Error("copy failed");
      }
      setText("api-copy", t("copied"));
    } catch (_) { accessMessage("copyFailed"); }
  });
  $("api-generate").addEventListener("click", () => {
    $("api-key").value = Array.from(crypto.getRandomValues(new Uint8Array(32)), x=>x.toString(16).padStart(2,"0")).join(""); keyChanged();
  });
  $("access-form").addEventListener("submit", async event => {
    event.preventDefault(); $("access-save").disabled = true;
    try {
      const values = {idle_minutes:Number($("session-duration").value === "custom" ? $("idle-minutes").value : $("session-duration").value), api_auth_required:$("api-required").checked, confirm_public_api:$("confirm-public-api").checked};
      if (apiKeyDirty) values.api_token = $("api-key").value;
      accessOptions = await authPost("/ui/security", values); apiKeyDirty = false;
      $("access-dialog").close(); $("api-key").value = ""; controlNotice = "accessSaved"; renderStatus();
    } catch (error) { if (error.status === 401) lockGui("sessionExpired"); else accessMessage("controlError"); }
    finally { $("access-save").disabled = false; }
  });
  $("logout-all").addEventListener("click", async () => {
    try { await authPost("/auth/logout-all"); lockGui("sessionExpired"); await checkAuth(); }
    catch (_) { accessMessage("controlError"); }
  });
  $("password-save").addEventListener("click", async () => {
    if (Array.from($("new-password").value).length < 8 || $("new-password").value !== $("repeat-password").value) { accessMessage("passwordMismatch"); return; }
    $("password-save").disabled = true;
    try { await authPost("/auth/password", {current_password:$("current-password").value, new_password:$("new-password").value}); lockGui("sessionExpired"); await checkAuth(); }
    catch (error) { if (error.message === "invalid_password") accessMessage("invalid_password"); else if (error.status === 401) lockGui("sessionExpired"); else accessMessage("controlError"); }
    finally { $("password-save").disabled = false; }
  });
  $("access-dialog").addEventListener("close", () => { for (const id of ["api-key","current-password","new-password","repeat-password"]) $(id).value = ""; });
  $("language").addEventListener("change", () => {
    language = $("language").value;
    try { localStorage.setItem("off-proxy-language", language); } catch (_) {}
    translate();
  });
  async function sendControl(path, values) {
    if (controlBusy || !authenticated) return false;
    controlBusy = true; renderStatus();
    try { await authPost(path, values); return true; }
    catch (_) { controlNotice = "controlError"; return false; }
    finally { controlBusy = false; await pollStatus(); renderStatus(); }
  }
  $("components").addEventListener("click", () => { $("components-error").hidden=true; renderComponents(); $("components-dialog").showModal(); });
  async function componentAction(path, values) {
    controlBusy = true; renderComponents(); $("components-error").hidden=true;
    try { await authPost(path,values); await pollStatus(); }
    catch(error) { setText("components-error", t(labels[language][error.message] ? error.message : "controlError")); $("components-error").hidden=false; }
    finally { controlBusy=false; renderComponents(); }
  }
  $("components-check").addEventListener("click", () => componentAction("/ui/components/check",{}));
  $("components-update").addEventListener("click", () => $("components-confirm").showModal());
  $("components-start").addEventListener("click", async () => {
    $("components-start").disabled=true;
    $("components-confirm").close();
    await componentAction("/ui/components/update",{confirmed:true});
    $("components-start").disabled=false;
  });
  $("sync").addEventListener("click", async () => {
    if (await sendControl("/ui/sync", {})) { controlNotice = "syncQueued"; renderStatus(); }
  });
  $("settings").addEventListener("click", () => {
    const options = snapshot.settings;
    $("gap-policy").value = options.delta_gap_policy;
    $("full-policy").value = options.full_import_policy;
    $("full-days").value = options.full_interval_days;
    $("auto-confirm").checked = false; $("auto-confirm-row").hidden = true; $("auto-confirm").required = false;
    $("settings-error").hidden = true;
    $("settings-dialog").showModal();
  });
  $("full-policy").addEventListener("change", () => {
    const consent = $("full-policy").value === "automatic" && snapshot.settings.full_import_policy !== "automatic";
    $("auto-confirm-row").hidden = !consent; $("auto-confirm").required = consent;
  });
  for (const button of document.querySelectorAll("[data-close]")) button.addEventListener("click", () => $(button.dataset.close).close());
  $("settings-cancel").addEventListener("click", () => $("settings-dialog").close());
  $("settings-form").addEventListener("submit", async event => {
    event.preventDefault(); $("settings-save").disabled = true;
    const ok = await sendControl("/ui/settings", {delta_gap_policy: $("gap-policy").value, full_import_policy: $("full-policy").value, full_interval_days: Number($("full-days").value), confirm_automatic_full_imports: $("auto-confirm").checked});
    $("settings-save").disabled = false;
    if (ok) { $("settings-dialog").close(); controlNotice = "saved"; renderStatus(); }
    else { setText("settings-error", t("controlError")); $("settings-error").hidden = false; }
  });
  $("full-cancel").addEventListener("click", () => $("full-dialog").close());
  $("full-start").addEventListener("click", async () => {
    $("full-start").disabled = true;
    const ok = await sendControl("/ui/full-import", {kind: fullKind, confirmed: true});
    $("full-start").disabled = false;
    if (ok) { $("full-dialog").close(); controlNotice = "fullQueued"; renderStatus(); }
    else { setText("full-error", t("controlError")); $("full-error").hidden = false; }
  });
  $("refresh").addEventListener("click", pollStatus);
  $("product-image").addEventListener("error", () => { $("product-image").hidden = true; });
  $("lookup-form").addEventListener("submit", async event => {
    event.preventDefault();
    const code = $("ean").value.trim();
    if (!/^[0-9]{1,256}$/.test(code)) { lookupNotice = "invalid"; lookupResult = null; renderLookup(); return; }
    const sequence = ++lookupSequence;
    lookupController?.abort();
    const controller = new AbortController(); lookupController = controller;
    const timeout = setTimeout(() => controller.abort(), 12000);
    lookupResult = null; lookupNotice = "lookupBusy"; $("lookup-button").disabled = true; $("lookup-message").className = ""; renderLookup();
    try {
      const params = new URLSearchParams({ean: code, lc: language, product_type: $("lookup-type").value});
      const response = await fetch(`/ui/lookup?${params}`, {cache: "no-store", signal: controller.signal});
      const data = await response.json();
      if (response.status === 401) { lockGui("sessionExpired"); return; }
      if (sequence !== lookupSequence) return;
      if (response.ok) { lookupResult = data; lookupNotice = null; }
      else { lookupNotice = response.status === 404 ? "notFound" : data.error === "datasets_not_ready" ? "notReady" : data.error === "database_unavailable" ? "databaseError" : "requestError"; }
    } catch (_) { if (sequence === lookupSequence) lookupNotice = "requestError"; }
    finally {
      clearTimeout(timeout);
      if (sequence === lookupSequence) { $("lookup-button").disabled = false; renderLookup(); }
    }
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) pollStatus(); });
  translate(); setText("activity-text", t("loading"));
  checkAuth();
  setInterval(() => { if (!document.hidden) pollStatus(); }, 5000);
  setInterval(() => { if (!document.hidden) updateCountdown(); }, 1000);
})();
