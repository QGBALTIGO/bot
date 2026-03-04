const tg = window.Telegram?.WebApp;

if (tg) {
    tg.ready();
    tg.expand();
}

const headers = {
    "X-Telegram-Init-Data": tg.initData
};

async function api(url, method = "GET", body = null) {

    const res = await fetch(url, {
        method: method,
        headers: {
            "Content-Type": "application/json",
            ...headers
        },
        body: body ? JSON.stringify(body) : null
    });

    return await res.json();
}

//////////////////////////
// COLEÇÃO
//////////////////////////

async function loadCollection() {

    const data = await api("/api/me/collection");

    if (!data.ok) return;

    document.getElementById("coins").innerText = data.coins;
    document.getElementById("giros").innerText = data.giros;

    const grid = document.getElementById("cards");

    if (!grid) return;

    grid.innerHTML = "";

    data.cards.forEach(card => {

        const el = document.createElement("div");

        el.className = "card";

        el.innerHTML = `
        <img src="${card.image}">
        <div class="card-info">
            <div class="card-name">${card.character_name}</div>
            <div class="card-anime">${card.anime_title}</div>
        </div>
        `;

        grid.appendChild(el);

    });

}

//////////////////////////
// LOJA
//////////////////////////

async function loadShop() {

    const data = await api("/api/shop/state");

    if (!data.ok) return;

    const coins = document.getElementById("coins");

    if (coins) coins.innerText = data.coins;

}

async function buyGiro() {

    const data = await api("/api/shop/buy/giro", "POST");

    const status = document.getElementById("status");

    if (status) status.innerText = JSON.stringify(data);

    loadShop();

}

//////////////////////////
// DADO
//////////////////////////

async function rollDice() {

    const data = await api("/api/dado/start", "POST");

    const result = document.getElementById("result");

    if (!data.ok) {

        result.innerText = "Erro ao rolar dado";
        return;

    }

    result.innerText = "Resultado do dado: " + data.roll;

}

//////////////////////////
// AUTO LOAD
//////////////////////////

if (document.getElementById("cards")) {
    loadCollection();
}

if (document.getElementById("coins")) {
    loadShop();
}
