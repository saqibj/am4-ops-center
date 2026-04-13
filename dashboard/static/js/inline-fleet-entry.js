/* Client-side gate for Add route → inline fleet entry (task 4). */
(function () {
  "use strict";

  function parseMeta(root) {
    var el = root.querySelector("script.arf-aircraft-meta");
    if (!el || !el.textContent) return {};
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return {};
    }
  }

  function num(v) {
    var n = parseInt(String(v || "").trim(), 10);
    return isNaN(n) ? 0 : n;
  }

  function bindRoot(root) {
    if (!root || root.getAttribute("data-inline-fleet-bound") === "1") return;
    root.setAttribute("data-inline-fleet-bound", "1");

    var meta = parseMeta(root);
    var ac = root.querySelector("#arf-aircraft");
    var qty = root.querySelector("#arf-qty");
    var hint = root.querySelector("#arf-gate-hint");
    var readyLabel = root.querySelector("#arf-ready-label");
    var est = root.querySelector("#arf-est-cost");
    var pax = root.querySelector("#arf-pax-config");
    var cargo = root.querySelector("#arf-cargo-config");
    var y = root.querySelector("#arf-cfg-y");
    var j = root.querySelector("#arf-cfg-j");
    var f = root.querySelector("#arf-cfg-f");
    var cl = root.querySelector("#arf-cargo-l");
    var ch = root.querySelector("#arf-cargo-h");
    var modS = root.querySelector("#arf-mod-speed");
    var modF = root.querySelector("#arf-mod-fuel");
    var modC = root.querySelector("#arf-mod-co2");
    var hubDisp = root.querySelector("#arf-hub-display");
    var hubOv = root.querySelector("#arf-hub-override");
    var hubIn = root.querySelector("#arf-hub-override-input");

    function syncHubUi() {
      if (!hubOv || !hubIn || !hubDisp) return;
      if (hubOv.checked) {
        hubIn.classList.remove("hidden");
        hubDisp.classList.add("hidden");
      } else {
        hubIn.classList.add("hidden");
        hubDisp.classList.remove("hidden");
        var rh = root.getAttribute("data-route-hub") || "";
        hubDisp.value = rh;
        hubIn.value = rh;
      }
    }

    function applyTypeUi(sn) {
      var m = meta[sn] || null;
      if (m && modS && modF && modC) {
        modS.checked = !!m.speed_mod;
        modF.checked = !!m.fuel_mod;
        modC.checked = !!m.co2_mod;
      }
      var isCargo = m && String(m.type).toUpperCase() === "CARGO";
      if (pax && cargo) {
        if (isCargo) {
          cargo.classList.remove("hidden");
          pax.classList.add("opacity-50");
        } else {
          cargo.classList.add("hidden");
          pax.classList.remove("opacity-50");
        }
      }
      if (est && m && qty) {
        var q = Math.max(1, num(qty.value) || 1);
        var c = num(m.cost);
        est.textContent =
          c > 0
            ? "Estimated list price: $" + (c * q).toLocaleString() + " (" + q + " × $" + c.toLocaleString() + ")"
            : "Estimated list price: —";
      } else if (est) {
        est.textContent = "Estimated list price: —";
      }
    }

    function gate() {
      if (!ac || !qty) return;
      var sn = ac.value.trim().toLowerCase();
      var qv = num(qty.value);
      var m = sn ? meta[sn] : null;
      var ok = false;
      var msg = "";

      if (!sn) {
        msg = "Enter an aircraft shortname.";
      } else if (qv < 1) {
        msg = "Add-to-fleet quantity must be at least 1.";
      } else if (m && String(m.type).toUpperCase() === "CARGO") {
        var l = num(cl && cl.value);
        var h = num(ch && ch.value);
        if (l + h < 1) msg = "Cargo: set Light and/or Heavy seats.";
        else ok = true;
      } else if (m) {
        var yy = num(y && y.value);
        var jj = num(j && j.value);
        var ff = num(f && f.value);
        if (yy + jj + ff < 1) msg = "Passenger: set at least one of Y / J / F.";
        else ok = true;
      } else {
        var yy2 = num(y && y.value);
        var jj2 = num(j && j.value);
        var ff2 = num(f && f.value);
        var l2 = num(cl && cl.value);
        var h2 = num(ch && ch.value);
        if (yy2 + jj2 + ff2 + l2 + h2 < 1) {
          msg = "Unknown type in DB: fill Y/J/F or cargo L/H as a planning check.";
        } else ok = true;
      }

      if (hubOv && hubOv.checked && hubIn) {
        var hi = (hubIn.value || "").trim().toUpperCase();
        if (!/^[A-Z]{3}$/.test(hi)) {
          ok = false;
          msg = "Override hub must be a 3-letter IATA code.";
        }
      }

      if (readyLabel) {
        if (ok) {
          readyLabel.innerHTML =
            "Ready — use <strong>Save route</strong> below to add to fleet and assign.";
          readyLabel.classList.remove("am4-text-secondary");
          readyLabel.classList.add("text-emerald-400/90");
        } else {
          readyLabel.textContent =
            "Configure aircraft and seats/cargo, then use Save route below.";
          readyLabel.classList.add("am4-text-secondary");
          readyLabel.classList.remove("text-emerald-400/90");
        }
      }
      if (hint) hint.textContent = ok ? "" : msg;
      root.setAttribute("data-inline-fleet-ok", ok ? "1" : "0");
    }

    function onAcChange() {
      applyTypeUi(ac.value.trim().toLowerCase());
      gate();
    }

    [
      ac,
      qty,
      y,
      j,
      f,
      cl,
      ch,
      hubOv,
      hubIn,
    ].forEach(function (el) {
      if (!el) return;
      el.addEventListener("input", gate);
      el.addEventListener("change", gate);
    });
    if (ac) ac.addEventListener("change", onAcChange);
    if (hubOv) hubOv.addEventListener("change", syncHubUi);

    syncHubUi();
    onAcChange();
    gate();
  }

  function initFromContainer(container) {
    if (!container || !container.querySelectorAll) return;
    var roots = container.querySelectorAll("[data-inline-fleet-entry]");
    for (var i = 0; i < roots.length; i++) bindRoot(roots[i]);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var mf = document.getElementById("add-route-main");
    if (mf && mf.getAttribute("data-ar-inline-gate") !== "1") {
      mf.setAttribute("data-ar-inline-gate", "1");
      mf.addEventListener("submit", function (ev) {
        var entry = document.querySelector("[data-inline-fleet-entry]");
        if (!entry) return;
        if (entry.getAttribute("data-inline-fleet-ok") !== "1") {
          ev.preventDefault();
          var h = entry.querySelector("#arf-gate-hint");
          if (h && !h.textContent) {
            h.textContent = "Complete the checklist above before saving.";
          }
        }
      });
    }
    initFromContainer(document.getElementById("aircraft-select-target"));
  });

  document.body.addEventListener("htmx:afterSwap", function (evt) {
    var t = evt.detail && evt.detail.target;
    if (t && t.id === "aircraft-select-target") initFromContainer(t);
  });

  window.Am4InlineFleetEntry = { init: initFromContainer };
})();
