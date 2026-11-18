"""Infraestructura común del agente: sesión de @playwright/mcp, modelo LLM y bucle LangGraph.

Configuración por entorno (.env):
  LLM_MODEL         p.ej. "gpt-4o-mini" (por defecto). Debe soportar visión (lee el captcha).
  LLM_PROVIDER      "openai" (por defecto), "google_genai", "anthropic"...
  LLM_API_KEY       clave del proveedor
  LLM_BASE_URL      opcional, endpoints compatibles con OpenAI (DeepSeek, Groq, Ollama...)
"""
import os
import shutil
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()


@dataclass
class AgentResult:
    ok: bool
    final_message: str
    steps: int
    trace: list[str] = field(default_factory=list)


@asynccontextmanager
async def sesion_playwright_mcp(headless: bool, user_data_dir: str | None):
    """Una única sesión MCP: el navegador permanece abierto durante todo el agente."""
    args = ["-y", "@playwright/mcp@latest", "--browser", "chrome"]
    if headless:
        args.append("--headless")
    if user_data_dir:
        args += ["--user-data-dir", user_data_dir]
    npx = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    # En Jupyter sys.stderr no tiene fileno(): el stderr del servidor MCP va a un archivo real.
    os.makedirs(".cache", exist_ok=True)
    with open(os.path.join(".cache", "mcp_stderr.log"), "a", encoding="utf-8") as errlog:
        async with stdio_client(
            StdioServerParameters(command=npx, args=args), errlog=errlog
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def crear_modelo() -> BaseChatModel:
    kwargs = {}
    if os.getenv("LLM_API_KEY"):
        kwargs["api_key"] = os.environ["LLM_API_KEY"]
    if os.getenv("LLM_BASE_URL"):
        kwargs["base_url"] = os.environ["LLM_BASE_URL"]
    # Algunos modelos (p.ej. Claude recientes) rechazan `temperature`: solo se envía si se define.
    if os.getenv("LLM_TEMPERATURE"):
        kwargs["temperature"] = float(os.environ["LLM_TEMPERATURE"])
    proveedor = os.getenv("LLM_PROVIDER", "openai")
    if proveedor == "anthropic":
        # Los bloques `thinking` van firmados contra todo el historial: al recortar snapshots
        # antiguos la firma deja de coincidir (400). Navegar no requiere razonamiento extendido.
        kwargs["thinking"] = {"type": "disabled"}
    return init_chat_model(
        os.getenv("LLM_MODEL", "gpt-4o-mini"),
        model_provider=proveedor,
        **kwargs,
    )


def texto_de_mensaje(mensaje) -> str:
    contenido = mensaje.content
    if isinstance(contenido, str):
        return contenido
    return " ".join(b.get("text", "") for b in contenido if isinstance(b, dict))


class RecortarResultadosAntiguos(AgentMiddleware):
    """Los snapshots de página son grandes: solo se envían completos los últimos resultados."""

    def __init__(self, conservar: int = 3, umbral: int = 1500) -> None:
        self.conservar = conservar
        self.umbral = umbral

    async def awrap_model_call(self, request, handler):
        mensajes = list(request.messages)
        indices = [i for i, m in enumerate(mensajes) if m.type == "tool"]
        for i in indices[: -self.conservar]:
            if len(texto_de_mensaje(mensajes[i])) > self.umbral:
                mensajes[i] = mensajes[i].model_copy(update={"content": "[resultado anterior omitido]"})
        return await handler(request.override(messages=mensajes))


async def correr_agente(
    tools: list[BaseTool],
    system_prompt: str,
    tarea: str,
    *,
    max_pasos: int,
    log: Callable[[str], None],
) -> AgentResult:
    agent = create_agent(
        crear_modelo(), tools, system_prompt=system_prompt, middleware=[RecortarResultadosAntiguos()]
    )
    trace: list[str] = []
    pasos, final = 0, ""
    async for estado in agent.astream(
        {"messages": [("user", tarea)]},
        config={"recursion_limit": max_pasos * 2 + 1},
        stream_mode="values",
    ):
        ultimo = estado["messages"][-1]
        if ultimo.type == "tool":
            resumen = " ".join(texto_de_mensaje(ultimo).split())[:160]
            trace.append(f"      -> {resumen}")
            log(trace[-1])
            continue
        if ultimo.type != "ai":
            continue
        pasos += 1
        llamadas = getattr(ultimo, "tool_calls", None) or []
        for call in llamadas:
            linea = f"[paso {pasos}] {call['name']}({str(call['args'])[:150]})"
            trace.append(linea)
            log(linea)
        if not llamadas:
            final = texto_de_mensaje(ultimo)
            trace.append(f"[paso {pasos}] FIN: {final}")
            log(trace[-1])
    return AgentResult(bool(final), final, pasos, trace)
