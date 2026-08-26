# Publicar una release

Dos artefactos por versión y plataforma, con nombres deliberadamente distintos:

| Artefacto | Qué es | Se compila con |
|---|---|---|
| `dft-monitor-desktop-<v>-<plataforma>.tar.gz` | App de escritorio, motor embebido, autónoma | `scripts/build_desktop.sh` |
| `dft-monitor-web-<v>-<plataforma>.tar.gz` | Servidor que se abre en el navegador | `scripts/build_web.sh` |

La versión sale de un único sitio, `src/monitor_api/__init__.py`. El tag debe
coincidir o la CI aborta.

---

## 1. Antes de nada: subir el código

Las releases cuelgan de un tag, y el tag de un commit. Si el trabajo no está en
GitHub, la release apunta a código que nadie puede ver.

**Nunca uses `git add -A`.** Hay borrados pendientes bajo `local_runs/` de datos
de corridas que estaban versionados y hoy viven en el disco externo vía symlink;
un `add -A` los borraría del repositorio de golpe. Añade por ruta.

```bash
git status                 # revisa que no se cuele nada del disco externo
git add <rutas concretas>
git commit -m "…"
git push origin main
```

## 2. Comprobar que la versión cuadra

```bash
grep __version__ src/monitor_api/__init__.py
```

Si vas a publicar `v0.3.0`, ahí debe poner `0.3.0`. Si no, edítalo, comitea y
vuelve a empujar antes de seguir.

## 3. Compilar los dos artefactos

**Primero, redirige la compilación a RAM.** `build/`, `dist/` y el build de
Flutter son symlinks a un disco NTFS montado con el driver `ntfs3` del kernel, y
compilar sobre él cuelga la máquina: una compilación dejó `cmake` en estado D
—espera de E/S ininterrumpible— bloqueado en `vfs_unlink`, con el kworker del
driver atascado 34 minutos. Hizo falta reiniciar. Antes, un `cp` sobre el mismo
árbol había terminado en Segmentation fault.

```bash
bash scripts/build_en_ram.sh     # apunta los tres a /dev/shm
```

**tmpfs se vacía al reiniciar**, así que hay que repetirlo antes de cada sesión
de compilación. `--status` dice dónde apunta cada directorio y `--restore` los
devuelve al disco.

```bash
bash scripts/build_desktop.sh    # ~137 MB
bash scripts/build_web.sh        # ~94 MB
```

Los `.tar.gz` quedan en `dist/`, que ahora vive en RAM. **Cópialos a un sitio
persistente antes de reiniciar** o los pierdes.

Cada script prueba lo que produce antes de comprimir: el de escritorio verifica
el contrato de arranque del motor embebido; el web comprueba salud, SPA,
estructuras y una predicción del surrogate.

## 4. Checksums

```bash
cd dist && sha256sum dft-monitor-*.tar.gz > SHA256SUMS && cd ..
cat dist/SHA256SUMS
```

## 5. Publicar

```bash
gh release create v0.2.0 \
  dist/dft-monitor-desktop-0.2.0-linux-x86_64.tar.gz \
  dist/dft-monitor-web-0.2.0-linux-x86_64.tar.gz \
  dist/SHA256SUMS \
  --title "Monitor DFT 0.2.0" \
  --notes-file docs/notas-release.md
```

Sin `gh`: en GitHub, **Releases → Draft a new release**, tag `v0.2.0`, y arrastra
los tres archivos.

---

## Trampas

**El workflow dispara con tags `v*`.** Si `.github/workflows/release.yml` está en
GitHub, crear el tag arranca Actions, que intentará compilar y publicar por su
cuenta. O dejas que lo haga la CI entera, o no comiteas el workflow y publicas a
mano — pero no las dos cosas, o acabarás con artefactos duplicados en la misma
release.

**Los binarios no van al repositorio.** `.git` ya pesa ~157 MB; 137 MB por
versión lo duplicarían y no hay vuelta atrás. Los assets de release viven fuera
del historial: se descargan igual y clonar no los arrastra.

**ASE es LGPL-2.1-or-later y viaja dentro del binario.** Su redistribución exige
incluir el aviso de licencia. El resto de dependencias empaquetadas
(scikit-learn, numpy, scipy, pandas, FastAPI, uvicorn, psutil) es BSD/MIT y no
impone nada.

**Sin `LICENSE` en el repositorio, nadie puede usar legalmente lo que publiques.**
Repo público sin licencia significa todos los derechos reservados.
