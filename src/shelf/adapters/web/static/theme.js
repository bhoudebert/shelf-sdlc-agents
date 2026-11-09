// Applies a remembered theme before the first paint. Without one the page is dark.
(function () {
  try {
    var saved = localStorage.getItem("shelf-theme");
    if (saved === "dark" || saved === "light") document.documentElement.setAttribute("data-theme", saved);
  } catch (e) {}
  if (!document.documentElement.getAttribute("data-theme")) document.documentElement.setAttribute("data-theme", "dark");
  document.documentElement.classList.add("js");
})();
