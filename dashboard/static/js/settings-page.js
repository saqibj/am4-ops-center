/**
 * Settings page: draft form, Save/Cancel, dirty detection, preview, section resets.
 */
(function () {
  "use strict";

  var saved = null;
  var toastTimer = null;

  function store() {
    return window.Am4UiSettings;
  }

  function clone(o) {
    return JSON.parse(JSON.stringify(o));
  }

  function $(id) {
    return document.getElementById(id);
  }

  function resolvePreviewTheme(themeMode) {
    if (themeMode === "light") return "light";
    if (themeMode === "dark") return "dark";
    try {
      return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } catch {
      return "dark";
    }
  }

  function themeModeFromForm() {
    var r = document.querySelector('input[name="theme_mode"]:checked');
    return r ? r.value : "dark";
  }

  function densityFromForm() {
    var r = document.querySelector('input[name="ui_density"]:checked');
    return r ? r.value : "comfortable";
  }

  function collectDraftState() {
    var st = clone(saved);
    st.appearance.theme_mode = themeModeFromForm();
    st.appearance.ui_density = densityFromForm();
    st.preferences.default_landing_path = $("default-landing").value || "/";
    st.notifications.route_change_alerts = $("notif-route").checked;
    st.notifications.maintenance_alerts = $("notif-maint").checked;
    st.notifications.marketing_alerts = $("notif-mkt").checked;
    return store().normalizeFromObject(st);
  }

  function isDirty() {
    try {
      return JSON.stringify(collectDraftState()) !== JSON.stringify(saved);
    } catch {
      return true;
    }
  }

  function updateDirtyUi() {
    var hint = $("settings-dirty-hint");
    var dirty = isDirty();
    hint.classList.toggle("hidden", !dirty);
    $("settings-save").disabled = !dirty;
  }

  function showToast(message) {
    var el = $("settings-toast");
    if (!el) return;
    if (toastTimer) {
      clearTimeout(toastTimer);
      toastTimer = null;
    }
    el.textContent = message;
    el.classList.remove("settings-toast--hidden");
    toastTimer = setTimeout(function () {
      el.classList.add("settings-toast--hidden");
      toastTimer = null;
    }, 3200);
  }

  function updatePreview() {
    var pv = $("settings-preview");
    if (!pv) return;
    var tm = themeModeFromForm();
    pv.setAttribute("data-preview-theme", resolvePreviewTheme(tm));
    pv.classList.toggle("density-compact", densityFromForm() === "compact");
  }

  function applyFormFromState(st) {
    var tm = st.appearance.theme_mode;
    var tr = document.querySelectorAll('input[name="theme_mode"]');
    for (var i = 0; i < tr.length; i++) {
      tr[i].checked = tr[i].value === tm;
    }
    var ud = st.appearance.ui_density;
    var dr = document.querySelectorAll('input[name="ui_density"]');
    for (var j = 0; j < dr.length; j++) {
      dr[j].checked = dr[j].value === ud;
    }
    $("default-landing").value = st.preferences.default_landing_path || "/";
    $("notif-route").checked = !!st.notifications.route_change_alerts;
    $("notif-maint").checked = !!st.notifications.maintenance_alerts;
    $("notif-mkt").checked = !!st.notifications.marketing_alerts;
    updatePreview();
    updateDirtyUi();
  }

  function syncSavedFromStore() {
    saved = clone(store().getState());
  }

  function onSave() {
    var st = collectDraftState();
    store().replaceState(st, { persist: true });
    syncSavedFromStore();
    applyFormFromState(saved);
    showToast("Settings saved.");
  }

  function onCancel() {
    applyFormFromState(saved);
  }

  function init() {
    if (!store() || !$("settings-save")) return;
    syncSavedFromStore();
    applyFormFromState(saved);

    $("settings-save").addEventListener("click", onSave);
    $("settings-cancel").addEventListener("click", onCancel);

    $("settings-section-jump").addEventListener("change", function () {
      var id = this.value;
      var target = document.querySelector(id);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    var inputs = document.querySelectorAll(
      'input[name="theme_mode"], input[name="ui_density"], #default-landing, #notif-route, #notif-maint, #notif-mkt'
    );
    for (var k = 0; k < inputs.length; k++) {
      inputs[k].addEventListener("change", function () {
        updatePreview();
        updateDirtyUi();
      });
      inputs[k].addEventListener("input", function () {
        updatePreview();
        updateDirtyUi();
      });
    }

    $("reset-appearance").addEventListener("click", function () {
      store().resetSection("appearance");
      syncSavedFromStore();
      applyFormFromState(saved);
      showToast("Appearance reset to defaults.");
    });
    $("reset-prefs").addEventListener("click", function () {
      store().resetSection("preferences");
      syncSavedFromStore();
      applyFormFromState(saved);
      showToast("Preferences reset.");
    });
    $("reset-notifs").addEventListener("click", function () {
      store().resetSection("notifications");
      syncSavedFromStore();
      applyFormFromState(saved);
      showToast("Notification preferences reset.");
    });
    $("reset-all").addEventListener("click", function () {
      if (!confirm("Reset all settings to defaults? This cannot be undone.")) return;
      store().resetAll();
      syncSavedFromStore();
      applyFormFromState(saved);
      showToast("All settings reset.");
    });

    window.addEventListener("beforeunload", function (e) {
      if (!isDirty()) return;
      e.preventDefault();
      e.returnValue = "";
    });

    document.addEventListener(
      "click",
      function (e) {
        if (!isDirty()) return;
        var a = e.target.closest("a");
        if (!a) return;
        var href = a.getAttribute("href");
        if (!href || href.charAt(0) === "#") return;
        if (href.indexOf("/") === 0 && !window.confirm("Discard unsaved changes?")) {
          e.preventDefault();
          e.stopPropagation();
        }
      },
      true
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
