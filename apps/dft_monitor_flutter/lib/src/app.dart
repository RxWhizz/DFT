import 'package:flutter/material.dart';

import 'router/app_router.dart';
import 'theme/app_theme.dart';

class DftMonitorApp extends StatelessWidget {
  const DftMonitorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Monitor DFT',
      debugShowCheckedModeBanner: false,
      theme: buildDarkTheme(),
      routerConfig: appRouter,
    );
  }
}
