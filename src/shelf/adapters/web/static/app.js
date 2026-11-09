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

  // Sections that refresh themselves (the work panel, the documents) must never fight the person using them:
  // no refresh while the pointer is over the section, while focus is inside it, or while text is selected in it.
  // The server also answers "nothing changed" with 204, so an idle refresh does not touch the page at all.
  function inUse(section) {
    if (section.matches(":hover")) return true;
    if (section.contains(document.activeElement) && document.activeElement !== document.body) return true;
    var selection = window.getSelection && window.getSelection();
    return !!(selection && !selection.isCollapsed && section.contains(selection.anchorNode));
  }
  document.body.addEventListener("htmx:beforeRequest", function (event) {
    var section = event.detail.elt;
    if (!section || (section.id !== "panel" && section.id !== "documents" && section.id !== "conversation")) return;
    if (event.detail.requestConfig && event.detail.requestConfig.verb !== "get") return; // a decision is never held back
    if (inUse(section)) event.preventDefault();
  });

  // A refreshed conversation keeps what the person had opened: the sections are folded by default, so a redraw would
  // otherwise close them again under their eyes.
  var opened = [];
  document.body.addEventListener("htmx:beforeSwap", function (event) {
    var section = event.detail.target;
    if (!section || section.id !== "conversation") return;
    opened = Array.prototype.map.call(section.querySelectorAll("details[open][data-key]"), function (d) {
      return d.getAttribute("data-key");
    });
  });
  document.body.addEventListener("htmx:afterSettle", function () {
    var section = document.getElementById("conversation");
    if (!section || !opened.length) return;
    opened.forEach(function (key) {
      var d = section.querySelector('details[data-key="' + key + '"]');
      if (d) d.open = true;
    });
    opened = [];
  });

  // The board is pushed by the server: hold a push while the pointer is over the list, and catch up when it leaves.
  var board = document.getElementById("board");
  if (board) {
    var behind = false;
    document.body.addEventListener("htmx:sseBeforeMessage", function (event) {
      if (board.matches(":hover") && board.querySelector(".item:hover, .item-link:hover, button:hover, a:hover")) {
        event.preventDefault();
        behind = true;
      }
    });
    board.addEventListener("mouseleave", function () {
      if (!behind) return;
      behind = false;
      if (window.htmx) window.htmx.ajax("GET", "/board/items", { target: "#board", swap: "innerHTML" });
    });
  }

  var lastHtml = {};
  document.body.addEventListener("htmx:beforeSwap", function (event) {
    var target = event.detail.target;
    if (!target || (target.id !== "panel" && target.id !== "documents")) return;
    // A refused decision answers 403 with the panel and its explanation: show it.
    if (target.id === "panel" && event.detail.xhr.status === 403) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
      lastHtml.panel = "";
      return;
    }
    // Do not replace a section with an identical copy: that would reset focus, folded documents and motion.
    var html = event.detail.serverResponse;
    if (html === lastHtml[target.id]) event.detail.shouldSwap = false;
    lastHtml[target.id] = html;
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
})();
