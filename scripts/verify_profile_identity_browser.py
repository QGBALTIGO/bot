"""Verify the real compiled profile UI with synthetic account data only."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import threading
from http.server import ThreadingHTTPServer

import verify_native_browser as fixtures


def run_tests(output: Path) -> None:
    from playwright.sync_api import sync_playwright

    output.mkdir(parents=True, exist_ok=True)
    report = {"scenarios": [], "checks": [], "page_errors": [], "console_errors": [], "data": "synthetic; no production account requests"}
    original_state = copy.deepcopy(fixtures.STATE)
    original_user = copy.deepcopy(fixtures.USER)
    server = ThreadingHTTPServer(("127.0.0.1", fixtures.PORT), fixtures.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH") or shutil.which("chromium") or shutil.which("google-chrome"), args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
        page.set_default_timeout(12000)
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        page.on("console", lambda msg: report["console_errors"].append(msg.text) if msg.type == "error" else None)
        favorite = {"id": 1, "name": "Personagem favorito de teste", "anime": "Obra do personagem", "image": "/fixture-art/7.svg"}
        try:
            for width in [320, 360, 390, 768, 1280]:
                page.set_viewport_size({"width": width, "height": 844})
                for case in ["favorite", "without-favorite", "missing-art", "long-text"]:
                    fixtures.USER.clear()
                    fixtures.USER.update(copy.deepcopy(original_user))
                    selected = None if case == "without-favorite" else dict(favorite)
                    if case == "missing-art":
                        selected["image"] = ""
                    if case == "long-text":
                        selected["name"] = "Personagem " + "NomeMuitoLongo" * 10
                        selected["anime"] = "Obra " + "TituloMuitoLongo" * 8
                        fixtures.USER["username"] = "usuario_de_teste_com_nome_longo"
                        fixtures.USER["titles"] = {"current": "Colecionador " + "TituloLongo" * 8}
                        fixtures.USER["role_tag"] = "ADMINISTRADOR"
                    fixtures.STATE["favorite"] = selected
                    # Distinct document URLs avoid same-fragment navigation retaining the previous fixture.
                    page.goto(f"http://127.0.0.1:{fixtures.PORT}/menu?fixture_case={case}-{width}#profile")
                    card = page.locator("[data-profile-identity]")
                    card.wait_for()
                    page.wait_for_timeout(140)
                    assert card.count() == 1
                    assert page.locator("main h1").count() == 1
                    assert card.evaluate("e => e.parentElement.firstElementChild === e")
                    expected_name = selected["name"] if selected else fixtures.STATE["nickname"]
                    actual_name = (card.locator("h1").text_content() or "").strip()
                    assert actual_name == expected_name, (case, width, actual_name, expected_name)
                    assert card.locator("[data-profile-username]").inner_text() == "@" + fixtures.USER["username"]
                    assert "LVL 8" in card.inner_text()
                    assert "PASSE GRÁTIS" in card.inner_text()
                    assert "EXPERIÊNCIA" in card.inner_text()
                    assert fixtures.USER["titles"]["current"] in (card.text_content() or "")
                    assert page.locator("[data-profile-favorite]").count() == (1 if selected else 0)
                    if selected:
                        assert (card.locator("[data-profile-work]").text_content() or "").strip() == selected["anime"]
                        if selected["image"]:
                            img = card.locator("[data-profile-avatar] img")
                            assert img.get_attribute("src") == selected["image"]
                            assert img.get_attribute("alt") == selected["name"]
                            assert img.get_attribute("src") != fixtures.USER["avatar"]
                            page.wait_for_function("document.querySelector('[data-profile-avatar] img').naturalWidth > 0")
                        else:
                            assert card.locator("[data-profile-avatar] img").count() == 0
                    else:
                        assert card.locator("[data-profile-work]").count() == 0
                        assert card.locator("[data-profile-avatar] img").get_attribute("src") == fixtures.USER["avatar"]
                    geometry = card.evaluate("""e => {
                        const c=e.getBoundingClientRect();
                        const inside=Array.from(e.querySelectorAll('h1,p,button,span')).every(n=>{const r=n.getBoundingClientRect();return r.width===0||(r.left>=c.left-1&&r.right<=c.right+1&&r.top>=c.top-1&&r.bottom<=c.bottom+1)});
                        const badges=e.querySelector('[data-profile-badges]').getBoundingClientRect();
                        const xp=e.querySelector('[data-profile-experience]').getBoundingClientRect();
                        return {inside,ordered:xp.top>=badges.bottom-1,overflow:document.documentElement.scrollWidth>innerWidth+1};
                    }""")
                    assert geometry["inside"], (case, width, geometry)
                    assert geometry["ordered"] and not geometry["overflow"], (case, width, geometry)
                    if case in ("favorite", "without-favorite"):
                        page.screenshot(path=str(output / f"profile-{case}-{width}.png"))
                    report["scenarios"].append({"case": case, "width": width, "single_card": True, "layout": geometry})
            report["checks"].append("single profile card, favorite artwork/name/work, account badges/XP, absence/missing art/long text in five viewport sizes")

            fixtures.USER.clear()
            fixtures.USER.update(copy.deepcopy(original_user))
            fixtures.STATE["favorite"] = dict(favorite)
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(f"http://127.0.0.1:{fixtures.PORT}/menu?fixture_case=interactive#profile")
            card = page.locator("[data-profile-identity]")
            card.get_by_role("button", name="Alterar personagem favorito", exact=True).click()
            page.get_by_role("button", name="Alterar favorito", exact=True).click()
            page.get_by_role("textbox", name="Buscar personagem favorito").fill("02")
            page.get_by_role("button", name="Favoritar Personagem 02", exact=True).wait_for()
            before_me = fixtures.STATE["gets"].count("/api/v1_7b82/me")
            page.get_by_role("button", name="Favoritar Personagem 02", exact=True).click()
            page.get_by_role("dialog", name="Escolher personagem favorito").wait_for(state="hidden")
            page.get_by_role("button", name="Ir para o painel", exact=True).click()
            card.get_by_role("heading", name="Personagem 02", exact=True).wait_for()
            assert card.locator("[data-profile-avatar] img").get_attribute("src") == fixtures.STATE["favorite"]["image"]
            assert fixtures.STATE["gets"].count("/api/v1_7b82/me") == before_me
            page.reload()
            card.get_by_role("heading", name="Personagem 02", exact=True).wait_for()
            card.get_by_role("button", name="Alterar personagem favorito", exact=True).click()
            page.get_by_role("button", name="Remover favorito", exact=True).click()
            page.get_by_role("button", name="Escolher favorito", exact=True).wait_for()
            page.get_by_role("button", name="Ir para o painel", exact=True).click()
            card.get_by_role("heading", name=fixtures.STATE["nickname"], exact=True).wait_for()
            assert card.locator("[data-profile-avatar] img").get_attribute("src") == fixtures.USER["avatar"]
            assert page.locator("[data-profile-favorite]").count() == 0
            report["checks"].append("avatar opens favorite settings, changing favorite updates the same profile without another /me request, reload persists, removal restores account identity")
            assert not report["page_errors"] and not report["console_errors"], report
            report["passed"] = True
        except Exception as error:
            report["failure"] = repr(error)
            page.screenshot(path=str(output / "failure.png"))
            raise
        finally:
            (output / "profile-identity-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
            browser.close()
            fixtures.STATE.clear()
            fixtures.STATE.update(original_state)
            fixtures.USER.clear()
            fixtures.USER.update(original_user)
            server.shutdown()
            server.server_close()
    print(json.dumps({"passed": True, "scenarios": len(report["scenarios"]), "checks": report["checks"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("profile-identity-proof"))
    run_tests(parser.parse_args().output)
