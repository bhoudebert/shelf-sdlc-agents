// Applies a remembered theme before the first paint. Without it the page follows the system.
(function () {
  try {
    var saved = localStorage.getItem("shelf-theme");
    if (saved === "dark" || saved === "light") document.documentElement.setAttribute("data-theme", saved);
  } catch (e) {}
  document.documentElement.classList.add("js");
})();
