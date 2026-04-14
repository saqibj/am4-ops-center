/* Optional Chart.js helpers; HTMX drives most UI. */
/* Global Am4UiSettings (settings-store.js): getState, setState, subscribe, resolveTheme, … */
/* Am4Branding.syncDefaultAppLogos — theme default logos (branding.js). */
/* shell-branding.js — placeholder (airline name/logo are server-rendered). */

(function () {
  "use strict";

  var LANDING_REDIRECT_KEY = "am4-ops-center.landing-redirect-v1";

  function maybeRedirectDefaultLanding() {
    if (typeof window === "undefined" || !window.Am4UiSettings) return;
    var path = window.location.pathname || "";
    if (path !== "/") return;
    if (sessionStorage.getItem(LANDING_REDIRECT_KEY)) return;

    var target = (window.Am4UiSettings.getState().preferences || {}).default_landing_path || "/";
    if (typeof target !== "string" || target === "/") return;

    var allowed = {};
    var list = window.Am4UiSettings.ALLOWED_LANDING_PATHS || [];
    for (var i = 0; i < list.length; i++) allowed[list[i]] = true;
    if (!allowed[target]) return;

    sessionStorage.setItem(LANDING_REDIRECT_KEY, "1");
    window.location.replace(target);
  }

  /** Future: gate toasts or banners by saved notification prefs. */
  function notificationEnabled(key) {
    if (!window.Am4UiSettings) return true;
    var n = window.Am4UiSettings.getState().notifications || {};
    if (key === "route_change_alerts") return n.route_change_alerts !== false;
    if (key === "maintenance_alerts") return n.maintenance_alerts === true;
    if (key === "marketing_alerts") return n.marketing_alerts === true;
    return true;
  }

  document.addEventListener("DOMContentLoaded", function () {
    maybeRedirectDefaultLanding();
  });

  window.Am4Notifications = {
    enabled: notificationEnabled,
  };
})();
