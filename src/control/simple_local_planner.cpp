// 局部规划接口与规则实现

#include <string>
#include <utility>

#include "qrics/control/local_planner.hpp"

namespace qrics::control {

namespace {

[[nodiscard]] ActionProposal make_proposal_base(const LocalPlanRequest& request,
                                                ActionType action_type, const std::string& prefix) {
  ActionProposal proposal{};
  proposal.proposal_id = prefix + "_" + request.task_node.node_id;
  proposal.policy_ref = request.policy_ref;
  proposal.task_node_id = request.task_node.node_id;
  proposal.action_type = action_type;
  proposal.confidence = 1.0;
  proposal.timestamp_ns = request.timestamp_ns;
  return proposal;
}

[[nodiscard]] qrics::common::Result<LocalPlan> fail(const std::string& code,
                                                    const std::string& message) {
  return qrics::common::Result<LocalPlan>::failure({qrics::common::Error{code, message}});
}

[[nodiscard]] LocalPlan from_recovery_decision(RecoveryDecision decision) {
  LocalPlan plan{};
  plan.proposal = std::move(decision.proposal);
  plan.target_reached = false;
  plan.reason = std::move(decision.reason);
  return plan;
}

}  // namespace

qrics::common::Result<LocalPlan> SimpleLocalPlanner::plan(const LocalPlanRequest& request) const {
  if (request.task_node.node_id.empty()) {
    return fail("TASK_NODE_ID_EMPTY", "Task node id must not be empty");
  }

  RecoveryRequest recovery_request{};
  recovery_request.task_node = request.task_node;
  recovery_request.robot_state = request.robot_state;
  recovery_request.policy_ref = request.policy_ref;
  recovery_request.timestamp_ns = request.timestamp_ns;
  auto recovery = recovery_controller_.evaluate(recovery_request);
  if (recovery.recovery_required) {
    return qrics::common::Result<LocalPlan>::success(from_recovery_decision(std::move(recovery)));
  }

  LocalPlan plan{};

  switch (request.task_node.type) {
    case qrics::task::TaskNodeType::MoveTo:
    case qrics::task::TaskNodeType::ReturnHome: {
      if (request.target.waypoint_id.empty()) {
        return fail("TARGET_WAYPOINT_EMPTY", "MoveTo/ReturnHome requires a target waypoint");
      }

      PathTrackRequest track_request{};
      track_request.task_node = request.task_node;
      track_request.target = request.target;
      track_request.robot_state = request.robot_state;
      track_request.policy_ref = request.policy_ref;
      track_request.timestamp_ns = request.timestamp_ns;
      auto tracked = path_tracker_.track(track_request);
      if (!tracked.ok) {
        return qrics::common::Result<LocalPlan>::failure(tracked.errors);
      }

      plan.target_reached = tracked.value.target_reached;
      plan.proposal = std::move(tracked.value.proposal);
      plan.reason = std::move(tracked.value.reason);

      if (!plan.target_reached) {
        ObstacleAvoidanceRequest avoidance_request{};
        avoidance_request.proposal = plan.proposal;
        avoidance_request.observation = request.observation;
        auto avoidance = obstacle_avoidance_.apply(avoidance_request);
        plan.proposal = std::move(avoidance.proposal);
        if (avoidance.adjusted) {
          plan.reason = std::move(avoidance.reason);
        }
      }

      return qrics::common::Result<LocalPlan>::success(std::move(plan));
    }

    case qrics::task::TaskNodeType::Dwell:
      plan.proposal = make_proposal_base(request, ActionType::Stop, "dwell");
      plan.reason = "Hold position during dwell";
      return qrics::common::Result<LocalPlan>::success(std::move(plan));

    case qrics::task::TaskNodeType::Stop:
      plan.proposal = make_proposal_base(request, ActionType::Stop, "stop");
      plan.target_reached = true;
      plan.reason = "Terminal stop action";
      return qrics::common::Result<LocalPlan>::success(std::move(plan));

    case qrics::task::TaskNodeType::Inspect:
      plan.proposal = make_proposal_base(request, ActionType::SafeStand, "inspect");
      plan.reason = "Inspect task holds the robot in SafeStand";
      return qrics::common::Result<LocalPlan>::success(std::move(plan));
  }

  return fail("TASK_NODE_TYPE_UNSUPPORTED", "Unsupported task node type");
}

}  // namespace qrics::control