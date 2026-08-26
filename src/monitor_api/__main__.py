"""Punto de entrada del monitor.

    python -m monitor_api          # desde el código fuente
    dft-monitor                    # binario congelado (PyInstaller lo usa)
"""
from .launcher import main

if __name__ == "__main__":
    main()
