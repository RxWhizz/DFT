#!/bin/bash
# Reinstala GPAW master y relanza el runner después de un reboot.
# Uso: bash scripts/restart_gpaw_and_runner.sh [slots] [cores_per_slot]
set -e

PROJECT=/home/luis-ochoa/Documents/Vscode/py/dft
PYTHON=$PROJECT/.venv/bin/python3
VENV=$PROJECT/.venv
SLOTS=${1:-4}
CORES=${2:-8}

echo "=== BUHO restart ==="
echo "Slots: $SLOTS  Cores/slot: $CORES"

# 1. Clonar GPAW si falta
if [ ! -f /tmp/gpaw_master/gpaw/__init__.py ]; then
    echo "Clonando GPAW master..."
    git clone --depth=1 https://gitlab.com/gpaw/gpaw.git /tmp/gpaw_master
fi

# 2. siteconfig.py
cat > /tmp/gpaw_master/siteconfig.py << SITEOF
libraries = ['xc']
library_dirs = ['${VENV}/lib']
include_dirs = ['${VENV}/include']
extra_link_args = ['-Wl,-rpath,${VENV}/lib']
compiler = 'mpicc'
mpi = True
SITEOF

# 3. Compilar si falta la .so
if [ ! -f /tmp/gpaw_master/_gpaw.cpython-312-x86_64-linux-gnu.so ]; then
    echo "Compilando _gpaw.so..."
    cd /tmp/gpaw_master
    C_INCLUDE_PATH=${VENV}/include \
    LIBRARY_PATH=${VENV}/lib \
    LD_RUN_PATH=${VENV}/lib \
    $PYTHON setup.py build_ext --inplace 2>&1 | tail -3
    cd $PROJECT
fi

# 4. Verificar GPAW
mpirun -n 2 $PYTHON -c "import gpaw; from gpaw.mpi import world; print(f'rank {world.rank} — GPAW {gpaw.__version__} OK')"

# 5. Resetear jobs running/failed → pending
$PYTHON -c "
import json; from pathlib import Path
relax = Path('$PROJECT/runs/relax_basic')
reset = 0
for d in relax.iterdir():
    if not d.is_dir(): continue
    p = d / 'status.json'
    try:
        s = json.loads(p.read_text())
        if s.get('status') in ('running', 'failed'):
            s['status'] = 'pending'
            for k in ('pid','start_time','mpi_cores','returncode','elapsed_min','finished_at'):
                s.pop(k, None)
            p.write_text(json.dumps(s, indent=2))
            reset += 1
    except: pass
print(f'Jobs reseteados: {reset}')
"

# 6. Lanzar runner
echo "Lanzando runner: $SLOTS slots x $CORES cores..."
PYTHONPATH=$PROJECT/src nohup $PYTHON $PROJECT/scripts/buho_relax_runner.py \
    --slots $SLOTS --cores $CORES --poll 60 \
    --relax-dir $PROJECT/runs/relax_basic \
    --mpirun mpirun \
    >> $PROJECT/runs/relax_basic/runner.log 2>&1 &
echo "Runner PID: $!"
echo ""
echo "Monitor: PYTHONPATH=$PROJECT/src $PYTHON $PROJECT/scripts/buho_monitor.py --relax-dir $PROJECT/runs/relax_basic"
