import 'activity_banner.dart';
import '../api/errors.dart';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../engine/engine_supervisor.dart';
import '../models/activity.dart';
import '../models/models.dart';
import '../repositories/repositories.dart';

class AppShell extends ConsumerWidget {
  const AppShell({required this.location, required this.child, super.key});

  final String location;
  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final engine = ref.watch(engineSupervisorProvider);
    final auth = ref.watch(authStateProvider);
    final activity =
        engine.isReady ? ref.watch(activityProvider).valueOrNull : null;

    return Scaffold(
      body: Row(
        children: [
          // El rail va dentro de un scroll: con once destinos ya no cabe en los
          // 720 px de alto que trae la ventana por defecto, y NavigationRail no
          // desplaza por su cuenta — recortaba los últimos y los dejaba
          // inalcanzables salvo maximizando. El ConstrainedBox + IntrinsicHeight
          // mantiene el rail a la altura completa cuando sí cabe, para que el
          // fondo no se corte a media pantalla.
          LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: IntrinsicHeight(
                  child: NavigationRail(
                    selectedIndex: _indexFor(location),
                    labelType: NavigationRailLabelType.all,
                    minWidth: 88,
                    onDestinationSelected: (index) =>
                        context.go(_pathFor(index)),
                    destinations: const [
                      NavigationRailDestination(
                        icon: Icon(Icons.monitor_heart_outlined),
                        label: Text('En vivo'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.list_alt_outlined),
                        label: Text('Trabajos'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.filter_alt_outlined),
                        label: Text('Cribado'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.auto_awesome_motion_outlined),
                        label: Text('Protocolo'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.hub_outlined),
                        label: Text('Candidatos'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.psychology_alt_outlined),
                        label: Text('Predictor'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.inventory_2_outlined),
                        label: Text('Lotes'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.view_in_ar_outlined),
                        label: Text('Estructuras'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.article_outlined),
                        label: Text('Resultados'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.terminal_outlined),
                        label: Text('Diagnóstico'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.build_outlined),
                        label: Text('Entorno'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const VerticalDivider(width: 1),
          Expanded(
            child: Column(
              children: [
                _TopBar(
                  engine: engine,
                  auth: auth.asData?.value,
                  activity: activity,
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: auth.when(
                      skipLoadingOnReload: true,
                      data: (state) => state.authEnabled && !state.authenticated
                          ? const _LoginPanel()
                          // La franja de actividad va aquí, no en una vista
                          // concreta: saber si el sistema está trabajando no
                          // debería depender de en qué pestaña estés.
                          : Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                const ActivityBanner(),
                                Expanded(child: child),
                              ],
                            ),
                      loading: () =>
                          const Center(child: CircularProgressIndicator()),
                      error: (error, _) =>
                          Center(child: Text(mensajeDeError(error))),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.engine,
    required this.auth,
    required this.activity,
  });

  final EngineState engine;
  final AuthState? auth;
  final Activity? activity;

  @override
  Widget build(BuildContext context) {
    final active = activity != null && activity!.activity != 'idle';
    final color = active
        ? _activityColor(context, activity!)
        : switch (engine.status) {
            EngineStatus.ready => Colors.greenAccent,
            EngineStatus.starting => Colors.amberAccent,
            EngineStatus.error => Colors.redAccent,
            EngineStatus.stopped => Colors.grey,
          };
    final label = active
        ? activity!.label
        : switch (engine.status) {
            EngineStatus.ready => 'motor local listo',
            EngineStatus.starting => 'arrancando motor',
            EngineStatus.error => 'motor con error',
            EngineStatus.stopped => 'motor detenido',
          };
    final detail = active ? activity!.detail : engine.ready?.dataRoot;

    return Container(
      height: 48,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: const BoxDecoration(
        color: Color(0xff111827),
        border: Border(bottom: BorderSide(color: Color(0xff1f2937))),
      ),
      child: Row(
        children: [
          const Text(
            'Monitor DFT',
            style: TextStyle(fontWeight: FontWeight.w700),
          ),
          const SizedBox(width: 12),
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          if (detail != null && detail.isNotEmpty) ...[
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                detail,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.end,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ] else
            const Spacer(),
          if (auth?.authEnabled == true && auth?.authenticated == true) ...[
            const SizedBox(width: 12),
            const _LogoutButton(),
          ],
        ],
      ),
    );
  }
}

Color _activityColor(BuildContext context, Activity activity) {
  final scheme = Theme.of(context).colorScheme;
  return switch (activity.activity) {
    'discovery' => Colors.lightBlueAccent,
    'dft' => scheme.primary,
    'queued' => scheme.tertiary,
    'generating' => scheme.tertiary,
    'benchmark' => Colors.amberAccent,
    _ => scheme.onSurfaceVariant,
  };
}

class _LoginPanel extends ConsumerStatefulWidget {
  const _LoginPanel();

  @override
  ConsumerState<_LoginPanel> createState() => _LoginPanelState();
}

class _LoginPanelState extends ConsumerState<_LoginPanel> {
  final _controller = TextEditingController();
  String? _error;
  bool _loading = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SizedBox(
        width: 380,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Monitor DFT',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _controller,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: 'Token'),
                  onSubmitted: (_) => _login(),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 10),
                  Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ],
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: _loading ? null : _login,
                    child: Text(_loading ? 'Comprobando...' : 'Entrar'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _login() async {
    final token = _controller.text.trim();
    if (token.isEmpty) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ref.read(authActionsProvider).login(token);
      ref.invalidate(authStateProvider);
      ref.invalidate(healthProvider);
    } catch (error) {
      setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }
}

class _LogoutButton extends ConsumerWidget {
  const _LogoutButton();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return TextButton(
      onPressed: () async {
        await ref.read(authActionsProvider).logout();
        ref.invalidate(authStateProvider);
      },
      child: const Text('Salir'),
    );
  }
}

int _indexFor(String location) {
  // El agente queda fuera hasta una version futura: los indices se corren.
  if (location.startsWith('/jobs')) return 1;
  if (location.startsWith('/screening')) return 2;
  if (location.startsWith('/protocolo-descubrimiento-autonomo') ||
      location.startsWith('/discovery')) {
    return 3;
  }
  if (location.startsWith('/candidates')) return 4;
  if (location.startsWith('/ml')) return 5;
  if (location.startsWith('/batches')) return 6;
  if (location.startsWith('/structures')) return 7;
  if (location.startsWith('/results')) return 8;
  if (location.startsWith('/diagnostics')) return 9;
  if (location.startsWith('/entorno')) return 10;
  return 0;
}

String _pathFor(int index) {
  return switch (index) {
    1 => '/jobs',
    2 => '/screening',
    3 => '/protocolo-descubrimiento-autonomo',
    4 => '/candidates',
    5 => '/ml',
    6 => '/batches',
    7 => '/structures',
    8 => '/results',
    9 => '/diagnostics',
    10 => '/entorno',
    _ => '/',
  };
}
