/**
 * Apply resolved light/dark theme before first paint. Loads synchronously in <head>.
 * Exposes Am4Theme for settings-store.js. Must match SETTINGS_STORAGE_KEY in ui_settings.py.
 */
(function (global) {
  "use strict";

  var STORAGE_KEY = "am4-ops-center.ui-settings.v1";
  var mediaQuery = null;
  var onMediaChange = null;

  function readThemeMode() {
    try {
      var raw = global.localStorage.getItem(STORAGE_KEY);
      if (!raw || !String(raw).trim()) return "dark";
      var d = JSON.parse(raw);
      var m = d && d.appearance && d.appearance.theme_mode;
      if (m === "light" || m === "dark" || m === "system") return m;
    } catch (e) {
      /* ignore */
    }
    return "dark";
  }

  function resolveMode(mode) {
    if (mode === "light") return "light";
    if (mode === "dark") return "dark";
    try {
      if (global.matchMedia && global.matchMedia("(prefers-color-scheme: dark)").matches) {
        return "dark";
      }
      return "light";
    } catch (e) {
      return "dark";
    }
  }

  function applyResolved(resolved) {
    var doc = global.document;
    if (!doc || !doc.documentElement) return;
    doc.documentElement.setAttribute("data-theme", resolved);
    doc.documentElement.style.colorScheme = resolved === "dark" ? "dark" : "light";
    try {
      if (global.Am4Branding && typeof global.Am4Branding.syncDefaultAppLogos === "function") {
        global.Am4Branding.syncDefaultAppLogos();
      }
    } catch (e) {
      /* ignore */
    }
  }

  function detachSystemListener() {
    if (mediaQuery && onMediaChange) {
      try {
        mediaQuery.removeEventListener("change", onMediaChange);
      } catch (e) {
        try {
          mediaQuery.removeListener(onMediaChange);
        } catch (e2) {
          /* ignore */
        }
      }
    }
    mediaQuery = null;
    onMediaChange = null;
  }

  function attachSystemListener() {
    detachSystemListener();
    if (!global.matchMedia) return;
    try {
      mediaQuery = global.matchMedia("(prefers-color-scheme: dark)");
      onMediaChange = function () {
        var mode = readThemeMode();
        if (mode !== "system") return;
        applyResolved(resolveMode("system"));
      };
      if (mediaQuery.addEventListener) {
        mediaQuery.addEventListener("change", onMediaChange);
      } else if (mediaQuery.addListener) {
        mediaQuery.addListener(onMediaChange);
      }
    } catch (e) {
      mediaQuery = null;
      onMediaChange = null;
    }
  }

  function syncSystemListener(themeMode) {
    if (themeMode === "system") attachSystemListener();
    else detachSystemListener();
  }

  function applyFromAppearance(appearance) {
    if (!appearance || typeof appearance !== "object") {
      applyResolved("dark");
      detachSystemListener();
      return;
    }
    var mode = appearance.theme_mode;
    if (mode !== "light" && mode !== "dark" && mode !== "system") mode = "dark";
    applyResolved(resolveMode(mode));
    syncSystemListener(mode);
  }

  function boot() {
    var mode = readThemeMode();
    applyResolved(resolveMode(mode));
    syncSystemListener(mode);
  }

  global.Am4Theme = {
    readThemeMode: readThemeMode,
    resolveMode: resolveMode,
    applyResolved: applyResolved,
    applyFromAppearance: applyFromAppearance,
    syncSystemListener: syncSystemListener,
    boot: boot,
  };

  boot();
})(typeof window !== "undefined" ? window : globalThis);
