import asyncio
import os
import shutil
import tempfile
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def sesion_linkedin(headless: bool, user_data_dir: str):
    """Sesión de @playwright/mcp cuyos snapshots y descargas se borran al terminar.

    Solo perdura el perfil de Chrome (`user_data_dir`), que conserva la sesión de LinkedIn.
    """
    os.makedirs(user_data_dir, exist_ok=True)
    os.makedirs(".cache", exist_ok=True)
    npx = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    with tempfile.TemporaryDirectory(prefix="linkedin_mcp_", ignore_cleanup_errors=True) as salida:
        args = [
            "-y", "@playwright/mcp@latest", "--browser", "chrome",
            "--user-data-dir", user_data_dir, "--output-dir", salida,
        ]
        if headless:
            args.append("--headless")
        # En Jupyter sys.stderr no tiene fileno(): el stderr del servidor MCP va a un archivo real.
        with open(os.path.join(".cache", "mcp_stderr.log"), "a", encoding="utf-8") as errlog:
            async with stdio_client(
                StdioServerParameters(command=npx, args=args), errlog=errlog
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    try:
                        yield session
                    finally:
                        # Cierre ordenado: sin él Chrome puede no llegar a guardar las cookies.
                        try:
                            await asyncio.wait_for(session.call_tool("browser_close", {}), 15)
                        except Exception:
                            pass
