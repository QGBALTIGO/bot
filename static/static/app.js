function qs(name) {
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}

async function load() {
  const user_id = qs("user_id");
  const grid = document.getElementById("grid");
  const sub = document.getElementById("sub");

  if (!user_id) {
    sub.textContent = "❌ Falta user_id na URL.";
    return;
  }

  const r = await fetch(`/api/collection?user_id=${encodeURIComponent(user_id)}`);
  const data = await r.json();

  if (!data.ok) {
    sub.textContent = "❌ Erro ao carregar coleção.";
    return;
  }

  const items = data.items || [];
  sub.textContent = `Itens: ${items.length}`;

  grid.innerHTML = "";
  for (const it of items) {
    const card = document.createElement("div");
    card.className = "card";

    const img = document.createElement("img");
    img.src = it.image || "https://via.placeholder.com/300x420?text=No+Image";
    img.alt = it.name || "Personagem";

    const meta = document.createElement("div");
    meta.className = "meta";

    const name = document.createElement("div");
    name.className = "name";
    name.textContent = it.name || "Sem nome";

    const anime = document.createElement("div");
    anime.className = "anime";
    anime.textContent = it.anime_title || "Obra";

    const id = document.createElement("div");
    id.className = "id";
    id.textContent = `ID: ${it.character_id}`;

    meta.appendChild(name);
    meta.appendChild(anime);
    meta.appendChild(id);

    card.appendChild(img);
    card.appendChild(meta);

    grid.appendChild(card);
  }
}

load();
