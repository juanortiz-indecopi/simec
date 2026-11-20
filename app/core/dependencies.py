from functools import lru_cache

from app.application.port.usecase.get_company_use_case import GetCompanyUseCase
from app.application.port.usecase.get_person_use_case import GetPersonUseCase
from app.application.port.usecase.get_sunarp_use_case import GetSunarpUseCase
from app.application.services.get_company_service import GetCompanyService
from app.application.services.get_person_service import GetPersonService
from app.application.services.get_sunarp_service import GetSunarpService 
from app.infrastructure.outbound.extractors.profile.dni_adapter import ApisNetPeDniAdapter
from app.infrastructure.outbound.extractors.profile.ruc_adapter import ApisNetPeRucAdapter
from app.infrastructure.outbound.extractors.rnp.ruc_adapter import RnpRucAdapter
from app.infrastructure.outbound.extractors.seace.dni_adapter import SeaceDniAdapter
from app.infrastructure.outbound.extractors.seace.ruc_adapter import SeaceRucAdapter
from app.infrastructure.outbound.extractors.sunat.dni_adapter import SunatDniAdapter
from app.infrastructure.outbound.extractors.sunat.ruc_adapter import SunatRucAdapter
from app.infrastructure.outbound.extractors.sunarp.agent_extractor import SunarpAgentExtractor


@lru_cache
def get_company_use_case() -> GetCompanyUseCase:
    return GetCompanyService(
        profile=ApisNetPeRucAdapter(),
        seace=SeaceRucAdapter(),
        sunat=SunatRucAdapter(),
        rnp=RnpRucAdapter(),
    )


@lru_cache
def get_person_use_case() -> GetPersonUseCase:
    return GetPersonService(
        profile=ApisNetPeDniAdapter(),
        seace=SeaceDniAdapter(),
        sunat=SunatDniAdapter(),
    )


@lru_cache
def get_sunarp_use_case() -> GetSunarpUseCase:
    # El agente LLM+MCP tarda más que un extractor HTTP: timeout propio de 10 minutos
    # (con Gemini cada paso es más lento que con Claude).
    return GetSunarpService(
        sunarp=SunarpAgentExtractor(),
        timeout_s=600.0,
    )