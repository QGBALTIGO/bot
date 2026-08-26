from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from commands.v2_entry import WebAppEntry, open_webapp_entry


async def _open(update: Update, context: ContextTypes.DEFAULT_TYPE, *, title: str, description: str, button: str, fragment: str = "home", icon: str = "🏴‍☠️") -> None:
    await open_webapp_entry(
        update,
        context,
        WebAppEntry(
            title=title,
            description=description,
            button=button,
            path=f"/hub#{fragment}",
            icon=icon,
        ),
    )


async def hub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open(update,context,title="Baltigo",description="Seu universo anime em um só lugar: explorar, colecionar, jogar, socializar, competir e personalizar.",button="🏴‍☠️ Abrir Baltigo",fragment="home")


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await hub(update,context)


async def favoritos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open(update,context,title="Favoritos & Watchlist",description="Acompanhe obras favoritas, planejadas, assistindo e concluídas.",button="⭐ Abrir Biblioteca",fragment="library",icon="⭐")


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await favoritos(update,context)


async def notificacoes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open(update,context,title="Notificações",description="Controle alertas de jogos, mensagens, notícias, episódios, missões e conquistas.",button="🔔 Abrir Notificações",fragment="notifications",icon="🔔")


async def atividade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open(update,context,title="Minha Atividade",description="Veja sua linha do tempo unificada de jogos, coleção, economia e social.",button="🧾 Ver Atividade",fragment="activity",icon="🧾")


async def amigos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open(update,context,title="Amigos",description="Pedidos de amizade e atalhos para mensagens, trocas e duelos.",button="👥 Abrir Social",fragment="social",icon="👥")


async def missoes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open(update,context,title="Missões",description="Objetivos diários e semanais atravessam jogos, coleção e social, com recompensas na economia principal.",button="✅ Abrir Missões",fragment="missions",icon="✅")


async def conquistas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open(update,context,title="Conquistas & Títulos",description="Marcos da sua jornada desbloqueiam títulos equipáveis no ecossistema Baltigo.",button="🏅 Abrir Conquistas",fragment="achievements",icon="🏅")


async def recomendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open(update,context,title="Recomendações",description="Sugestões usam o que você já coleciona e acompanha para indicar o próximo passo.",button="✨ Ver Recomendações",fragment="home",icon="✨")


async def noticias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open(update,context,title="Notícias",description="Feed prioriza obras da sua biblioteca e favoritos.",button="📰 Abrir Notícias",fragment="explore",icon="📰")


async def agenda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open(update,context,title="Agenda",description="A área de acompanhamento conecta sua watchlist aos próximos episódios disponíveis.",button="📅 Abrir Agenda",fragment="library",icon="📅")


async def configuracoes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open(update,context,title="Configurações",description="Privacidade e preferências ficam centralizadas entre perfil, mensagens e notificações.",button="⚙️ Abrir Configurações",fragment="notifications",icon="⚙️")


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _open(update,context,title="Ajuda Baltigo",description="Navegue por objetivo em vez de decorar dezenas de comandos.",button="🆘 Abrir Central",fragment="home",icon="🆘")
