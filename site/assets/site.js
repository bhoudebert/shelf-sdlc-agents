(function () {
  var root = document.documentElement;
  root.classList.add("js");

  // Theme toggle: remembers a manual choice, otherwise follows the system.
  var btn = document.getElementById("theme");
  function current() {
    var t = root.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  if (btn) {
    btn.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("shelf-theme", next); } catch (e) {}
      btn.setAttribute("aria-pressed", String(next === "dark"));
    });
    btn.setAttribute("aria-pressed", String(current() === "dark"));
  }

  // Copy buttons on code blocks.
  document.querySelectorAll("pre").forEach(function (pre) {
    var b = document.createElement("button");
    b.type = "button"; b.className = "copy"; b.textContent = "Copy";
    b.setAttribute("aria-label", "Copy this code");
    b.addEventListener("click", function () {
      var text = pre.querySelector("code").innerText;
      var done = function () { b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1600); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () {});
    });
    pre.appendChild(b);
  });

  // Entrances: content is visible by default and only hidden once this script runs.
  var items = document.querySelectorAll(".rise");
  if (!("IntersectionObserver" in window)) { items.forEach(function (e) { e.classList.add("in"); }); return; }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } });
  }, { threshold: 0.12 });
  items.forEach(function (e) { io.observe(e); });
})();
