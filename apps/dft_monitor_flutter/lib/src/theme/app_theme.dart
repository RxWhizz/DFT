import 'package:flutter/material.dart';

ThemeData buildDarkTheme() {
  const seed = Color(0xff3b82f6);
  final scheme = ColorScheme.fromSeed(
    seedColor: seed,
    brightness: Brightness.dark,
    surface: const Color(0xff111827),
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: const Color(0xff0a0d12),
    cardTheme: CardThemeData(
      color: const Color(0xff111827),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: const BorderSide(color: Color(0xff1f2937)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: const Color(0xff0b1220),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(6)),
      isDense: true,
    ),
    navigationRailTheme: const NavigationRailThemeData(
      backgroundColor: Color(0xff111827),
      selectedIconTheme: IconThemeData(color: seed),
      selectedLabelTextStyle: TextStyle(color: Colors.white),
      unselectedLabelTextStyle: TextStyle(color: Color(0xff9ca3af)),
    ),
  );
}
