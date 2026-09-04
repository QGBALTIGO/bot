from __future__ import annotations

from webapp_services.terms import TERMS_HTML, TERMS_LONG, TERMS_VERSION, TEXTS, pick_lang


def test_terms_language_selection_preserves_existing_fallbacks() -> None:
    assert pick_lang("pt-BR") == "pt"
    assert pick_lang("es-MX") == "es"
    assert pick_lang("en-US") == "en"
    assert pick_lang("fr") == "en"
    assert pick_lang(None) == "en"


def test_terms_text_catalog_preserves_three_languages_and_revision() -> None:
    assert set(TEXTS) == {"pt", "en", "es"}
    assert TEXTS["pt"]["title"] == "Termos de Uso e Privacidade"
    assert TEXTS["en"]["title"] == "Terms of Use & Privacy"
    assert TEXTS["es"]["title"] == "Términos de Uso y Privacidad"
    assert TERMS_VERSION
    assert TERMS_VERSION in TEXTS["pt"]["subtitle"]
    assert TERMS_VERSION in TEXTS["en"]["subtitle"]
    assert TERMS_VERSION in TEXTS["es"]["subtitle"]


def test_terms_long_content_and_html_contract_are_preserved() -> None:
    assert set(TERMS_LONG) == {"pt", "en", "es"}
    assert "SUA PRIVACIDADE" in TERMS_LONG["pt"]
    assert "YOUR PRIVACY" in TERMS_LONG["en"]
    assert "TU PRIVACIDAD" in TERMS_LONG["es"]

    for placeholder in (
        "__UID__",
        "__LANG__",
        "__LANGCODE__",
        "__TITLE__",
        "__BODY__",
        "__JOINBLOCK__",
        "__TOPBANNER__",
        "__BGURL__",
        "__TVERSION__",
    ):
        assert placeholder in TERMS_HTML

    assert '/api/terms/accept' in TERMS_HTML
    assert '/api/terms/decline' in TERMS_HTML
