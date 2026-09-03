# Monitor DFT Flutter

Flutter desktop rewrite for the DFT monitor UI.

This app is desktop-first: it starts the existing Python/FastAPI monitor as a
local embedded engine, discovers its ephemeral localhost port from a JSON ready
line, and talks to it through the same API used by the current React SPA.

Current status:

- Source scaffold plus Linux/Windows platform folders are present.
- `flutter analyze` and `flutter test` pass with Flutter 3.47.1 / Dart 3.13.1.
- Linux debug and release Flutter builds pass with the native desktop toolchain.
- OpenAPI `dart-dio` client generation passes with Java 17, including
  `build_runner`, `dart analyze`, and generated package tests.
- Diagnostics lets the user select a data root, select an engine binary,
  restart/stop the engine, and open the external log directory.
- Live/jobs/screening providers refresh automatically while views are mounted.

Useful commands:

```bash
cd apps/dft_monitor_flutter
flutter pub get
flutter analyze
flutter test
flutter run -d linux
```

For development from this repository, set the engine explicitly if needed:

```bash
export DFT_MONITOR_ENGINE=/home/luis-ochoa/DFT/bin/dft-monitor-web
flutter run -d linux
```

To generate the OpenAPI client after installing Java 11+:

```bash
scripts/generate_flutter_api.sh
```

Current Linux app bundle:

```bash
apps/dft_monitor_flutter/build/linux/x64/release/bundle/dft_monitor_flutter
```

Local launch helper:

```bash
scripts/run_flutter_app.sh
```

## Compilar en Windows

`.dart_tool/` y `build/` están versionados como **symlinks de Linux**. Git para
Windows con `core.symlinks=false` los materializa como ficheros de texto con la
ruta dentro, así que ni `flutter pub get` ni el analizador funcionan hasta
reemplazarlos por *junctions* que apunten al volumen de trabajo:

```powershell
$app  = "<repo>\apps\dft_monitor_flutter"
$work = "C:\NuevoVol\dft-monitor-flutter-work"
Remove-Item "$app\.dart_tool","$app\build" -Force
New-Item -ItemType Junction -Path "$app\.dart_tool" -Target "$work\dart_tool_app"
New-Item -ItemType Junction -Path "$app\build"      -Target "$work\build"
git update-index --skip-worktree apps/dft_monitor_flutter/.dart_tool apps/dft_monitor_flutter/build
```

Ese último comando **no es opcional**: sin él git ve las junctions como
borrados (`D`) y un `git add -A` elimina los symlinks del repositorio, con lo
que se rompe la compilación en Linux. `--skip-worktree` los oculta del índice
sin tocar lo que está commiteado. Para revertirlo: `--no-skip-worktree`.

Además hay dos SDK de Flutter en esta máquina: `C:\NuevoVol\flutter` es el de
**Linux** (no trae `dart.exe`, y cada invocación reintenta diez veces antes de
fallar, lo que parece lentitud); el de Windows es `C:\NuevoVol\flutter-windows`.

On this workstation, heavy working directories are symlinked into:

```bash
/media/luis-ochoa/Nuevo vol/DFT-work
/media/luis-ochoa/Nuevo vol/dft-monitor-desktop-work
```

The runtime config used by the desktop app is:

```bash
/media/luis-ochoa/Nuevo vol/DFT-work/runtime/config/monitor.yaml
```
