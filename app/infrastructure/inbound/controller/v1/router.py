from fastapi import APIRouter

from app.infrastructure.inbound.controller.v1 import (
    company_controller,
    facebook_controller,
    health_controller,
    instagram_controller,
    news_controller,
    person_controller,
    sunarp_controller,
)

api_router = APIRouter()
api_router.include_router(health_controller.router, prefix="/health", tags=["Health"])
api_router.include_router(company_controller.router, prefix="/companies", tags=["Companies"])
api_router.include_router(person_controller.router, prefix="/persons", tags=["Persons"])
api_router.include_router(sunarp_controller.router, prefix="/sunarp", tags=["SUNARP"])
api_router.include_router(instagram_controller.router, prefix="/instagram", tags=["Instagram"])
api_router.include_router(facebook_controller.router, prefix="/facebook", tags=["Facebook"])
api_router.include_router(news_controller.router, prefix="/news", tags=["News"])
