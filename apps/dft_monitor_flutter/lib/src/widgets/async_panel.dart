import '../api/errors.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class AsyncPanel<T> extends StatelessWidget {
  const AsyncPanel({
    required this.value,
    required this.builder,
    this.height,
    super.key,
  });

  final AsyncValue<T> value;
  final Widget Function(T data) builder;
  final double? height;

  @override
  Widget build(BuildContext context) {
    return value.when(
      // Sin esto, cada tick del refresco deja el panel en estado «cargando» y
      // el spinner sustituye al contenido: con 17 providers mirando el mismo
      // reloj, la pantalla entera saltaba cada cinco segundos. `when` sí
      // conserva los datos al refrescar (`skipLoadingOnRefresh`), pero no
      // cuando el provider se reconstruye porque cambió algo que observa, que
      // es justo lo que hace el tick.
      skipLoadingOnReload: true,
      data: builder,
      loading: () => SizedBox(
        height: height ?? 120,
        child: const Center(child: CircularProgressIndicator()),
      ),
      error: (error, stack) => SizedBox(
        height: height ?? 120,
        child: Center(
          child: Text(mensajeDeError(error), style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ),
      ),
    );
  }
}
