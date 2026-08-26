"""Lectura de artefactos en disco para los endpoints del monitor.

Se separa de los routers para que `router.py` no siga creciendo y para poder
testear el acceso al sistema de archivos sin levantar la app.
"""
