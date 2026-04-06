/**
 * AM4 Ops Center — UI settings (localStorage + in-memory store).
 * Schema must match dashboard/ui_settings.py (SETTINGS_SCHEMA_VERSION).
 */
(function (global) {
  "use strict";

  var SCHEMA_VERSION = 1;
  var STORAGE_KEY = "am4-ops-center.ui-settings.v1";

  var ALLOWED_THEME_MODES = { light: 1, dark: 1, system: 1 };
  var ALLOWED_DENSITIES = { comfortable: 1, compact: 1 };
  var ALLOWED_LANDING_PATHS = {
    "/": 1,
    "/hub-explorer": 1,
    "/aircraft": 1,
    "/route-analyzer": 1,
    "/fleet-planner": 1,
    "/buy-next": 1,
    "/my-fleet": 1,
    "/my-hubs": 1,
    "/my-routes": 1,
    "/fleet-health": 1,
    "/contributions": 1,
    "/heatmap": 1,
  };

  var MAX_AIRLINE_NAME_LEN = 60;
  var MAX_LOGO_DATA_URL_CHARS = 700000;
  var LOGO_PREFIXES = [
    "data:image/png;base64,",
    "data:image/jpeg;base64,",
    "data:image/jpg;base64,",
    "data:image/webp;base64,",
    "data:image/gif;base64,",
  ];

  function defaults() {
    return {
      schema_version: SCHEMA_VERSION,
      appearance: { theme_mode: "dark", ui_density: "comfortable" },
      branding: { airline_name: "", airline_logo_data_url: null },
      preferences: { default_landing_path: "/" },
      notifications: {
        route_change_alerts: true,
        maintenance_alerts: false,
        marketing_alerts: false,
      },
    };
  }

  function sanitizeAirlineName(raw) {
    if (raw == null) return "";
    var text = String(raw)
      /* eslint-disable-next-line no-control-regex -- strip C0 controls except tab/LF/CR */
      .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, "")
      .trim()
      .replace(/\s+/g, " ");
    if (text.length > MAX_AIRLINE_NAME_LEN) text = text.slice(0, MAX_AIRLINE_NAME_LEN);
    return text;
  }

  function sanitizeLogoDataUrl(raw) {
    if (raw == null) return null;
    var s = String(raw).trim();
    if (!s) return null;
    if (s.length > MAX_LOGO_DATA_URL_CHARS) return null;
    var okPrefix = false;
    for (var i = 0; i < LOGO_PREFIXES.length; i++) {
      if (s.indexOf(LOGO_PREFIXES[i]) === 0) {
        okPrefix = true;
        break;
      }
    }
    if (!okPrefix) return null;
    if (s.indexOf(";base64,") === -1) return null;
    if (s.indexOf("..") !== -1 || s.indexOf("data:text/html") === 0) return null;
    return s;
  }

  function coerceThemeMode(v) {
    return typeof v === "string" && ALLOWED_THEME_MODES[v] ? v : "dark";
  }

  function coerceDensity(v) {
    return typeof v === "string" && ALLOWED_DENSITIES[v] ? v : "comfortable";
  }

  function coerceBool(v, d) {
    return typeof v === "boolean" ? v : d;
  }

  function coerceLanding(v) {
    return typeof v === "string" && ALLOWED_LANDING_PATHS[v] ? v : "/";
  }

  function normalizeFromObject(data) {
    var d = defaults();
    if (!data || typeof data !== "object") return d;

    var appearance = data.appearance && typeof data.appearance === "object" ? data.appearance : {};
    var branding = data.branding && typeof data.branding === "object" ? data.branding : {};
    var preferences = data.preferences && typeof data.preferences === "object" ? data.preferences : {};
    var notifications = data.notifications && typeof data.notifications === "object" ? data.notifications : {};

    d.schema_version = SCHEMA_VERSION;
    d.appearance = {
      theme_mode: coerceThemeMode(appearance.theme_mode),
      ui_density: coerceDensity(appearance.ui_density),
    };
    d.branding = {
      airline_name: sanitizeAirlineName(branding.airline_name != null ? branding.airline_name : ""),
      airline_logo_data_url: sanitizeLogoDataUrl(branding.airline_logo_data_url),
    };
    d.preferences = {
      default_landing_path: coerceLanding(preferences.default_landing_path),
    };
    d.notifications = {
      route_change_alerts: coerceBool(notifications.route_change_alerts, true),
      maintenance_alerts: coerceBool(notifications.maintenance_alerts, false),
      marketing_alerts: coerceBool(notifications.marketing_alerts, false),
    };
    return d;
  }

  function parseStored(raw) {
    if (raw == null || !String(raw).trim()) return defaults();
    try {
      var data = JSON.parse(raw);
      return normalizeFromObject(data);
    } catch {
      return defaults();
    }
  }

  function cloneState(s) {
    return JSON.parse(JSON.stringify(s));
  }

  function mergePatch(base, patch) {
    if (!patch || typeof patch !== "object") return normalizeFromObject(base);
    var merged = cloneState(base);
    if (patch.appearance && typeof patch.appearance === "object") {
      merged.appearance = Object.assign({}, merged.appearance, patch.appearance);
    }
    if (patch.branding && typeof patch.branding === "object") {
      merged.branding = Object.assign({}, merged.branding, patch.branding);
    }
    if (patch.preferences && typeof patch.preferences === "object") {
      merged.preferences = Object.assign({}, merged.preferences, patch.preferences);
    }
    if (patch.notifications && typeof patch.notifications === "object") {
      merged.notifications = Object.assign({}, merged.notifications, patch.notifications);
    }
    return normalizeFromObject(merged);
  }

  function prefersDarkMq() {
    if (typeof global.matchMedia !== "function") return null;
    try {
      return global.matchMedia("(prefers-color-scheme: dark)").matches;
    } catch {
      return null;
    }
  }

  function resolveTheme(themeMode) {
    if (themeMode === "light") return "light";
    if (themeMode === "dark") return "dark";
    var dark = prefersDarkMq();
    if (dark === null) return "dark";
    return dark ? "dark" : "light";
  }

  var listeners = [];
  var state;

  function loadFromStorage() {
    try {
      if (typeof global.localStorage === "undefined") return defaults();
      var raw = global.localStorage.getItem(STORAGE_KEY);
      return parseStored(raw);
    } catch {
      return defaults();
    }
  }

  function persistToStorage(s) {
    try {
      if (typeof global.localStorage !== "undefined") {
        global.localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
      }
    } catch {
      /* quota / private mode */
    }
  }

  function syncDomTheme() {
    if (global.Am4Theme && typeof global.Am4Theme.applyFromAppearance === "function") {
      global.Am4Theme.applyFromAppearance(state.appearance);
    }
  }

  function syncDomDensity() {
    if (typeof global.document === "undefined" || !global.document.body) return;
    var compact = state.appearance && state.appearance.ui_density === "compact";
    global.document.body.classList.toggle("am4-density-compact", compact);
  }

  function notify() {
    syncDomTheme();
    syncDomDensity();
    var snap = getState();
    for (var i = 0; i < listeners.length; i++) {
      try {
        listeners[i](snap);
      } catch {
        /* ignore subscriber errors */
      }
    }
    try {
      var ev = new CustomEvent("am4-settings-changed", { detail: snap });
      global.dispatchEvent(ev);
    } catch {
      /* IE / very old */
    }
  }

  function getState() {
    return cloneState(state);
  }

  function setState(partial, options) {
    state = mergePatch(state, partial);
    if (!options || options.persist !== false) persistToStorage(state);
    notify();
    return getState();
  }

  function replaceState(next, options) {
    state = normalizeFromObject(next);
    if (!options || options.persist !== false) persistToStorage(state);
    notify();
    return getState();
  }

  function resetSection(section) {
    var d = defaults();
    if (section === "appearance") state.appearance = d.appearance;
    else if (section === "branding") state.branding = d.branding;
    else if (section === "preferences") state.preferences = d.preferences;
    else if (section === "notifications") state.notifications = d.notifications;
    else return getState();
    state.schema_version = SCHEMA_VERSION;
    persistToStorage(state);
    notify();
    return getState();
  }

  function resetAll() {
    state = defaults();
    persistToStorage(state);
    notify();
    return getState();
  }

  function subscribe(fn) {
    if (typeof fn !== "function") return function () {};
    listeners.push(fn);
    return function unsubscribe() {
      var idx = listeners.indexOf(fn);
      if (idx !== -1) listeners.splice(idx, 1);
    };
  }

  state = loadFromStorage();
  syncDomTheme();
  syncDomDensity();

  global.Am4UiSettings = {
    SCHEMA_VERSION: SCHEMA_VERSION,
    STORAGE_KEY: STORAGE_KEY,
    ALLOWED_LANDING_PATHS: Object.keys(ALLOWED_LANDING_PATHS),
    defaults: defaults,
    parseStored: parseStored,
    normalizeFromObject: normalizeFromObject,
    mergePatch: mergePatch,
    sanitizeAirlineName: sanitizeAirlineName,
    sanitizeLogoDataUrl: sanitizeLogoDataUrl,
    resolveTheme: resolveTheme,
    getState: getState,
    setState: setState,
    replaceState: replaceState,
    persist: function () {
      persistToStorage(state);
    },
    reloadFromStorage: function () {
      state = loadFromStorage();
      notify();
      return getState();
    },
    resetSection: resetSection,
    resetAll: resetAll,
    subscribe: subscribe,
  };
})(typeof window !== "undefined" ? window : globalThis);
