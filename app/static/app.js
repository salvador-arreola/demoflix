const grid = document.getElementById("grid");
const form = document.getElementById("movie-form");
const msg = document.getElementById("form-message");
const submitBtn = document.getElementById("submit-btn");
const emptyHint = document.getElementById("empty-hint");

function showMessage(text, ok) {
  msg.hidden = false;
  msg.textContent = text;
  msg.className = "form-message " + (ok ? "ok" : "error");
}

function hideMessage() {
  msg.hidden = true;
  msg.textContent = "";
  msg.className = "form-message";
}

function card(movie) {
  const el = document.createElement("article");
  el.className = "card";
  el.innerHTML = `
    <img src="${movie.poster_url}" alt="" loading="lazy" />
    <div class="title-overlay">${escapeHtml(movie.title)}</div>
  `;
  return el;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

async function loadMovies() {
  const res = await fetch("/api/movies");
  if (!res.ok) throw new Error("Could not load catalog");
  return res.json();
}

function render(movies) {
  grid.innerHTML = "";
  emptyHint.hidden = movies.length > 0;
  for (const m of movies) {
    grid.appendChild(card(m));
  }
}

async function refresh() {
  try {
    const movies = await loadMovies();
    render(movies);
  } catch (e) {
    showMessage(e.message || "Network error", false);
  }
}

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  hideMessage();
  const fd = new FormData(form);
  submitBtn.disabled = true;
  try {
    const res = await fetch("/api/movies", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      let text = "Upload failed";
      if (typeof detail === "string") text = detail;
      else if (Array.isArray(detail))
        text = detail.map((e) => e.msg || JSON.stringify(e)).join("; ");
      showMessage(text, false);
      return;
    }
    showMessage(
      "Saved: poster object in Cloud Storage and catalog.json updated",
      true
    );
    form.reset();
    await refresh();
  } catch (e) {
    showMessage(e.message || "Network error", false);
  } finally {
    submitBtn.disabled = false;
  }
});

refresh();
