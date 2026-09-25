"""Single Portuguese help catalog reused by bot and MiniApp."""

TOPICS = [
    {
        "id": "collection",
        "title": "Coleção, desejos e proteção",
        "text": "Favorito representa você no perfil. Desejado é quem você quer conseguir. Protegido não sai da coleção sem desbloqueio. Reservado participa de uma troca ou anúncio. Na Oficina, a última cópia nunca é consumida.",
        "tab": "collecting",
        "command": "/colecionar",
    },
    {
        "id": "trading",
        "title": "Trocas e confirmações",
        "text": "Confira os dois lados da proposta. A criação confirma a oferta inicial do autor. Uma alteração remove os aceites e exige nova confirmação dos dois participantes. Ofertas antigas não podem confirmar uma revisão nova.",
        "tab": "trading",
        "command": "/trocar",
    },
    {
        "id": "market",
        "title": "Mercado e leilões",
        "text": "O preço é o total do lote, em Coins. A carta fica reservada. Lances ficam em garantia; quando você é superado, seus Coins voltam. Leilões com lance não podem ser cancelados. Lances nos dois minutos finais podem estender o prazo, no máximo dez minutos além do prazo original.",
        "tab": "marketplace",
        "command": "/mercado",
    },
    {
        "id": "workshop",
        "title": "Oficina de duplicatas",
        "text": "Cada cópia excedente rende um fragmento. Fragmentos criam cosméticos e não são dinheiro nem podem ser transferidos. A prévia mostra exatamente quais cópias serão consumidas.",
        "tab": "workshop",
        "command": "/oficina",
    },
    {
        "id": "events",
        "title": "Eventos e expedições",
        "text": "Somente eventos revisados pela administração ficam disponíveis. Contribua com um personagem elegível da sua coleção, sem perder a carta. O servidor controla prazo, limites diários e meta coletiva. Recompensas são cosméticas e só podem ser resgatadas uma vez.",
        "tab": "events",
        "command": "/eventos",
    },
    {
        "id": "privacy",
        "title": "Privacidade e compartilhamento",
        "text": "A descoberta de parceiros e a vitrine inline começam desativadas. Ative apenas o que deseja usar. Perfis privados não aparecem na descoberta. Compartilhar uma ficha não publica sua coleção inteira.",
        "tab": "collecting",
        "command": "/colecionar",
    },
    {
        "id": "activity",
        "title": "Presença e recompensas",
        "text": "O resgate diário segue o horário de São Paulo. O mesmo registro vale no comando e na MiniApp. Sete presenças consecutivas liberam um emblema, sem multiplicar Coins.",
        "tab": "activity",
        "command": "/agora",
    },
    {
        "id": "support",
        "title": "Algo não funcionou?",
        "text": "Atualize o aplicativo quando solicitado e tente a ação novamente. Nunca compartilhe token, sessão ou senha com outras pessoas. Um botão antigo pode exigir uma nova confirmação para proteger sua coleção.",
        "tab": "settings",
        "command": "/menu",
    },
]
