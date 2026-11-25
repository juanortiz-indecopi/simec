"""Endpoint completo con extractor y repositorio falsos: sin red ni base de datos."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.application.port.out.extractor_port import ExtractorPort
from app.application.port.out.snapshot_repository_port import (
    PersistenceError,
    SnapshotRepositoryPort,
)
from app.application.services.get_instagram_service import GetInstagramService
from app.core.dependencies import get_instagram_use_case
from app.domain.models.audit import AuditResult, AuditStatus
from app.domain.models.instagram import InstagramProfile
from app.domain.models.query import FetchMode, StoredSnapshot
from app.main import app

URL = "/api/v1/instagram/"


class FakeExtractor(ExtractorPort):
    source_name = "INSTAGRAM_PROFILE"

    def __init__(self):
        self.calls = []
        self.name = "Ana"
        self.status = AuditStatus.SUCCESS

    async def extract(self, parameter):
        self.calls.append(parameter)
        ok = self.status is AuditStatus.SUCCESS
        return {
            "audit": AuditResult(
                self.source_name, parameter, 5, self.status, None if ok else "falló", datetime.now(timezone.utc)
            ),
            "data": InstagramProfile(parameter, "https://www.instagram.com/x/", False, self.name) if ok else None,
            "raw": None,
        }


class FakeRepository(SnapshotRepositoryPort):
    def __init__(self):
        self.current = {}
        self.saved = []

    async def find_current(self, source_names, cache_key):
        return {n: self.current[n, cache_key] for n in source_names if (n, cache_key) in self.current}

    async def try_begin_refresh(self, source_names, cache_key, lease):
        return frozenset(source_names)

    async def refreshing(self, source_names, cache_key, lease):
        return frozenset()

    async def end_refresh(self, source_names, cache_key):
        pass

    async def save_outcome(self, outcome):
        self.saved.append(outcome)
        for e in outcome.executions:
            if e.audit.status is AuditStatus.SUCCESS:
                self.current[e.audit.source_name, outcome.cache_key] = StoredSnapshot(
                    len(self.saved), e.audit.source_name, e.data, e.audit.executed_at_utc
                )


class BrokenRepository(FakeRepository):
    async def find_current(self, *_):
        raise PersistenceError("caída")

    try_begin_refresh = refreshing = end_refresh = save_outcome = find_current


@pytest.fixture
def env():
    extractor, repository = FakeExtractor(), FakeRepository()
    service = GetInstagramService(extractor, snapshots=repository)
    app.dependency_overrides[get_instagram_use_case] = lambda: service
    yield TestClient(app), extractor, repository
    app.dependency_overrides.clear()


def test_first_live_then_database(env):
    client, extractor, repository = env
    first, second = client.get(URL + "@Ana.Demo").json(), client.get(URL + "ana.demo").json()
    assert (first["served_from"], second["served_from"]) == ("LIVE", "DATABASE")
    assert first["profile"] == second["profile"]
    assert second["audit_entries"][0]["from_cache"] is True
    assert extractor.calls == ["ana.demo"]
    assert len(repository.saved) == 2  # Ambas consultas quedan registradas.


def test_refresh_goes_to_web_and_updates(env):
    client, extractor, repository = env
    client.get(URL + "ana")
    extractor.name = "Ana Nueva"
    body = client.get(URL + "ana?refresh=true").json()
    assert body["served_from"] == "LIVE" and body["profile"]["full_name"] == "Ana Nueva"
    assert repository.saved[-1].fetch_mode is FetchMode.REFRESH
    assert client.get(URL + "ana").json()["profile"]["full_name"] == "Ana Nueva"
    assert len(extractor.calls) == 2


@pytest.mark.parametrize("failure", [AuditStatus.ERROR, AuditStatus.NO_DATA])
def test_failed_refresh_keeps_stored_data(env, failure):
    client, extractor, _ = env
    client.get(URL + "ana")
    extractor.status = failure
    body = client.get(URL + "ana?refresh=true").json()
    assert body["profile"]["full_name"] == "Ana"
    assert body["audit_entries"][0]["status"] == failure.value
    assert body["audit_entries"][0]["from_cache"] is True


def test_not_found_is_not_cached(env):
    client, extractor, _ = env
    extractor.status = AuditStatus.NO_DATA
    assert client.get(URL + "nadie").json()["profile"] is None
    client.get(URL + "nadie")
    assert len(extractor.calls) == 2


@pytest.mark.parametrize("value", ["a..b", ".ana", "a b", "x" * 31])
def test_invalid_username(env, value):
    client, extractor, _ = env
    assert client.get(URL + value).status_code == 422
    assert extractor.calls == []


def test_missing_photo_file_has_no_url(env):
    client, _, repository = env
    profile = InstagramProfile("ana", "u", False, photo_path="files/instagram/no_existe.jpg")
    repository.current["INSTAGRAM_PROFILE", "ana"] = StoredSnapshot(
        1, "INSTAGRAM_PROFILE", profile, datetime.now(timezone.utc)
    )
    assert client.get(URL + "ana").json()["profile"]["photo_url"] is None


def test_database_down_still_answers():
    service = GetInstagramService(FakeExtractor(), snapshots=BrokenRepository())
    app.dependency_overrides[get_instagram_use_case] = lambda: service
    try:
        body = TestClient(app).get(URL + "ana").json()
    finally:
        app.dependency_overrides.clear()
    assert body["served_from"] == "LIVE" and body["profile"]["full_name"] == "Ana"
