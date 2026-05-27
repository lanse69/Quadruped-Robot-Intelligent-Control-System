// 策略运行时规则占位实现

#include <string>
#include <utility>

#include "qrics/control/policy_runtime.hpp"

namespace qrics::control {

namespace {

[[nodiscard]] qrics::common::Result<PolicyRuntimeResult> fail(const std::string& code,
                                                              const std::string& message) {
  return qrics::common::Result<PolicyRuntimeResult>::failure({qrics::common::Error{code, message}});
}

}  // namespace

RuleBasedPolicyRuntime::RuleBasedPolicyRuntime(const LocalPlanner& local_planner)
    : local_planner_(local_planner) {}

qrics::common::Result<PolicyRuntimeResult> RuleBasedPolicyRuntime::infer(
    const PolicyRuntimeRequest& request) const {
  if (request.run_id.empty()) {
    return fail("RUN_ID_EMPTY", "PolicyRuntimeRequest.run_id must not be empty");
  }
  if (request.task_node.node_id.empty()) {
    return fail("TASK_NODE_ID_EMPTY", "PolicyRuntimeRequest.task_node.node_id must not be empty");
  }

  LocalPlanRequest plan_request{};
  plan_request.task_node = request.task_node;
  plan_request.target = request.target;
  plan_request.robot_state = request.robot_state;
  plan_request.policy_ref = request.policy_ref;
  plan_request.timestamp_ns = request.timestamp_ns;

  auto local_plan = local_planner_.plan(plan_request);
  if (!local_plan.ok) {
    return qrics::common::Result<PolicyRuntimeResult>::failure(local_plan.errors);
  }

  PolicyRuntimeResult result{};
  result.proposal = std::move(local_plan.value.proposal);
  result.target_reached = local_plan.value.target_reached;
  result.reason = std::move(local_plan.value.reason);
  return qrics::common::Result<PolicyRuntimeResult>::success(std::move(result));
}

}  // namespace qrics::control