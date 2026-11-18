import asyncio
import sys

from app.infrastructure.outbound.extractors.sunarp.sunarp import SunarpExtractor


async def main() -> None:
    oficina, area, partida = (sys.argv[1:4] + ["CUSCO", "Personas Jurídicas", "11156404"][len(sys.argv[1:4]):])
    res = await SunarpExtractor().extract(oficina, area, partida)
    audit = res["audit"]
    print(audit.status, audit.duration_ms, "ms", audit.details)
    print(res["data"])


asyncio.run(main())
