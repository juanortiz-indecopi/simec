"""Pruebas sin red ni base de datos: páginas sintéticas con la forma observada en Facebook."""
import json
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.application.port.out.extractor_port import ExtractorPort
from app.application.services.get_facebook_page_service import GetFacebookPageService
from app.core.dependencies import get_facebook_page_use_case
from app.domain.models.audit import AuditResult, AuditStatus
from app.domain.models.facebook import (
    CompanyFacts,
    FacebookField,
    FacebookLink,
    FacebookMediaType,
    FacebookPage,
    FacebookPost,
    MatchResult,
    normalize_page,
)
from app.domain.models.profile import CompanyProfile
from app.domain.models.query import QueryType
from app.domain.models.sunat import SunatProfile
from app.domain.services.facebook_verification import split_legal_form, verify_page
from app.infrastructure.outbound.extractors.facebook.parser import (
    PageState,
    merge,
    parse_ad_status,
    parse_fields,
    parse_spanish_date,
    read_main,
    read_section,
)
from app.infrastructure.outbound.persistence.mapper.payload_mapper import dump, load
from app.main import app
from tests.test_instagram_endpoint import BrokenRepository, FakeRepository

RUC = "20603687478"


# ------------------------------------------------------------------ parámetro page
@pytest.mark.parametrize(
    "value, expected",
    [
        ("codideep", "codideep"),
        (" @CodiDeep ", "codideep"),
        ("NASA", "nasa"),
        ("https://www.facebook.com/codideep", "codideep"),
        ("http://m.facebook.com/codideep/?locale=es_LA&x=1", "codideep"),
        ("facebook.com/codideep/about", "codideep"),
        ("https://es-la.facebook.com/pg/codideep/", "codideep"),
        ("https://www.facebook.com/profile.php?id=100063518592455&sk=about", "100063518592455"),
        ("https://www.facebook.com/people/Mi-Empresa/100063518592455/", "100063518592455"),
        ("https://www.facebook.com/p/Mi-Empresa-100063518592455/", "100063518592455"),
        ("100063518592455", "100063518592455"),
        ("20603687478", None),  # RUC
        ("CODIDEEP E.I.R.L.", None),
        ("https://www.facebook.com/codideep/posts/123", None),
        ("https://www.facebook.com/groups/123", None),
        ("https://www.facebook.com/share/abc/", None),
        ("https://www.facebook.com/", None),
        ("www.facebook.com", None),
        ("https://facebook.com.evil.com/codideep", None),
        ("https://evil.com/codideep", None),
        ("http://[", None),
        ("../x", None),
        ("", None),
    ],
)
def test_normalize_page(value, expected):
    assert normalize_page(value) == expected


# ------------------------------------------------------------------ parser
def card(kind, title, url=None):
    return {
        "timeline_context_list_item_type": f"INTRO_CARD_{kind}",
        "renderer": {"context_item": {"title": {"text": title}, "url": url}},
    }


def tab_field(kind, title, link_url=None):
    return {"field_type": kind, "title": {"text": title}, "link_url": link_url}


def story(post_id="9", created=1793726188, owner="100", text="hola", media="Photo", feedback=True):
    ufi = {
        "reaction_count": {"count": 3}, "share_count": {"count": 2},
        "comment_rendering_instance": {"comments": {"total_count": 1}},
    }
    return {
        "__typename": "Story", "post_id": post_id, "creation_time": created,
        "permalink_url": f"https://www.facebook.com/acme/posts/{post_id}",
        "actors": [{"id": owner}],
        "attachments": [{"media": {"__typename": media}}] if media else [],
        "comet_sections": {
            "content": {"story": {"message": {"text": text} if text else None}},
            "feedback": {"deep": ufi} if feedback else {},
        },
    }


def make_page(*nodes, name="Acme Perú", city="Abancay", header=None, **over):
    user = {
        "name": name, "id": "100", "url": "https://www.facebook.com/acme.peru",
        "delegate_page": {"id": "55"}, "show_verified_badge_on_profile": False,
        "profilePicLarge": {"uri": "https://x.fbcdn.net/a.jpg"},
        "profile_social_context": {"content": [{"text": {"text": "1,1\xa0mil seguidores"}}, {"text": {"text": "2 seguidos"}}]},
    } | (header or {})
    page = {
        "url": "https://www.facebook.com/acme.peru/", "status": 200, "body": "Iniciar sesión",
        "metas": {
            "og:title": f"{name} | {city} ", "al:android:url": "fb://profile/100",
            "og:description": f"{name}, {city}. 1.164\xa0seguidores · 3 personas están hablando de esto. Hola",
        },
        "json": [
            json.dumps({"user": {"profile_header_renderer": {"user": user}}}),
            json.dumps({"delegate_page": {"id": "55", "best_description": {"text": "Somos Acme"}}}),
            json.dumps(list(nodes)),
        ],
    }
    return page | over


def test_reads_page():
    reading = read_main(
        make_page(
            card("INFLUENCER_CATEGORY", "Página · Empresa de software"),
            card("ADDRESS", "Jr. Uno 1, Abancay, Peru"),
            card("CONFIRMED_OWNER_LABEL", "ACME S.A.C."),
            card("PROFILE_PHONE", "968 498 437"),
            card("PROFILE_EMAIL", "a@acme.pe"),
            card("WEBSITE", "acme.pe", "https://l.facebook.com/l.php?u=https%3A%2F%2Facme.pe%2F%3Futm_source%3Dfb&h=x"),
            card("BUSINESS_HOURS", "Siempre abierto"),
            card("NUEVO_TIPO", "dato"),
            story(),
        ),
        "acmeperu",  # Facebook ignora los puntos.
    )
    f = reading.fields
    assert reading.state is PageState.OK and reading.pending is False
    assert (f["account_id"], f["page_id"], f["name"], f["city"]) == ("100", "55", "Acme Perú", "Abancay")
    assert (f["followers"], f["following"], f["talking_about"]) == (1164, 2, 3)
    assert f["category"] == "Empresa de software" and f["description"] == "Somos Acme"
    assert f["responsible"] == "ACME S.A.C." and f["business_hours"] == "Siempre abierto"
    assert f["phones"] == ("968 498 437",) and f["emails"] == ("a@acme.pe",)
    assert f["links"] == (FacebookLink("https://acme.pe/", "WEB"),)
    assert f["other_info"] == (FacebookField("nuevo_tipo", "dato"),)
    post = f["latest_post"]
    assert (post.text, post.reactions, post.comments, post.shares) == ("hola", 3, 1, 2)
    assert post.media_type is FacebookMediaType.PHOTO
    assert post.published_at == datetime.fromtimestamp(1793726188, timezone.utc)


def test_login_form_is_not_a_block():
    assert read_main(make_page(body="Correo electrónico\nContraseña\nIniciar sesión"), "100").state is PageState.OK


def test_name_cannot_fake_followers():
    name = "Acme 999 seguidores"
    assert read_main(make_page(name=name), "100").fields["followers"] == 1164


@pytest.mark.parametrize("key", ["100", "55", "acme.peru"])
def test_identity_by_id_or_username(key):
    assert read_main(make_page(), key).state is PageState.OK


def test_personal_profile_is_not_read():
    reading = read_main(make_page(header={"delegate_page": None}), "100")
    assert reading.state is PageState.NOT_A_PAGE and reading.fields == {}


@pytest.mark.parametrize(
    "over, state",
    [
        ({"json": [], "body": "Este contenido no está disponible en este momento"}, PageState.NOT_FOUND),
        ({"json": [], "body": "Estás bloqueado temporalmente"}, PageState.BLOCKED),
        ({"status": 429}, PageState.BLOCKED),
        ({"url": "https://www.facebook.com/login/?next=x"}, PageState.BLOCKED),
        ({"json": []}, PageState.ERROR),
        ({"metas": {}}, PageState.ERROR),
        ({"metas": {"og:title": "Acme Perú", "al:android:url": "fb://profile/999"}}, PageState.ERROR),
    ],
)
def test_states(over, state):
    assert read_main(make_page(**over), "100").state is state


def test_other_page_is_error():
    assert read_main(make_page(), "otra").state is PageState.ERROR


def test_latest_post_ignores_other_authors_and_order():
    reading = read_main(
        make_page(story("1", 100), story("2", 300, text=None, media=None), story("3", 999, owner="777")), "100"
    )
    post = reading.fields["latest_post"]
    assert post.post_id == "2" and post.text is None and post.media_type is FacebookMediaType.NONE


def test_missing_counts_are_null():
    post = read_main(make_page(story(feedback=False)), "100").fields["latest_post"]
    assert post.reactions is None and post.comments is None


def test_sections_complete_without_duplicates():
    main = read_main(
        make_page(card("PROFILE_PHONE", "968 498 437"), card("WEBSITE", "acme.pe", "https://acme.pe/")), "100"
    ).fields
    about = read_section(
        make_page(
            tab_field("profile_phone", "+51 968498437"), tab_field("website", "http://www.acme.pe"),
            tab_field("profile_email", "A@acme.pe"), tab_field("instagram", "acme", "https://instagram.com/acme"),
            tab_field("category", "Otra"),
        ),
        "100",
    )
    transparency = read_section(
        make_page(
            tab_field("page_id", "55"), tab_field("creation_date", "27 de abril de 2016"),
            tab_field("ad_status", "Esta página no tiene anuncios en circulación."), tab_field("admin_info", "x"),
        ),
        "100",
    )
    merged = merge(merge(main, about.fields), transparency.fields)
    assert merged["phones"] == ("968 498 437",) and merged["emails"] == ("A@acme.pe",)
    assert [(x.url, x.platform) for x in merged["links"]] == [
        ("https://acme.pe/", "WEB"), ("https://instagram.com/acme", "INSTAGRAM")
    ]
    assert merged["created_on"] == date(2016, 4, 27) and merged["has_active_ads"] is False
    assert merged["other_info"] == ()


def test_section_of_other_page_is_rejected():
    assert read_section(make_page(tab_field("page_id", "1")), "999").state is PageState.ERROR


def test_unsafe_link_is_not_a_link():
    fields = parse_fields([json.dumps([card("WEBSITE", "x", "javascript:alert(1)")])])
    assert fields["links"] == ()


def test_momentary_hours_and_repeated_owner():
    fields = parse_fields([json.dumps([
        card("BUSINESS_HOURS", "Abierto ahora"), card("CONFIRMED_OWNER_LABEL", "ACME S.A.C."),
        tab_field("confirmed_owner", "ACME S.A.C. es responsable de esta página."),
    ])])
    assert "business_hours" not in fields and fields["responsible"] == "ACME S.A.C." and fields["other_info"] == ()


def test_small_parsers():
    assert parse_spanish_date("31 de foo de 2020") is None and parse_spanish_date("31 de febrero de 2020") is None
    assert parse_ad_status("Esta página tiene anuncios en circulación.") is True
    assert parse_ad_status("otra cosa") is None


# ------------------------------------------------------------------ verificación
def page(name="CODIDEEP EIRL", **over):
    return FacebookPage("k", "u", "1", name, **({"city": "Abancay"} | over))


CODIDEEP = CompanyFacts(RUC, ("CODIDEEP E.I.R.L.",), ("AV. MARTINELLI MZA. B",), ("ABANCAY",), ("Principal - 6201 - X",))
AMERICA = CompanyFacts(
    "20601590175", ("AMERICA SERVICES AND SOLUTIONS S.A.C.",),
    ("JR. SANTA ROSA NRO. 116 CERCADO ABANCAY APURIMAC - ABANCAY - ABANCAY",), ("ABANCAY",), ("Principal - 6190 - X",),
)
AMERICA_PAGE = page(
    "Internet Apurímac America Services", category="Proveedor de internet", address="Jr. Santa Rosa 116- Abancay, Peru"
)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Inversiones Huayna del Perú E.I.R.L.", ("INVERSIONES HUAYNA DEL PERU", "EIRL")),
        ("ACME S.A.C.", ("ACME", "SAC")),
        ("ACME SOCIEDAD ANONIMA CERRADA", ("ACME", "SAC")),
        ("ACME S.A.", ("ACME", "SA")),
        ("ACME S.R.L.", ("ACME", "SRL")),
        ("ACME EMPRESA INDIVIDUAL DE RESPONSABILIDAD LIMITADA", ("ACME", "EIRL")),
        ("Casa", ("CASA", None)),
    ],
)
def test_legal_form(name, expected):
    assert split_legal_form(name) == expected


def test_real_cases():
    assert verify_page(page(), CODIDEEP).result is MatchResult.PROBABLE
    assert verify_page(AMERICA_PAGE, AMERICA).result is MatchResult.PROBABLE
    assert verify_page(page(), AMERICA).result is MatchResult.NO_EVIDENCE
    assert verify_page(AMERICA_PAGE, CODIDEEP).result is MatchResult.NO_EVIDENCE


def test_city_alone_or_different_number_is_not_enough():
    assert verify_page(page("Pollos Don Pepe"), CODIDEEP).result is MatchResult.NO_EVIDENCE
    other = page("Librería Sol", address="Jr. Santa Rosa 1160, Abancay")
    assert verify_page(other, AMERICA).result is MatchResult.NO_EVIDENCE


def test_same_name_elsewhere_or_other_legal_form_is_only_possible():
    assert verify_page(page("Codideep", city="Tacna"), CODIDEEP).result is MatchResult.POSSIBLE
    assert verify_page(page("CODIDEEP SAC"), CODIDEEP).result is MatchResult.POSSIBLE


def test_part_of_distinctive_name_is_only_possible():
    saga = CompanyFacts("20100128056", ("SAGA FALABELLA S A",), places=("LIMA",))
    result = verify_page(page("Falabella.com Perú", city=None), saga)
    assert result.result is MatchResult.POSSIBLE
    assert result.reasons == ("Coincide una palabra distintiva del nombre",)


def test_ruc_or_responsible_is_probable():
    assert verify_page(page("Marca X", city=None, description=f"RUC: {RUC}"), CODIDEEP).result is MatchResult.PROBABLE
    assert verify_page(page("Marca X", city=None, description=f"9{RUC}"), CODIDEEP).result is MatchResult.NO_EVIDENCE
    assert verify_page(page("Marca X", responsible="CODIDEEP EIRL"), CODIDEEP).result is MatchResult.PROBABLE


# ------------------------------------------------------------------ persistencia y endpoint
def test_persistence_round_trip():
    full = FacebookPage(
        "k", "u", "1", "n", phones=("1",), links=(FacebookLink("https://a.pe", "WEB"),), created_on=date(2016, 4, 27),
        other_info=(FacebookField("a", "b"),),
        latest_post=FacebookPost("9", "u", datetime(2026, 1, 1, tzinfo=timezone.utc), FacebookMediaType.PHOTO, "t", 1, 2, 3),
    )
    assert load(json.loads(json.dumps(dump(full)[0]))) == full


class Fake(ExtractorPort):
    def __init__(self, name, data):
        self._name, self.data, self.calls = name, data, 0

    @property
    def source_name(self):
        return self._name

    async def extract(self, parameter):
        self.calls += 1
        status = AuditStatus.SUCCESS if self.data else AuditStatus.ERROR
        audit = AuditResult(self._name, parameter, 1, status, None, datetime.now(timezone.utc))
        return {"audit": audit, "data": self.data, "raw": None}


@pytest.fixture
def env():
    fb = Fake("FACEBOOK_PAGE", page())
    profile = Fake("P", CompanyProfile(RUC, "CODIDEEP E.I.R.L.", district="ABANCAY", province="ABANCAY"))
    sunat = Fake("S", SunatProfile(RUC, economic_activities=("Principal - 6201 - X",)))
    repository = FakeRepository()
    service = GetFacebookPageService(fb, profile, sunat, snapshots=repository)
    app.dependency_overrides[get_facebook_page_use_case] = lambda: service
    yield TestClient(app), fb, profile, sunat, repository
    app.dependency_overrides.clear()


def get(client, **params):
    return client.get("/api/v1/facebook/pages", params=params)


def test_without_ruc_only_reads(env):
    client, fb, profile, _, _ = env
    body = get(client, page="https://www.facebook.com/codideep?x=1&y=2").json()
    assert body["requested_page"] == "codideep" and body["verification"] is None
    assert body["page"]["name"] == "CODIDEEP EIRL" and profile.calls == 0


def test_cache_refresh_and_verification(env):
    client, fb, profile, sunat, repository = env
    first = get(client, page="codideep", ruc=RUC).json()
    second = get(client, page="CODIDEEP", ruc=RUC).json()
    third = get(client, page="codideep", ruc=RUC, refresh=True).json()
    assert [x["served_from"] for x in (first, second, third)] == ["LIVE", "DATABASE", "MIXED"]
    assert all(x["verification"]["result"] == "PROBABLE" for x in (first, second, third))
    assert (fb.calls, profile.calls, sunat.calls) == (2, 1, 1)  # refresh no repite las fuentes de la empresa
    keys = {(o.query_type, o.cache_key) for o in repository.saved}
    assert keys == {(QueryType.FACEBOOK_PAGE, "codideep"), (QueryType.COMPANY_BY_RUC, RUC)}
    assert all(o.subject is None for o in repository.saved if o.query_type is QueryType.FACEBOOK_PAGE)


def test_failed_refresh_keeps_data(env):
    client, fb, *_ = env
    get(client, page="codideep")
    fb.data = None
    body = get(client, page="codideep", refresh=True).json()
    assert body["page"]["name"] == "CODIDEEP EIRL" and body["audit_entries"][0]["status"] == "ERROR"


def test_not_evaluated(env):
    client, fb, profile, sunat, _ = env
    assert get(client, page="codideep", ruc="10449009521").json()["verification"]["result"] == "NOT_EVALUATED"
    assert profile.calls == 0
    profile.data = sunat.data = None
    assert get(client, page="codideep", ruc=RUC).json()["verification"]["result"] == "NOT_EVALUATED"
    fb.data = None
    assert get(client, page="nadie", ruc=RUC).json()["verification"]["result"] == "NOT_EVALUATED"


@pytest.mark.parametrize("params", [{}, {"page": RUC}, {"page": "Codideep Abancay"}, {"page": "codideep", "ruc": "123"}])
def test_invalid_parameters(env, params):
    assert get(env[0], **params).status_code == 422
    assert env[1].calls == 0


def test_database_down_still_answers():
    service = GetFacebookPageService(
        Fake("FACEBOOK_PAGE", page()), Fake("P", None), Fake("S", None), snapshots=BrokenRepository()
    )
    app.dependency_overrides[get_facebook_page_use_case] = lambda: service
    try:
        assert get(TestClient(app), page="codideep").json()["served_from"] == "LIVE"
    finally:
        app.dependency_overrides.clear()
