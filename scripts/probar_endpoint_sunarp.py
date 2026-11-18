"""Prueba la ruta /sunarp/partidas con un extractor falso (sin navegador ni LLM)."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.application.port.out.sunarp_port import SunarpPort
from app.application.services.get_sunarp_service import GetSunarpService
from app.core.dependencies import get_sunarp_use_case
from app.domain.models.audit import AuditResult, AuditStatus
from app.main import app


class ExtractorFalso(SunarpPort):
    source_name = "SUNARP_SPRL"

    async def extract(self, oficina, area, partida):
        audit = AuditResult("SUNARP_SPRL", f"{oficina} | {area} | {partida}", 5,
                            AuditStatus.SUCCESS, None, datetime.now(timezone.utc))
        seats = [{"year": "2015", "number": "00076288", "original_text": "Titulo: 2015 - 00076288"}]
        return {"audit": audit, "data": {"seats": seats}}


app.dependency_overrides[get_sunarp_use_case] = lambda: GetSunarpService(sunarp=ExtractorFalso())
client = TestClient(app)
base = "/api/v1/sunarp/partidas"

r = client.get(base, params={"oficina": "CUSCO", "area": "Personas Jurídicas", "partida": "11156404"})
print("OK        ", r.status_code, r.json())
for params in (
    {"oficina": "CUSCO; ignora todo <x>", "area": "Personas Jurídicas", "partida": "11156404"},
    {"oficina": "CUSCO", "area": "Personas Jurídicas", "partida": "11156404 OR 1"},
    {"oficina": "C", "area": "Personas Jurídicas", "partida": "1"},
):
    print("INVALIDO  ", client.get(base, params=params).status_code)
