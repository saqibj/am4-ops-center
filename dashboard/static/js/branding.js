/**
 * Default app logos (theme-aware). Uses <img class="am4-app-logo" data-am4-default-logo>.
 * Picks app-logo-light.png vs app-logo-dark.png from data-theme; on load error uses fallback then hides.
 */
(function (global) {
  "use strict";

  var PATH_DARK = "/static/img/app-logo-dark.png";
  var PATH_LIGHT = "/static/img/app-logo-light.png";
  var PATH_FALLBACK = "/static/img/app-logo-fallback.png";

  function resolvedTheme() {
    return global.document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function primaryUrl() {
    return resolvedTheme() === "light" ? PATH_LIGHT : PATH_DARK;
  }

  function syncDefaultAppLogos() {
    var doc = global.document;
    if (!doc || !doc.querySelectorAll) return;
    var imgs = doc.querySelectorAll("img.am4-app-logo[data-am4-default-logo]");
    var url = primaryUrl();
    for (var i = 0; i < imgs.length; i++) {
      (function (img) {
        if (img.getAttribute("src") === url) return;
        img.onerror = function () {
          img.onerror = function () {
            img.onerror = null;
            img.style.display = "none";
          };
          img.src = PATH_FALLBACK;
        };
        img.src = url;
      })(imgs[i]);
    }
  }

  global.Am4Branding = {
    defaultLogoUrlForTheme: primaryUrl,
    syncDefaultAppLogos: syncDefaultAppLogos,
    paths: { dark: PATH_DARK, light: PATH_LIGHT, fallback: PATH_FALLBACK },
  };

  function onReady() {
    syncDefaultAppLogos();
  }

  if (global.document.readyState === "loading") {
    global.document.addEventListener("DOMContentLoaded", onReady);
  } else {
    onReady();
  }
})(typeof window !== "undefined" ? window : globalThis);
