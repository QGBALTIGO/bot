const tg = window.Telegram?.WebApp;
if (tg) {
tg.ready();
tg.expand();
}

const INIT_DATA = tg?.initData || "";

/* TODO O RESTO DO SEU JS ORIGINAL AQUI */

function escapeHtml(s){
...
}

function apiGet(url){
...
}

function renderCollection(){
...
}

function loadCollection(){
...
}

loadCollection();
