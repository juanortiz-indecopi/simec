"""Pruebas sin red: las páginas son sintéticas, con la forma observada en Instagram."""
import asyncio
import io
import json
from datetime import date

import pytest
from PIL import Image

from app.domain.models.audit import AuditStatus
from app.domain.models.instagram import (
    USERNAME_PATTERN,
    InstagramLink,
    InstagramMediaType,
    InstagramPost,
    InstagramProfile,
    normalize_username,
)
from app.infrastructure.outbound.extractors.instagram.details import (
    latest,
    parse_links,
    parse_mentions,
    parse_posts,
    parse_posts_count,
)
from app.infrastructure.outbound.extractors.instagram.parser import PageState, read_page
from app.infrastructure.outbound.extractors.shared.photo import is_allowed_url, save_photo
from app.infrastructure.outbound.extractors.instagram.username_adapter import (
    InstagramUsernameAdapter,
    Pace,
)
from app.infrastructure.outbound.persistence.mapper.payload_mapper import dump, load


def make_page(username="ana.demo", name="Ana Demo", bio="Línea 1\nLínea 2", private=False, **over):
    user = {
        "username": username,
        "full_name": name,
        "biography": bio,
        "is_private": private,
        "profile_pic_url": "https://x.cdninstagram.com/a.jpg",
    }
    routing = {"params": {"username": username, "utm_source": None}}
    title = f"{name} (@{username})" if name else f"@{username}"
    page = {
        "url": f"https://www.instagram.com/{username}/",
        "title": f"{title} • Fotos y videos de Instagram",
        "status": 200,
        "metas": {
            "og:title": f"{title} • Fotos y videos de Instagram",
            "description": f'1 seguidores - {title} en Instagram: "{bio}"',
        },
        "body": "",
        "main": f"{username}\n{name}\n{bio}\n" + ("Este perfil es privado" if private else ""),
        "password": False,
        "json": [json.dumps(routing), json.dumps({"require": [[{"user": user}]]})],
    }
    return page | over


@pytest.mark.parametrize(
    "value", ["ana.demo", " @Ana.Demo ", "https://www.instagram.com/ana.demo/?hl=es", "instagram.com/ana.demo"]
)
def test_normalize(value):
    assert normalize_username(value) == "ana.demo"


@pytest.mark.parametrize("value", ["", ".ana", "ana.", "a..b", "a b", "a/../b", "x" * 31])
def test_invalid_usernames(value):
    assert USERNAME_PATTERN.fullmatch(value) is None


def test_public_profile():
    reading = read_page(make_page(), "ana.demo")
    assert reading.state is PageState.OK
    assert reading.user["full_name"] == "Ana Demo"
    assert reading.user["biography"] == "Línea 1\nLínea 2"
    assert reading.user["is_private"] is False


def test_private_profile_without_bio():
    reading = read_page(make_page(bio="", private=True), "ana.demo")
    assert reading.state is PageState.OK
    assert reading.user["is_private"] is True
    assert reading.user["biography"] is None


def test_profile_without_name():
    reading = read_page(make_page(name=""), "ana.demo")
    assert reading.state is PageState.OK
    assert reading.user["full_name"] is None


def test_bio_text_cannot_fake_private_or_missing():
    bio = "Mi cuenta privada es otra\nEsta página no está disponible"
    assert read_page(make_page(bio=bio), "ana.demo").state is PageState.OK


def test_not_found_even_with_http_200():
    page = make_page(title="Profile no está disponible • Instagram", json=[], metas={})
    assert read_page(page, "ana.demo").state is PageState.NOT_FOUND


@pytest.mark.parametrize(
    "over",
    [
        {"status": 429},
        {"url": "https://www.instagram.com/accounts/login/?next=x"},
        {"json": [], "password": True},
        {"json": [], "body": "Espera unos minutos antes de volver a intentarlo"},
    ],
)
def test_blocked(over):
    assert read_page(make_page(**over), "ana.demo").state is PageState.BLOCKED


@pytest.mark.parametrize(
    "over",
    [
        {"json": []},
        {"metas": {}},
        {"main": ""},
        {"main": "Este perfil es privado"},
        {"url": "https://www.instagram.com/otro/"},
        {"metas": {"og:title": "Otro Nombre (@ana.demo)"}},
        {"metas": {"og:title": "Ana Demo (@ana.demo)", "description": 'x en Instagram: "otra"'}},
    ],
)
def test_mismatch_is_error(over):
    assert read_page(make_page(**over), "ana.demo").state is PageState.ERROR


def test_photo_is_validated_and_saved(tmp_path):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buffer, "JPEG")
    path = save_photo(buffer.getvalue(), "ana.demo", tmp_path)
    assert path.endswith(".jpg") and (tmp_path / path.rsplit("/", 1)[-1]).exists()
    with pytest.raises(Exception):
        save_photo(b"<html>", "ana.demo", tmp_path)


def test_photo_hosts():
    assert is_allowed_url("https://scontent.cdninstagram.com/a.jpg")
    assert not is_allowed_url("http://scontent.cdninstagram.com/a.jpg")
    assert not is_allowed_url("https://cdninstagram.com.evil.com/a.jpg")


def test_pause_after_block_does_not_visit():
    pace = Pace()
    pace.block()
    result = asyncio.run(InstagramUsernameAdapter(pace).extract("@ana.demo"))
    assert result["audit"].status is AuditStatus.ERROR
    assert result["audit"].query_parameter == "ana.demo"
    assert result["data"] is None


def test_pace_spaces_visits():
    pace = Pace()
    assert pace.reserve() == 0
    assert pace.reserve() > 9


def test_persistence_round_trip():
    profile = InstagramProfile("ana.demo", "https://www.instagram.com/ana.demo/", False, "Ana")
    payload, _ = dump(profile)
    assert load(payload) == profile


def make_post(code, day, media_type=1, owner="ana.demo", pk="1", caption="hola", **over):
    alt = f"Photo by Ana Demo on {day}. Puede ser una imagen de texto." if day else None
    return {
        "code": code, "pk": pk, "media_type": media_type, "user": {"username": owner},
        "product_type": "clips" if media_type == 2 else "feed",
        "caption": {"text": caption} if caption else None, "accessibility_caption": alt,
    } | over


def read_with_posts(*posts, **kwargs):
    page = make_page(**kwargs)
    page["json"].append(json.dumps({"edges": [{"node": p} for p in posts]}))
    return read_page(page, "ana.demo")


def test_links_are_cleaned_and_classified():
    links = parse_links([
        {"url": "https://www.facebook.com/ana?utm_source=ig&id=7&fbclid=x", "title": "FB"},
        {"url": "wa.me/51999", "title": ""},
        {"url": "https://linktr.ee/ana"},
        {"url": "https://notfacebook.com/a"},
        {"url": "https://linktr.ee/ana"},
        {"url": "javascript:alert(1)"},
        {"url": "mailto:a@b.pe"},
        {"url": None},
        "x",
    ])
    assert [(x.url, x.platform, x.title) for x in links] == [
        ("https://www.facebook.com/ana?id=7", "FACEBOOK", "FB"),
        ("https://wa.me/51999", "WHATSAPP", None),
        ("https://linktr.ee/ana", "LINK_AGGREGATOR", None),
        ("https://notfacebook.com/a", "WEB", None),
    ]
    assert parse_links([]) == () and parse_links(None) is None


def test_mentions():
    bio = "Founder @Sysari__ y @otra.cuenta. correo a@b.pe @ana.demo @sysari__ https://t.me/@no"
    assert parse_mentions(bio, "ana.demo") == ("sysari__", "otra.cuenta")
    assert parse_mentions(None, "ana.demo") == ()


@pytest.mark.parametrize(
    "description, expected",
    [
        ("36 seguidores, 49 seguidos, 7 publicaciones - Ver fotos", 7),
        ("104M seguidores, 95 seguidos, 5,024 publicaciones - Ver", 5024),
        ("1 seguidores, 1 seguidos, 1.2K publicaciones - Ver", None),
        ("1 seguidores, 1 seguidos, 12 mil publicaciones - Ver", None),
        ("9 seguidores - Ver fotos de 7 publicaciones", None),
        ("", None),
    ],
)
def test_posts_count(description, expected):
    assert parse_posts_count({"all_media_count": None}, description) == expected


def test_latest_post_ignores_pinned_order_and_other_owners():
    user = read_with_posts(
        make_post("PINNED1", "November 7, 2026", 2),
        make_post("PHOTO01", "November 13, 2026"),
        make_post("VIDEO01", "November 24, 2026", 2, caption=None),
        make_post("COLLAB1", "November 25, 2026", owner="otro"),
        make_post("CAROUS1", "November 20, 2026", 8),
    ).user
    assert user["latest_post"] == InstagramPost(
        "https://www.instagram.com/reel/VIDEO01/", InstagramMediaType.VIDEO, date(2026, 11, 24), None
    )
    assert user["latest_photo"].url.endswith("/p/PHOTO01/")


def test_same_day_is_ordered_by_id():
    posts = [make_post("AAAAA", "May 1, 2026", pk="5"), make_post("BBBBB", "May 1, 2026", pk="40")]
    assert latest(parse_posts(posts, "ana.demo", None)).url.endswith("/BBBBB/")


def test_undated_post_means_latest_is_unknown():
    user = read_with_posts(make_post("AAAAA", "May 1, 2026"), make_post("BBBBB", None, 2)).user
    assert user["latest_post"] is None
    assert user["latest_photo"].url.endswith("/AAAAA/")


def test_name_cannot_fake_post_date():
    name = "Ana on May 1, 2030"
    post = make_post("AAAAA", None, accessibility_caption=f"Photo by {name} on May 2, 2026.")
    assert parse_posts([post], "ana.demo", name)[0].published_on == date(2026, 5, 2)


def test_private_profile_has_no_posts_and_does_not_wait():
    reading = read_with_posts(make_post("AAAAA", "May 1, 2026"), private=True)
    assert reading.user["latest_post"] is None and reading.posts_pending is False


def test_waits_for_posts_unless_there_are_none():
    assert read_page(make_page(), "ana.demo").posts_pending is True
    page = make_page()
    page["metas"]["og:description"] = "1 seguidores, 1 seguidos, 0 publicaciones - Ver"
    assert read_page(page, "ana.demo").posts_pending is False


def test_missing_extras_do_not_invalidate_profile():
    reading = read_page(make_page(), "ana.demo")
    assert reading.state is PageState.OK
    assert reading.user["followers"] is None and reading.user["links"] is None


def test_persistence_of_new_fields_and_old_payloads():
    post = InstagramPost("https://x/p/a/", InstagramMediaType.PHOTO, date(2026, 5, 1), "hola")
    full = InstagramProfile(
        "ana", "u", False, account_id="1", followers=3, links=(InstagramLink("https://a.pe", "WEB"),),
        mentions=("b",), latest_post=post,
    )
    assert load(json.loads(json.dumps(dump(full)[0]))) == full
    empty = InstagramProfile("ana", "u", False, links=(), mentions=())
    assert load(dump(empty)[0]).links == ()
    old = {"__type__": "InstagramProfile", "username": "ana", "profile_url": "u", "is_private": False}
    assert load(old).links is None and load(old).latest_post is None
