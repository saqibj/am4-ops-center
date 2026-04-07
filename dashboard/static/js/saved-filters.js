/**
 * Serialize filter forms to query strings (last value wins for duplicate keys)
 * and apply saved presets by replacing location.search.
 */
(function (global) {
  "use strict";

  function formToQueryString(formEl) {
    if (!formEl) {
      return "";
    }
    var fd = new FormData(formEl);
    var m = new Map();
    fd.forEach(function (v, k) {
      m.set(k, v);
    });
    return new URLSearchParams(m).toString();
  }

  global.am4SavedFilters = {
    applySelect: function (sel) {
      if (!sel || !sel.value) {
        return;
      }
      var opt = sel.options[sel.selectedIndex];
      var q = opt.getAttribute("data-params");
      if (q === null || q === "") {
        global.location.search = "";
        return;
      }
      global.location.search = q.charAt(0) === "?" ? q : "?" + q;
    },

    fillParamsHidden: function (formId, hiddenId) {
      var form = document.getElementById(formId);
      var h = document.getElementById(hiddenId);
      if (!h) {
        return;
      }
      h.value = formToQueryString(form);
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
