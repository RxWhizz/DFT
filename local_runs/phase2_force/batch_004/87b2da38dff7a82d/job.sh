#!/bin/bash
# Un mpiexec POR config (aislamiento de procesos MPI; ver input.py).
# El runner exporta GPAW_SETUP_PATH y NCORES; conda env ya activo.
set -u
cd "$(dirname "$0")"
for k in 0 1 2 3; do
    mpiexec -n "${NCORES:-8}" python input.py --config-index "$k"
done
exec python input.py --finalize
