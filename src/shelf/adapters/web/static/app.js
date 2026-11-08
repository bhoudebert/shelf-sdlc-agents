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

  // "Copy" buttons: data-copy="#selector" copies that element's text, then says so for a moment.
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-copy]");
    if (!button) return;
    var source = document.querySelector(button.getAttribute("data-copy"));
    if (!source) return;
    var label = button.textContent;
    var done = function () {
      button.textContent = button.getAttribute("data-done") || "Copied";
      setTimeout(function () { button.textContent = label; }, 2000);
    };
    var text = source.innerText;
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { selectText(source); });
    } else {
      selectText(source);
    }
  });
  function selectText(node) {
    var range = document.createRange();
    range.selectNodeContents(node);
    var selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }

  // Private-key helper: turns a .pem into the one-line value a .env file needs. Everything happens in the browser.
  Array.prototype.forEach.call(document.querySelectorAll("[data-pem]"), function (root) {
    var file = root.querySelector("[data-pem-file]");
    var text = root.querySelector("[data-pem-text]");
    var out = root.querySelector("[data-pem-out]");
    var copy = root.querySelector("[data-pem-copy]");
    var error = root.querySelector("[data-pem-error]");
    function show(raw) {
      var pem = (raw || "").replace(/\r/g, "").trim();
      var ok = /-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(pem) && /-----END [A-Z ]*PRIVATE KEY-----/.test(pem);
      out.hidden = copy.hidden = ok ? false : true;
      error.hidden = ok || !pem;
      if (!ok) { error.textContent = pem ? "That does not look like a private key. It should start with -----BEGIN RSA PRIVATE KEY-----." : ""; return; }
      out.querySelector("code").textContent = 'GITHUB_APP_PRIVATE_KEY="' + pem.split("\n").map(function (l) { return l.trim(); }).filter(Boolean).join("\\n") + '"';
    }
    file.addEventListener("change", function () {
      var chosen = file.files && file.files[0];
      if (!chosen) return;
      var reader = new FileReader();
      reader.onload = function () { text.value = String(reader.result); show(text.value); };
      reader.readAsText(chosen);
    });
    text.addEventListener("input", function () { show(text.value); });
  });
})();
