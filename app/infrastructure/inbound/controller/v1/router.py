from fastapi import APIRouter

from app.infrastructure.inbound.controller.v1 import (
    company_controller,
    health_controller,
    person_controller,
    sunarp_controller,
)

api_router = APIRouter()
api_router.include_router(health_controller.router, prefix="/health", tags=["Health"])
api_router.include_router(company_controller.router, prefix="/companies", tags=["Companies"])
api_router.include_router(person_controller.router, prefix="/persons", tags=["Persons"])
api_router.include_router(sunarp_controller.router, prefix="/sunarp", tags=["SUNARP"])