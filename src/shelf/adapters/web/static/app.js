// shelf-sdlc: the small amount of script the interface needs. Everything works without it,
// except the theme toggle, the board filter and the confirmation before a destructive decision.
(function () {
  var root = document.documentElement;

  // Theme toggle: remembers a manual choice, otherwise the system decides.
  var toggle = document.getElementById("theme");
  function currentTheme() {
    var t = root.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  if (toggle) {
    toggle.setAttribute("aria-pressed", String(currentTheme() === "dark"));
    toggle.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("shelf-theme", next); } catch (e) {}
      toggle.setAttribute("aria-pressed", String(next === "dark"));
    });
  }

  // Board filter. The filter lives on #board itself, which is never replaced, so it survives live updates.
  var board = document.getElementById("board");
  var buttons = document.querySelectorAll(".filters button");
  function count() {
    if (!board) return;
    var total = 0;
    ["waiting", "running", "done"].forEach(function (key) {
      var n = board.querySelectorAll('.group[data-group="' + key + '"] .item').length;
      total += n;
      var el = document.querySelector('[data-count="' + key + '"]');
      if (el) el.textContent = n ? String(n) : "0";
    });
    var bar = document.querySelector(".filters");
    if (bar) bar.hidden = total === 0;
    var all = document.querySelector('[data-count="all"]');
    if (all) all.textContent = String(total);
  }
  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      board.setAttribute("data-filter", button.getAttribute("data-filter"));
      buttons.forEach(function (b) { b.setAttribute("aria-pressed", String(b === button)); });
    });
  });
  count();
  document.body.addEventListener("htmx:sseMessage", function () { setTimeout(count, 0); });
  document.body.addEventListener("htmx:afterSwap", count);

  // Ask before a decision that ends the work.
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-confirm]");
    if (button && !window.confirm(button.getAttribute("data-confirm"))) event.preventDefault();
  });

  // The work panel refreshes itself every few seconds. Do not replace it while someone is typing
  // a note, and do not replace it with an identical copy (that would reset focus and replay motion).
  var lastPanel = "";
  document.body.addEventListener("htmx:beforeRequest", function (event) {
    var panel = document.getElementById("panel");
    if (!panel || event.detail.elt !== panel) return;
    var note = panel.querySelector("textarea");
    if ((note && note.value) || panel.contains(document.activeElement)) event.preventDefault();
  });
  document.body.addEventListener("htmx:beforeSwap", function (event) {
    var target = event.detail.target;
    if (!target || target.id !== "panel") return;
    // A refused decision answers 403 with the panel and its explanation: show it.
    if (event.detail.xhr.status === 403) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
      lastPanel = "";
      return;
    }
    var html = event.detail.serverResponse;
    if (html === lastPanel) event.detail.shouldSwap = false;
    lastPanel = html;
  });
})();
