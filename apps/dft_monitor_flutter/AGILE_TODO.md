# Agile To-Do: Flutter Desktop Rewrite

## Done in scaffold
- EPIC 1: Flutter source tree, Material 3 dark shell, navigation rail, base dependencies.
- EPIC 2: Python launcher contract `--engine --port 0 --print-ready-json`; Flutter `EngineSupervisor`.
- EPIC 3: Repository layer for health, jobs, batches, structures, screening, and WebSocket stream.
- EPIC 4: Initial Live dashboard and Jobs/detail/log/traces/metadata UI.
- EPIC 5: CIF parser and native `CustomPainter` structure viewer.
- EPIC 6: Screening controls, funnel, gates, ranking, and DFT start confirmation.
- EPIC 7: Host build script and PyInstaller engine spec.
- Linux/Windows platform folders generated with `flutter create`.
- Flutter analyzer and CIF parser tests pass.
- OpenAPI `dart-dio` client generated under `packages/monitor_api_client`.
- Generated client `build_runner`, analyzer, and tests pass.
- Linux Flutter debug/release builds pass.
- Engine source smoke test passes on an ephemeral local port.
- Local app launch helper starts the release bundle and embedded engine.
- Heavy repo/app work dirs are symlinked to `/media/luis-ochoa/Nuevo vol`.
- Persistent desktop settings for data root and engine path.
- Diagnostics controls for data root, engine path, restart/stop, and logs.
- Timed refresh for Live, Jobs, job details, logs, and Screening.

## Next sprint
- Replace manual repository DTOs with the generated `dart-dio` client where practical.
- Move/parameterize PyInstaller packaging work dirs before full portable packaging.
- Add a first-run setup dialog for portable bundles.
- Add WebSocket-driven invalidation to reduce polling once event coverage is complete.

## Acceptance backlog
- Linux portable bundle opens without browser and starts embedded engine.
- Windows portable zip opens without Python/Node installed.
- Two app instances run simultaneously with different engine ports.
- Closing the window stops the engine process.
- Estructuras opens current jobs, selected recent structures, top8, and reference phases.
- Cribado runs with seed/lotes/candidatos, shows ranking, and prepares DFT with confirmation.
