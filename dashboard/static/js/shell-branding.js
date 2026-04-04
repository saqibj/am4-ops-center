/**
 * Apply saved airline name + logo to the shell and Overview welcome line.
 * Subscribes to Am4UiSettings so changes persist without full reload when possible.
 */
(function () {
  "use strict";

  function getStore() {
    return window.Am4UiSettings;
  }

  function syncShellBranding() {
    var store = getStore();
    if (!store) return;
    var st = store.getState();
    var name = (st.branding && st.branding.airline_name) || "";
    var logo = st.branding && st.branding.airline_logo_data_url;

    var nameEl = document.getElementById("shell-airline-name");
    if (nameEl) {
      if (name) {
        nameEl.textContent = name;
        nameEl.setAttribute("title", name);
        nameEl.classList.remove("hidden");
      } else {
        nameEl.textContent = "";
        nameEl.removeAttribute("title");
        nameEl.classList.add("hidden");
      }
    }

    var logoEl = document.getElementById("shell-airline-logo");
    if (logoEl) {
      if (logo) {
        logoEl.onerror = function () {
          logoEl.onerror = null;
          logoEl.classList.add("hidden");
          logoEl.removeAttribute("src");
        };
        logoEl.alt = name ? "" : "Airline logo";
        logoEl.src = logo;
        logoEl.classList.remove("hidden");
      } else {
        logoEl.onerror = null;
        logoEl.alt = "";
        logoEl.classList.add("hidden");
        logoEl.removeAttribute("src");
      }
    }

    var welcome = document.getElementById("overview-welcome");
    if (welcome) {
      if (name) {
        welcome.textContent = "Welcome back — " + name;
      } else {
        welcome.textContent = "Welcome to your operations dashboard.";
      }
    }
  }

  function init() {
    syncShellBranding();
    var store = getStore();
    if (store && typeof store.subscribe === "function") {
      store.subscribe(function () {
        syncShellBranding();
      });
    }
    document.addEventListener("am4-settings-changed", syncShellBranding);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
