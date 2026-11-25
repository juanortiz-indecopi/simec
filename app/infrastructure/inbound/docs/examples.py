from typing import Any, Final

AUDIT_EXAMPLE: Final[dict[str, Any]] = {
    "source_name": "SEACE_PENTAHO_CDA_RUC",
    "query_parameter": "20607524476",
    "duration_ms": 779,
    "status": "SUCCESS",
    "details": None,
    "executed_at_utc": "2026-11-10T14:49:46.322370Z",
    "from_cache": False,
    "data_fetched_at": "2026-11-10T14:49:46.322370Z",
    "is_stale": False,
}

# Fuente servida desde la base de datos (consulta previa): no se consultó en esta petición.
CACHED_AUDIT_EXAMPLE: Final[dict[str, Any]] = {
    "source_name": "SUNAT_SCRAPER_RUC",
    "query_parameter": "20607524476",
    "duration_ms": 0,
    "status": "SUCCESS",
    "details": "Servido desde la base de datos; obtenido de la fuente el 2026-11-10 14:49 UTC.",
    "executed_at_utc": "2026-11-10T14:49:46.322370Z",
    "from_cache": True,
    "data_fetched_at": "2026-11-10T14:49:46.322370Z",
    "is_stale": False,
}

SUNAT_EXAMPLE: Final[dict[str, Any]] = {
    "tax_id": "20607524476",
    "taxpayer_type": "EMPRESA INDIVIDUAL DE RESP. LTDA",
    "commercial_name": "INVERSIONES HUAYNA DEL PERU",
    "registration_date": "2021-02-24",
    "activity_start_date": "2021-03-15",
    "status": "BAJA DE OFICIO",
    "condition": "HABIDO",
    "tax_alert": None,
    "fiscal_address": "CAL.VILLA LA RINCONADA LOTE. H-1 APV. VILLA LA RINCONADA CUSCO - CUSCO - SAN JERONIMO",
    "economic_activities": ["Principal - 4630 - VENTA AL POR MAYOR DE ALIMENTOS, BEBIDAS Y TABACO"],
    "electronic_issuance": "FACTURA PORTAL DESDE 27/05/2021",
    "legal_representatives": [
        {
            "document_type": "DNI",
            "document_number": "44900952",
            "full_name": "RUIZ AUCCAPIÑA RONALD",
            "role": "TITULAR-GERENTE",
            "start_date": "2021-02-08",
        }
    ],
    "branch_offices": [
        {
            "code": "0004",
            "establishment_type": "LO. L. COMERCIAL",
            "address": "LOTE. 105 GRU. MERCADO MAYORISTA FERIAL DE PRODUCTORES OTR. STAND 105 CUSCO - CUSCO - SAN JERONIMO",
            "economic_activity": "4630",
        }
    ],
}

SEACE_RECORD_EXAMPLE: Final[dict[str, Any]] = {
    "ruc": "20607524476",
    "validities": [
        {
            "chapter": "Proveedor de Bienes",
            "status": "ACTIVE",
            "start_date": "2021-03-25",
            "end_date": None,
            "department": "CUSCO",
        }
    ],
    "shareholders": [
        {
            "relationship_type": "ACCIONISTA",
            "document_number": "44900952",
            "full_name": "RUIZ AUCCAPIÑA RONALD",
            "share_percentage": 100.0,
        }
    ],
    "awards": [
        {
            "fiscal_year": 2023,
            "modality": None,
            "contracting_entity": "MUNICIPALIDAD PROVINCIAL DE CALCA",
            "amount": 322592.71,
            "processes_count": 10,
        }
    ],
}

COMPANY_EXAMPLE: Final[dict[str, Any]] = {
    "ruc": "20607524476",
    "served_from": "MIXED",
    "profile": {
        "document_number": "20607524476",
        "legal_name": "INVERSIONES Y SERVICIOS HUAYNA DEL PERU EMPRESA INDIVIDUAL DE RESPONSABILIDAD LIMITADA",
        "status": "BAJA DE OFICIO",
        "condition": "HABIDO",
        "address": "CAL. VILLA LA RINCONADA LOTE H-1 APV. VILLA LA RINCONADA",
        "ubigeo": "080104",
        "department": "CUSCO",
        "province": "CUSCO",
        "district": "SAN JERONIMO",
        "via_type": "CAL.",
        "via_name": "VILLA LA RINCONADA",
        "zone_type": "VILLA LA RINCONADA",
        "zone_code": "APV.",
        "number": None,
        "lot": "H-1",
        "apartment": None,
        "block": None,
        "kilometer": None,
    },
    "seace": SEACE_RECORD_EXAMPLE,
    "sunat": SUNAT_EXAMPLE,
    "rnp": {
        "ruc": "20607524476",
        "business_name": "INVERSIONES Y SERVICIOS HUAYNA DEL PERU EMPRESA INDIVIDUAL DE RESPONSABILIDAD LIMITADA",
        "registrations": [
            {
                "chapter": "BIENES",
                "provider_code": None,
                "payment_date": "2021-03-18",
                "procedure_number": "2021-18895585",
                "status": "APROBACION AUTOMATICA",
                "reason": "REQUISITOS CONFORME",
            }
        ],
    },
    "audit_entries": [AUDIT_EXAMPLE, CACHED_AUDIT_EXAMPLE],
}

def _sunarp_seat_example(year: str, number: str, size_bytes: int) -> dict[str, Any]:
    file_name = f"titulo_{year}-{number}_partida_11156404.pdf"
    return {
        "year": year,
        "number": number,
        "original_text": f"Titulo: {year} - {number}",
        "documents": [
            {
                "partida": "11156404",
                "url": f"http://localhost:8000/files/sunarp/CUSCO_11156404/{file_name}",
                "file_path": f"files/sunarp/CUSCO_11156404/{file_name}",
                "size_bytes": size_bytes,
            }
        ],
        "document_status": "DOWNLOADED",
        "document_detail": (
            f"SIGUELO_OK: Se descargó correctamente el asiento de inscripción para el título "
            f"{number} del año {year} en la oficina registral de CUSCO (partida 11156404)."
        ),
    }


SUNARP_EXAMPLE: Final[dict[str, Any]] = {
    "oficina": "CUSCO",
    "area": "Personas Juridicas",
    "partida": "11156404",
    "served_from": "LIVE",
    "record": {
        "partida": "11156404",
        "seats": [
            _sunarp_seat_example("2015", "00076288", 346200),
            _sunarp_seat_example("2015", "00017762", 1847790),
            _sunarp_seat_example("2014", "00077954", 1634127),
        ],
    },
    "audit_entries": [
        {
            "source_name": "SUNARP_SPRL",
            "query_parameter": "CUSCO | Personas Juridicas | 11156404",
            "duration_ms": 817321,
            "status": "SUCCESS",
            "details": None,
            "executed_at_utc": "2026-11-20T04:46:43.611683Z",
            "from_cache": False,
            "data_fetched_at": "2026-11-20T04:46:43.611683Z",
            "is_stale": False,
        },
        {
            "source_name": "SUNARP_SIGUELO",
            "query_parameter": "CUSCO | 11156404 | 3 títulos",
            "duration_ms": 677327,
            "status": "SUCCESS",
            "details": "3/3 títulos con PDF (3 archivos).",
            "executed_at_utc": "2026-11-20T04:46:43.242967Z",
            "from_cache": False,
            "data_fetched_at": "2026-11-20T04:46:43.242967Z",
            "is_stale": False,
        },
    ],
}

FACEBOOK_EXAMPLE: Final[dict[str, Any]] = {
    "requested_page": "codideep",
    "served_from": "LIVE",
    "page": {
        "key": "codideep",
        "page_url": "https://www.facebook.com/codideep",
        "account_id": "100063518592455",
        "page_id": "1727888410822955",
        "name": "CODIDEEP EIRL",
        "category": "Empresa de software",
        "description": "Nos especializamos en soluciones de software empresarial",
        "city": "Abancay",
        "address": "Abancay - Apurímac - Perú, Abancay, Peru",
        "is_verified": False,
        "followers": 1164,
        "phones": [],
        "emails": ["contact@codideep.com"],
        "links": [{"url": "https://eirl.codideep.com/", "platform": "WEB"}],
        "created_on": "2016-04-27",
        "has_active_ads": False,
    },
    "verification": {
        "ruc": "20603687478",
        "result": "PROBABLE",
        "reasons": ["Coincide la forma societaria (EIRL)", "Coincide el nombre distintivo"],
        "warnings": [],
    },
    "audit_entries": [
        {**AUDIT_EXAMPLE, "source_name": "FACEBOOK_PAGE", "query_parameter": "codideep"}
    ],
}

INSTAGRAM_EXAMPLE: Final[dict[str, Any]] = {
    "username": "nasa",
    "served_from": "LIVE",
    "profile": {
        "username": "nasa",
        "full_name": "NASA",
        "biography": "Making the seemingly impossible, possible. ✨",
        "is_private": False,
        "profile_url": "https://www.instagram.com/nasa/",
        "photo_url": "http://localhost:8000/files/instagram/nasa_0123456789ab.jpg",
        "photo_path": "files/instagram/nasa_0123456789ab.jpg",
        "account_id": "528817151",
        "is_verified": True,
        "followers": 104241480,
        "following": 91,
        "posts_count": 5024,
        "links": [{"url": "https://www.nasa.gov", "platform": "WEB", "title": "NASA.gov Homepage"}],
        "mentions": [],
        "threads_username": "nasa",
        "latest_post": {
            "url": "https://www.instagram.com/p/DgIPu3wl3OR/",
            "media_type": "PHOTO",
            "published_on": "2026-11-24",
            "caption": "Texto de la publicación",
        },
        "latest_photo": {
            "url": "https://www.instagram.com/p/DgIPu3wl3OR/",
            "media_type": "PHOTO",
            "published_on": "2026-11-24",
            "caption": "Texto de la publicación",
        },
    },
    "audit_entries": [
        {**AUDIT_EXAMPLE, "source_name": "INSTAGRAM_PROFILE", "query_parameter": "nasa"}
    ],
}

PERSON_EXAMPLE: Final[dict[str, Any]] = {
    "dni": "44900952",
    "served_from": "LIVE",
    "profile": {
        "document_number": "44900952",
        "full_name": "RONALD RUIZ AUCCAPIÑA",
        "given_names": "RONALD",
        "first_surname": "RUIZ",
        "second_surname": "AUCCAPIÑA",
        "check_digit": None,
    },
    "seace": {
        "document_number": "44900952",
        "linked_providers": [
            {
                "presence": {
                    "ruc": "20607524476",
                    "business_name": "INVERSIONES Y SERVICIOS HUAYNA DEL PERU EMPRESA INDIVIDUAL DE RESPONSABILIDAD LIMITADA",
                    "condition": "VIGENTE",
                },
                "record": SEACE_RECORD_EXAMPLE,
            }
        ],
    },
    "sunat": {**SUNAT_EXAMPLE, "tax_id": "10449009521", "taxpayer_type": "PERSONA NATURAL SIN NEGOCIO"},
    "audit_entries": [
        {**AUDIT_EXAMPLE, "source_name": "SEACE_PENTAHO_CDA_DNI", "query_parameter": "44900952"}
    ],
}
