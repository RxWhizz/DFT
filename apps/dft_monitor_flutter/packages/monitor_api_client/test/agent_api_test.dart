import 'package:test/test.dart';
import 'package:monitor_api_client/monitor_api_client.dart';


/// tests for AgentApi
void main() {
  final instance = MonitorApiClient().getAgentApi();

  group(AgentApi, () {
    // Agent Chat
    //
    //Future<AgentChatResponse> agentChatApiAgentChatPost(AgentChatRequest agentChatRequest) async
    test('test agentChatApiAgentChatPost', () async {
      // TODO
    });

    // Agent Health
    //
    //Future<AgentHealthResponse> agentHealthApiAgentHealthGet() async
    test('test agentHealthApiAgentHealthGet', () async {
      // TODO
    });

    // Approve Proposal
    //
    //Future<AgentProposalResponse> approveProposalApiAgentProposalsProposalIdApprovePost(String proposalId) async
    test('test approveProposalApiAgentProposalsProposalIdApprovePost', () async {
      // TODO
    });

    // Reject Proposal
    //
    //Future<AgentProposalResponse> rejectProposalApiAgentProposalsProposalIdRejectPost(String proposalId) async
    test('test rejectProposalApiAgentProposalsProposalIdRejectPost', () async {
      // TODO
    });

  });
}
