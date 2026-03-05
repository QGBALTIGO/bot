# repair_anilist_all.py
# ✅ Repara AniList (capas/infos) em 2 arquivos: ANIME + MANGA
# ✅ Sem dependências externas (NÃO usa requests) — só biblioteca padrão
# ✅ Sobrescreve os MESMOS arquivos em data/
# ✅ Só tenta corrigir quem está com anilist == null

import os
import json
import re
import time
import difflib
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

ANILIST_URL = "https://graphql.anilist.co"
UA = "SourceBaltigoRepair/1.0 (+https://t.me/SourceBaltigoBot)"

# ====== CONFIG: quais arquivos reparar ======
TARGETS = [
    {
        "label": "ANIME",
        "media_type": "ANIME",
        "path": os.getenv("ANIME_JSON", "data/catalogo_enriquecido.json"),
    },
    {
        "label": "MANGA",
        "media_type": "MANGA",
        "path": os.getenv("MANGA_JSON", "data/catalogo_mangas_enriquecido.json"),
    },
]

QUERY = """
query ($search: String, $type: MediaType) {
  Page(perPage: 10) {
    media(search: $search, type: $type) {
      id
      type
      format
      status
      seasonYear
      episodes
      chapters
      volumes
      averageScore
      popularity
      title { romaji english native }
      coverImage { extraLarge large medium color }
      bannerImage
      siteUrl
    }
  }
}
"""

def _http_post_json(url: str, payload: dict, timeout: int = 25) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": UA,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8", errors="replace")
    return json.loads(data)

def norm_title(s: str) -> str:
    s = (s or "").strip()

    # remove emojis/símbolos comuns que poluem busca
    s = re.sub(r"[|•·★☆✅❌⚠️🔥🎴✨📚📢🏴‍☠️⚔️▶️⏳💬📺⭐]+", " ", s)

    # remove conteúdos entre colchetes/parênteses
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = re.sub(r"\([^\)]*\)", " ", s)

    # remove hashtags
    s = re.sub(r"#\w+", " ", s)

    # normaliza espaços
    s = re.sub(r"\s+", " ", s).strip()

    # corta depois de separadores comuns
    for sep in [" | ", " — ", " - ", " – ", " / ", " • ", "｜", "–"]:
        if sep in s:
            s = s.split(sep)[0].strip()

    # tira sufixos comuns
    s = re.sub(r"\b(legendado|dublado|hd|fullhd|completo|completa)\b", "", s, flags=re.I).strip()
    s = re.sub(r"\s+", " ", s).strip()

    return s

def title_candidates(rec: dict) -> List[str]:
    cands: List[str] = []

    raw = (rec.get("title_raw") or rec.get("titulo") or rec.get("title") or "").strip()
    if raw:
        cands.append(raw)

    rt = (rec.get("raw_text") or "").strip()
    if rt:
        first = rt.splitlines()[0].strip()
        if first:
            cands.append(first)

    # às vezes o canal/botão tem nome útil
    mb = (rec.get("main_button_url") or "").strip()
    if mb and "t.me/" in mb:
        # pega slug do t.me/slug
        slug = mb.split("t.me/")[-1].strip("/")
        if slug and len(slug) >= 3:
            # slug pode ter underline; transforma em título
            cands.append(slug.replace("_", " "))

    # variações normalizadas + sem pontuação pesada
    extra: List[str] = []
    for s in cands:
        n = norm_title(s)
        if n:
            extra.append(n)
        n2 = re.sub(r"[^\w\s]", " ", n, flags=re.UNICODE)
        n2 = re.sub(r"\s+", " ", n2).strip()
        if n2 and n2 != n:
            extra.append(n2)

    # remove duplicados mantendo ordem
    seen = set()
    out: List[str] = []
    for s in cands + extra:
        ss = (s or "").strip()
        if not ss:
            continue
        key = ss.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(ss)
    return out[:6]

def unwrap_records(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return [x for x in data["records"] if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    # tenta encontrar uma lista em chaves comuns
    if isinstance(data, dict):
        for k in ("items", "data", "results", "animes", "mangas", "catalogo"):
            v = data.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    raise RuntimeError("JSON em formato inesperado (precisa ser lista ou {'records': [...]})")

def extract_year(rec: dict) -> Optional[int]:
    y = rec.get("year_post")
    try:
        if y is None:
            return None
        if isinstance(y, bool):
            return None
        return int(y)
    except Exception:
        return None

def fetch_anilist(search: str, media_type: str) -> List[dict]:
    payload = {"query": QUERY, "variables": {"search": search, "type": media_type}}
    data = _http_post_json(ANILIST_URL, payload, timeout=25)
    media = data.get("data", {}).get("Page", {}).get("media", []) or []
    if not isinstance(media, list):
        return []
    return [m for m in media if isinstance(m, dict)]

def best_match(search: str, media: List[dict], year_hint: Optional[int]) -> Tuple[Optional[dict], float]:
    s_norm = norm_title(search).lower()
    best = None
    best_score = -1.0

    for m in media:
        t = m.get("title") or {}
        titles = [
            (t.get("romaji") or ""),
            (t.get("english") or ""),
            (t.get("native") or ""),
        ]

        local_best = 0.0
        for tt in titles:
            tt_n = norm_title(tt).lower()
            if not tt_n:
                continue
            score = difflib.SequenceMatcher(None, s_norm, tt_n).ratio()
            local_best = max(local_best, score)

        # bônus se bater o ano
        if year_hint and m.get("seasonYear") == year_hint:
            local_best += 0.06

        if local_best > best_score:
            best_score = local_best
            best = m

    return best, best_score

def build_anilist_obj(m: dict) -> dict:
    t = m.get("title") or {}
    title_display = (t.get("english") or t.get("romaji") or t.get("native") or "").strip()

    cov = m.get("coverImage") or {}
    cover = (cov.get("extraLarge") or cov.get("large") or cov.get("medium") or "").strip()

    return {
        "id": m.get("id"),
        "type": m.get("type"),
        "format": m.get("format"),
        "status": m.get("status"),
        "seasonYear": m.get("seasonYear"),
        "averageScore": m.get("averageScore"),
        "popularity": m.get("popularity"),
        "title": t,
        "title_display": title_display,
        "cover": cover,
        "bannerImage": (m.get("bannerImage") or "").strip(),
        "siteUrl": (m.get("siteUrl") or "").strip(),
    }

def repair_file(path: str, media_type: str, label: str, sleep_s: float = 0.85) -> None:
    if not os.path.exists(path):
        print(f"[{label}] ❌ Arquivo não encontrado: {path}")
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = unwrap_records(data)
    total = len(records)

    fixed = 0
    tried = 0
    skipped_has = 0
    failures = 0

    print(f"\n[{label}] 🚀 Iniciando reparo AniList — {total} registros — arquivo: {path}")

    for idx, rec in enumerate(records, start=1):
        if rec.get("anilist"):
            skipped_has += 1
            continue

        cands = title_candidates(rec)
        if not cands:
            continue

        tried += 1
        year_hint = extract_year(rec)

        found = False
        best_any = None
        best_any_score = -1.0
        best_any_search = ""

        for cand in cands:
            search = norm_title(cand)
            if len(search) < 2:
                continue

            try:
                media = fetch_anilist(search, media_type)
                best, score = best_match(search, media, year_hint=year_hint)

                if best and score > best_any_score:
                    best_any = best
                    best_any_score = score
                    best_any_search = search

                # threshold: evita match errado
                if best and score >= 0.62:
                    rec["anilist"] = build_anilist_obj(best)
                    fixed += 1
                    found = True
                    print(f"[{label}] [OK] {idx}/{total} | '{cands[0]}' -> '{rec['anilist']['title_display']}' (score={score:.2f} via '{search}')")
                    break
            except urllib.error.HTTPError as e:
                failures += 1
                print(f"[{label}] [ERR] {idx}/{total} | HTTPError {e.code} | '{cands[0]}'")
                break
            except Exception as e:
                failures += 1
                print(f"[{label}] [ERR] {idx}/{total} | {type(e).__name__}: {e} | '{cands[0]}'")
                break
            finally:
                time.sleep(sleep_s)

        if not found:
            # log “melhor tentativa” pra você debugar
            if best_any is not None:
                t = best_any.get("title") or {}
                disp = (t.get("english") or t.get("romaji") or t.get("native") or "").strip()
                print(f"[{label}] [NO] {idx}/{total} | '{cands[0]}' (best='{disp}' score={best_any_score:.2f} via '{best_any_search}')")
            else:
                print(f"[{label}] [NO] {idx}/{total} | '{cands[0]}' (sem retorno do AniList)")

    # salva no mesmo arquivo
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        data["records"] = records
    elif isinstance(data, list):
        data = records
    else:
        # fallback: coloca em records
        data = {"records": records}

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(
        f"[{label}] ✅ Finalizado | Corrigidos: {fixed} | Tentados: {tried} | Já tinham AniList: {skipped_has} | Falhas: {failures}\n"
        f"[{label}] 💾 Sobrescrito: {path}"
    )

def main():
    for t in TARGETS:
        repair_file(t["path"], t["media_type"], t["label"], sleep_s=0.85)

    print("\n🏁 Tudo pronto! Agora reinicie o webapp/bot para o catálogo refletir as capas e infos.")

if __name__ == "__main__":
    main()
