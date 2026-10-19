// Orbital Agents site behaviour: mobile navigation, billing switch, FAQ accordion, demo form.
(function () {
  "use strict";

  // ---- mobile navigation -------------------------------------------------------------
  var toggle = document.getElementById("nav-toggle");
  var nav = document.getElementById("primary-nav");
  function setNav(open) {
    toggle.setAttribute("aria-expanded", String(open));
    nav.classList.toggle("is-open", open);
  }
  toggle.addEventListener("click", function () {
    setNav(toggle.getAttribute("aria-expanded") !== "true");
  });
  nav.addEventListener("click", function (e) {
    if (e.target.closest("a") && toggle.getAttribute("aria-expanded") === "true") setNav(false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
      setNav(false);
      toggle.focus();
    }
  });

  // ---- billing switch ----------------------------------------------------------------
  var billing = document.getElementById("billing-toggle");
  var billingWrap = billing.closest(".billing");
  billing.addEventListener("click", function () {
    var annual = billing.getAttribute("aria-checked") !== "true";
    billing.setAttribute("aria-checked", String(annual));
    billingWrap.classList.toggle("is-annual", annual);
    document.querySelectorAll("[data-price]").forEach(function (el) {
      el.textContent = annual ? el.dataset.annual : el.dataset.monthly;
    });
    document.querySelectorAll("[data-billing-note]").forEach(function (el) {
      el.textContent = annual ? "billed annually" : " ";
    });
  });

  // ---- FAQ accordion -----------------------------------------------------------------
  document.querySelectorAll("#faq button[aria-controls]").forEach(function (btn) {
    var panel = document.getElementById(btn.getAttribute("aria-controls"));
    btn.addEventListener("click", function () {
      var open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(open));
      panel.hidden = !open;
    });
  });

  // ---- demo form ---------------------------------------------------------------------
  var form = document.getElementById("demo-form");
  var status = document.getElementById("form-status");
  var EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  var rules = [
    ["name", function (f) { return f.value.trim() !== ""; }, "Please enter your full name."],
    ["email", function (f) { return EMAIL.test(f.value.trim()); }, "Please enter a valid work email address."],
    ["company", function (f) { return f.value.trim() !== ""; }, "Please enter your company name."],
    ["team_size", function (f) { return f.value !== ""; }, "Please select your team size."],
    ["consent", function (f) { return f.checked; }, "Please accept to be contacted."]
  ];

  function setError(field, message) {
    var err = document.getElementById("err-" + field.name);
    if (message) {
      field.setAttribute("aria-invalid", "true");
      err.textContent = message;
    } else {
      field.removeAttribute("aria-invalid");
      err.textContent = "";
    }
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    status.textContent = "";
    var firstInvalid = null;
    rules.forEach(function (rule) {
      var field = form.elements[rule[0]];
      var ok = rule[1](field);
      setError(field, ok ? "" : rule[2]);
      if (!ok && !firstInvalid) firstInvalid = field;
    });
    if (firstInvalid) {
      firstInvalid.focus();
      return;
    }
    form.reset();
    status.textContent = "Thanks! Our team will contact you within one business day.";
  });

  // Clear an error as soon as the field becomes valid ("input" fires while typing, so the
  // layout never shifts under the pointer at blur time).
  rules.forEach(function (rule) {
    var field = form.elements[rule[0]];
    var evt = field.type === "checkbox" || field.tagName === "SELECT" ? "change" : "input";
    field.addEventListener(evt, function () {
      if (field.getAttribute("aria-invalid") === "true" && rule[1](field)) setError(field, "");
    });
  });
})();
