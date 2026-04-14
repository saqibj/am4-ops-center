/**
 * AM4 Ops Center — UI settings (localStorage + in-memory store).
 * Schema must match dashboard/ui_settings.py (SETTINGS_SCHEMA_VERSION).
 * Airline name and logo are server-side — not stored here.
 */
(function (global) {
  "use strict";

  var SCHEMA_VERSION = 2;
  var STORAGE_KEY = "am4-ops-center.ui-settings.v1";

  var ALLOWED_THEME_MODES = { light: 1, dark: 1, system: 1 };
  var ALLOWED_DENSITIES = { comfortable: 1, compact: 1 };
  var ALLOWED_LANDING_PATHS = {
    "/": 1,
    "/hub-explorer": 1,
    "/aircraft": 1,
    "/route-analyzer": 1,
    "/scenarios": 1,
    "/fleet-planner": 1,
    "/buy-next": 1,
    "/buy-next/global": 1,
    "/my-fleet": 1,
    "/my-hubs": 1,
    "/my-routes": 1,
    "/routes/add": 1,
    "/fleet-health": 1,
    "/demand-utilization": 1,
    "/extraction-deltas": 1,
    "/hub-roi": 1,
    "/contributions": 1,
    "/heatmap": 1,
  };

  function defaults() {
    return {
      schema_version: SCHEMA_VERSION,
      appearance: { theme_mode: "dark", ui_density: "comfortable" },
      preferences: { default_landing_path: "/" },
      notifications: {
        route_change_alerts: true,
        maintenance_alerts: false,
        marketing_alerts: false,
      },
    };
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
    var preferences = data.preferences && typeof data.preferences === "object" ? data.preferences : {};
    var notifications = data.notifications && typeof data.notifications === "object" ? data.notifications : {};

    d.schema_version = SCHEMA_VERSION;
    d.appearance = {
      theme_mode: coerceThemeMode(appearance.theme_mode),
      ui_density: coerceDensity(appearance.ui_density),
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
