import 'package:go_router/go_router.dart';

import '../views/agent_view.dart';
import '../views/batches_view.dart';
import '../views/candidates_view.dart';
import '../views/dashboard_view.dart';
import '../views/diagnostics_view.dart';
import '../views/jobs_view.dart';
import '../views/ml_view.dart';
import '../views/results_view.dart';
import '../views/screening_view.dart';
import '../views/structures_view.dart';
import '../widgets/app_shell.dart';

final appRouter = GoRouter(
  initialLocation: '/',
  routes: [
    ShellRoute(
      builder: (context, state, child) =>
          AppShell(location: state.uri.path, child: child),
      routes: [
        GoRoute(path: '/', builder: (context, state) => const DashboardView()),
        GoRoute(path: '/agent', builder: (context, state) => const AgentView()),
        GoRoute(path: '/jobs', builder: (context, state) => const JobsView()),
        GoRoute(
            path: '/batches', builder: (context, state) => const BatchesView()),
        GoRoute(
            path: '/candidates',
            builder: (context, state) => const CandidatesView()),
        GoRoute(path: '/ml', builder: (context, state) => const MlView()),
        GoRoute(
            path: '/structures',
            builder: (context, state) => const StructuresView()),
        GoRoute(
            path: '/screening',
            builder: (context, state) => const ScreeningView()),
        GoRoute(
            path: '/results', builder: (context, state) => const ResultsView()),
        GoRoute(
            path: '/diagnostics',
            builder: (context, state) => const DiagnosticsView()),
      ],
    ),
  ],
);
