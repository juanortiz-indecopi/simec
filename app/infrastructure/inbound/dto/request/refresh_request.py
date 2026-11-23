from typing import Annotated

from fastapi import Query

RefreshQuery = Annotated[
    bool,
    Query(
        description=(
            "`false` (por defecto): responde con los datos guardados en la base de datos y solo "
            "consulta en la web las fuentes que aún no tienen datos. `true`: vuelve a consultar "
            "todas las fuentes en la web y guarda el resultado; si una fuente falla, se conservan "
            "y se muestran sus datos guardados."
        ),
    ),
]
