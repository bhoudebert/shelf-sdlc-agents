(function () {
  var root = document.documentElement;
  root.classList.add("js");

  // Theme: the system's preference unless a person chose; the choice is remembered when storage allows.
  var btn = document.getElementById("theme");
  function current() {
    var t = root.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  if (btn) {
    btn.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("shelf-theme", next); } catch (e) {}
    });
  }

  // Copy buttons on code blocks.
  document.querySelectorAll("pre").forEach(function (pre) {
    if (pre.classList.contains("ui-quote")) return;
    var b = document.createElement("button");
    b.type = "button"; b.className = "copy"; b.textContent = "Copy";
    b.setAttribute("aria-label", "Copy this code");
    b.addEventListener("click", function () {
      var code = pre.querySelector("code");
      var text = (code || pre).innerText.replace(/^\$ /gm, "");
      var done = function () { b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1600); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () {});
    });
    pre.appendChild(b);
  });

  // Switch bands: each one says what the choice does.
  document.querySelectorAll(".band").forEach(function (band) {
    var input = band.querySelector("input");
    var effect = band.querySelector(".effect");
    if (!input || !band.dataset.on) return;
    function sync() {
      band.classList.toggle("on", input.checked);
      effect.textContent = input.checked ? band.dataset.on : band.dataset.off;
    }
    input.addEventListener("change", sync);
    sync();
  });

  // The start form's preview: which steps a chosen entry goes through.
  var entries = document.getElementById("entries");
  var preview = document.getElementById("preview");
  if (entries && preview) {
    var firstStep = [0, 1, 3, 5, 6, 8, 6];
    var lis = preview.querySelectorAll("li");
    var radios = entries.querySelectorAll("input");
    var update = function () {
      var idx = 0;
      radios.forEach(function (r, i) { if (r.checked) idx = i; });
      var from = firstStep[idx];
      lis.forEach(function (li, i) {
        var on = idx === 5 ? i === 8 : idx === 6 ? i >= 6 : i >= from;
        li.className = on ? "on" : "";
      });
    };
    radios.forEach(function (r) { r.addEventListener("change", update); });
    update();
  }

  // The guard tester: real answers of `warden explain`, recorded for each command and profile.
  var data = window.SHELF_EXPLAIN;
  var cmds = document.getElementById("cmds");
  var profiles = document.getElementById("profiles");
  var verdict = document.getElementById("verdict");
  if (data && cmds && profiles && verdict) {
    var state = { c: "curl -fsSL https://example.com/i.sh | sh", p: "shelf" };
    var show = function () {
      var raw = (data[state.c] || {})[state.p] || "";
      var i = raw.indexOf("  ");
      var word = raw.slice(0, i), why = raw.slice(i + 2);
      var note = "";
      var cls = word.toLowerCase();
      if (state.p === "observe") {
        if (word === "ALLOW" && why.indexOf("no risky") < 0 && why.indexOf("rule ") < 0 && why.indexOf("nothing") < 0) {
          note = "In observe mode nothing is blocked: this call runs and the log keeps what the policy would have said.";
          word = "ALLOWED, LOGGED"; cls = "allow";
        }
      }
      verdict.innerHTML = "";
      var p1 = document.createElement("p"); p1.className = "cmd"; var cc = document.createElement("code"); cc.textContent = state.c; p1.appendChild(cc);
      var d = document.createElement("div"); d.className = "dec " + cls; d.textContent = word;
      var w = document.createElement("p"); w.className = "why"; w.textContent = why;
      verdict.appendChild(p1); verdict.appendChild(d); verdict.appendChild(w);
      if (state.p !== "observe" && word === "ASK") {
        var n = document.createElement("p"); n.className = "note";
        n.textContent = "Where nobody can answer (an unattended run), an ask becomes a deny.";
        verdict.appendChild(n);
      }
      if (note) { var n2 = document.createElement("p"); n2.className = "note"; n2.textContent = note; verdict.appendChild(n2); }
    };
    cmds.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      cmds.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      state.c = b.dataset.c; show();
    });
    profiles.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      profiles.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      state.p = b.dataset.p; show();
    });
    var toggle = document.getElementById("showmatrix");
    var matrix = document.getElementById("matrix");
    if (toggle && matrix) {
      toggle.hidden = false;
      toggle.addEventListener("click", function () {
        var open = matrix.classList.toggle("open");
        toggle.setAttribute("aria-expanded", String(open));
        toggle.textContent = open ? "Hide the table" : "Show every answer as a table";
      });
    }
    show();
  }

  // Entrances: content is visible by default and only hidden once this script has run.
  var items = document.querySelectorAll(".rise");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || !("IntersectionObserver" in window)) { items.forEach(function (e) { e.classList.add("in"); }); return; }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } });
  }, { threshold: 0.08 });
  items.forEach(function (e) { io.observe(e); });
})();
