import '../api/errors.dart';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import '../repositories/repositories.dart';
import '../widgets/async_panel.dart';
import '../widgets/status_chip.dart';

class AgentView extends ConsumerStatefulWidget {
  const AgentView({super.key});

  @override
  ConsumerState<AgentView> createState() => _AgentViewState();
}

class _AgentViewState extends ConsumerState<AgentView> {
  final _controller = TextEditingController();
  final List<_ChatTurn> _turns = [];
  final Map<String, String> _proposalStatus = {};
  bool _structured = false;
  bool _sending = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final health = ref.watch(agentHealthProvider);
    final healthValue = health.asData?.value;
    final canChat =
        healthValue?.enabled == true && healthValue?.ok == true && !_sending;

    return LayoutBuilder(
      builder: (context, constraints) {
        final sidecarWidth =
            (constraints.maxWidth * 0.24).clamp(330.0, 480.0).toDouble();
        final turnMaxWidth =
            (constraints.maxWidth * 0.58).clamp(760.0, 1160.0).toDouble();
        return Row(
          children: [
            Expanded(
              child: Card(
                child: Column(
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(12),
                      child: Row(
                        children: [
                          Text('Agente',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(width: 8),
                          _HealthDot(health: health),
                          const SizedBox(width: 8),
                          Text(healthValue?.model ?? 'dft-agent:14b-q4',
                              style: Theme.of(context).textTheme.bodySmall),
                          if (healthValue?.modelPresent == false) ...[
                            const SizedBox(width: 8),
                            const StatusChip('modelo pendiente'),
                          ],
                        ],
                      ),
                    ),
                    const Divider(height: 1),
                    Expanded(
                      child: ListView(
                        padding: const EdgeInsets.all(12),
                        children: [
                          if (health.hasError)
                            _Warning(
                                text:
                                    'No se pudo consultar el agente: ${health.error}'),
                          if (healthValue != null &&
                              healthValue.enabled &&
                              !healthValue.ok)
                            _Warning(
                                text:
                                    'Agente no disponible: ${healthValue.error ?? 'Ollama no responde'}'),
                          if (_turns.isEmpty)
                            Padding(
                              padding: const EdgeInsets.all(12),
                              child: Text(
                                'Pregunta por jobs, logs, trazas, batches, cribado o reportes.',
                                style: Theme.of(context).textTheme.bodyMedium,
                              ),
                            ),
                          for (final turn in _turns)
                            _TurnCard(
                              turn: turn,
                              maxWidth: turnMaxWidth,
                              proposalStatus: _proposalStatus,
                              onProposal: _proposal,
                            ),
                        ],
                      ),
                    ),
                    const Divider(height: 1),
                    Padding(
                      padding: const EdgeInsets.all(12),
                      child: Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _controller,
                              enabled: canChat,
                              minLines: 1,
                              maxLines: 4,
                              decoration: const InputDecoration(
                                  hintText: 'Pregunta al agente local'),
                              onSubmitted: canChat ? (_) => _send() : null,
                            ),
                          ),
                          const SizedBox(width: 8),
                          FilterChip(
                            selected: _structured,
                            label: const Text('JSON'),
                            onSelected: (value) =>
                                setState(() => _structured = value),
                          ),
                          const SizedBox(width: 8),
                          FilledButton.icon(
                            onPressed: canChat ? _send : null,
                            icon: const Icon(Icons.send_outlined),
                            label: Text(_sending ? '...' : 'Enviar'),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 12),
            SizedBox(
              width: sidecarWidth,
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: AsyncPanel(
                    value: health,
                    builder: (data) => _AgentSidecar(health: data),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Future<void> _send() async {
    final message = _controller.text.trim();
    if (message.isEmpty) return;
    setState(() => _sending = true);
    try {
      final history = _turns
          .take(_turns.length)
          .toList()
          .reversed
          .take(8)
          .toList()
          .reversed
          .map((turn) => {'role': turn.role, 'content': turn.content})
          .toList();
      final response = await ref.read(agentActionsProvider).chat(
            message: message,
            history: history,
            structured: _structured,
          );
      setState(() {
        _turns.add(_ChatTurn(role: 'user', content: message));
        _turns.add(_ChatTurn(
            role: 'assistant', content: response.message, response: response));
        _controller.clear();
      });
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(mensajeDeError(error))));
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _proposal(String id, bool approve) async {
    try {
      final proposal = approve
          ? await ref.read(agentActionsProvider).approve(id)
          : await ref.read(agentActionsProvider).reject(id);
      setState(() => _proposalStatus[id] = proposal.status);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(mensajeDeError(error))));
      }
    }
  }
}

class _ChatTurn {
  const _ChatTurn({required this.role, required this.content, this.response});

  final String role;
  final String content;
  final AgentChatResponse? response;
}

class _HealthDot extends StatelessWidget {
  const _HealthDot({required this.health});

  final AsyncValue<AgentHealth> health;

  @override
  Widget build(BuildContext context) {
    final data = health.asData?.value;
    final color = health.isLoading
        ? Colors.amberAccent
        : data?.ok == true
            ? Colors.greenAccent
            : data?.enabled == true
                ? Colors.amberAccent
                : Colors.grey;
    return Container(
      width: 8,
      height: 8,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
  }
}

class _Warning extends StatelessWidget {
  const _Warning({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xff451a03),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Text(text),
      ),
    );
  }
}

class _TurnCard extends StatelessWidget {
  const _TurnCard({
    required this.turn,
    required this.maxWidth,
    required this.proposalStatus,
    required this.onProposal,
  });

  final _ChatTurn turn;
  final double maxWidth;
  final Map<String, String> proposalStatus;
  final void Function(String id, bool approve) onProposal;

  @override
  Widget build(BuildContext context) {
    final isUser = turn.role == 'user';
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: Card(
          color: isUser ? const Color(0xff0f2744) : null,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(isUser ? 'Tu' : 'Agente',
                    style: Theme.of(context).textTheme.labelSmall),
                const SizedBox(height: 6),
                SelectableText(turn.content),
                if (turn.response != null)
                  _AgentResult(response: turn.response!),
                for (final id in turn.response?.proposalIds ?? const <String>[])
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Row(
                      children: [
                        Expanded(
                            child: Text(id, overflow: TextOverflow.ellipsis)),
                        OutlinedButton(
                          onPressed: proposalStatus[id] == 'approved'
                              ? null
                              : () => onProposal(id, true),
                          child: const Text('Aprobar'),
                        ),
                        const SizedBox(width: 6),
                        OutlinedButton(
                          onPressed: proposalStatus[id] == 'rejected'
                              ? null
                              : () => onProposal(id, false),
                          child: const Text('Rechazar'),
                        ),
                        if (proposalStatus[id] != null) ...[
                          const SizedBox(width: 6),
                          StatusChip(proposalStatus[id]!),
                        ],
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AgentResult extends StatelessWidget {
  const _AgentResult({required this.response});

  final AgentChatResponse response;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (response.toolResults.isNotEmpty)
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final tool in response.toolResults)
                  Tooltip(
                    message: tool.error ?? tool.name,
                    child: StatusChip('${tool.name}${tool.ok ? '' : ' !'}'),
                  ),
              ],
            ),
          if (response.structured != null) ...[
            const SizedBox(height: 8),
            Container(
              constraints: const BoxConstraints(maxHeight: 260),
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                border: Border.all(color: const Color(0xff334155)),
                borderRadius: BorderRadius.circular(6),
              ),
              child: SingleChildScrollView(
                child: SelectableText(
                  const JsonEncoder.withIndent('  ')
                      .convert(response.structured),
                  style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _AgentSidecar extends StatelessWidget {
  const _AgentSidecar({required this.health});

  final AgentHealth health;

  @override
  Widget build(BuildContext context) {
    final status = health.ok
        ? 'listo'
        : health.enabled
            ? health.error ?? 'no disponible'
            : 'desactivado';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Ollama', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        _Line('Estado', status),
        _Line('Provider', health.provider),
        _Line('URL', health.baseUrl),
        _Line('Version', health.version ?? '-'),
        _Line('Modelo', health.model),
        _Line('Modelos', health.modelsDir),
        _Line('Revive', health.reviveRepo),
        const Divider(height: 28),
        const Text(
            'Herramientas v1: solo lectura. Maximo 4 rondas. Escrituras por propuesta auditada.'),
      ],
    );
  }
}

class _Line extends StatelessWidget {
  const _Line(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
              width: 86,
              child: Text(label, style: Theme.of(context).textTheme.bodySmall)),
          Expanded(child: Text(value, overflow: TextOverflow.ellipsis)),
        ],
      ),
    );
  }
}
