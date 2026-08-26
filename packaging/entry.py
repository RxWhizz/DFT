"""Punto de entrada del binario congelado.

PyInstaller ejecuta su script de arranque como `__main__` de nivel superior, sin
contexto de paquete: un `from .launcher import main` falla ahí con
«attempted relative import with no known parent package». Por eso el entry point
del empaquetado es este archivo, con import absoluto, y `monitor_api/__main__.py`
se queda idiomático para `python -m monitor_api`.
"""
from monitor_api.launcher import main

if __name__ == "__main__":
    main()
