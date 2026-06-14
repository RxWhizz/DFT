# Entrenamiento del MLIP en Google Colab (GPU)

El entrenamiento del potencial interatómico (MACE multi-cabeza) corre en **Colab con GPU**
porque en CPU es impráctico (benchmark de esta sesión: los cores no escalan, ~26 h para 50
épocas). Solo el paso de entrenamiento se mueve a la nube; la ingesta de datos y la
evaluación/validación completas siguen siendo locales.

## Arquitectura

```
LOCAL (CPU)                         GOOGLE DRIVE             COLAB (GPU)
build_mlip_training.py ─┐
pack_colab_bundle.py ───┴─► bundle.tar.gz ──► MyDrive/mlip_colab/ ──► notebook: train (cuda, fp32)
                                              output/*.model    ◄────  guarda modelo + logs
fetch_colab_model.py ◄────────────────────── output/*.model
   └─► models/mace_phase2/phase2_mlip_<tag>.model
        └─► eval_mlip.py + validate_mlip.py  (local, fp32)
```

## Pasos

### 1. (Local) Construir el set de entrenamiento — si cambió algún dato
```bash
PYTHONPATH=src .venv/bin/python3 scripts/build_mlip_training.py --valid-frac 0.2
```
Genera `data/mlip_datasets/build/` con los 6 `*.xyz` + `heads.json`.

### 2. (Local) Empaquetar el bundle para Colab
```bash
PYTHONPATH=src .venv/bin/python3 scripts/pack_colab_bundle.py --tag mh_b000 --epochs 50 --batch 16
```
Produce `data/mlip_datasets/colab_mlip_bundle.tar.gz` (~13 MB) con datos + `heads.json`
(rutas relativas) + `run_train.json` (comando exacto, cuda/float32) + holdout de sanidad.

### 3. Subir a Google Drive
Sube `colab_mlip_bundle.tar.gz` a la carpeta **`MyDrive/mlip_colab/`** (créala si no existe).

### 4. (Colab) Entrenar
1. Abre [`notebooks/train_mlip_colab.ipynb`](train_mlip_colab.ipynb) en Colab.
2. `Runtime → Change runtime type → GPU` (T4 basta).
3. Ejecuta todas las celdas. El notebook: confirma GPU, instala `mace-torch==0.3.15`,
   monta Drive, extrae el bundle, **entrena en GPU** (minutos, no horas), imprime un RMSE
   de sanidad y guarda el modelo en `MyDrive/mlip_colab/output/`.

### 5. (Local) Traer el modelo y evaluar
Baja `output/phase2_mlip_mh_b000.model` (y los `.log` si quieres curvas) de Drive, luego:
```bash
# trae el modelo al repo
python scripts/fetch_colab_model.py --from-dir ~/Descargas/output --tag mh_b000
#   (o: --model ~/Descargas/phase2_mlip_mh_b000.model)

# evaluación completa (curvas, parity, generalización, test de fases) y validación física
PYTHONPATH=src .venv/bin/python3 scripts/eval_mlip.py     --tag mh_b000 --dtype float32 --baseline
PYTHONPATH=src .venv/bin/python3 scripts/validate_mlip.py --tag mh_b000 --dtype float32
```
Resultados en `reports/training fase 2/` (PNGs + JSONs).

## Notas

- **Precisión:** se entrena en **float32** (en GPU el float64 del T4 está muy penalizado y
  float32 es el estándar de fine-tuning de MLIP). La eval local también usa `--dtype float32`.
  El modelo se guarda con `--save_cpu`, así carga en CPU local sin GPU.
- **Versión:** Colab y local usan `mace-torch==0.3.15` → el `.model` carga sin problemas.
- **Fuente única del comando:** `run_train.json` lo genera `build_mace_cmd()` de
  `scripts/train_mlip.py` (mismos hiperparámetros que el path local). No hay que editar el
  notebook para cambiar la config: ajusta los flags de `pack_colab_bundle.py` y re-empaqueta.
- **Re-entrenar tras nuevos lotes DFT:** repite pasos 1→5. El split 80/20 es estable por
  `candidate_id`, así que los frames nuevos no contaminan la validación previa.
- **Datos:** solo se suben los `build/*.xyz` (47 MB) + un holdout chico. Los zips grandes de
  `~/Documents/Data` no se suben; la ingesta (`ingest_public_datasets.py`) es local.
