// Marks each calendar square as past, today or future, using the visitor's date.
// (Done in the browser so "today" is right even if the site was built yesterday.)
(function () {
  const pad = (n) => String(n).padStart(2, "0");
  const now = new Date();
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  document.querySelectorAll(".tile[data-date]").forEach((tile) => {
    const date = tile.dataset.date;
    tile.classList.add(date === today ? "is-today" : date < today ? "is-past" : "is-future");
  });
})();
