// 局部规划接口与占位实现

#include <cmath>
#include <string>
#include <utility>

#include "qrics/control/local_planner.hpp"

namespace qrics::control {

namespace {

[[nodiscard]] double distance_between(const qrics::common::Pose& lhs,
                                      const qrics::common::Pose& rhs) noexcept {
  const double dx = rhs.position.x - lhs.position.x;
  const double dy = rhs.position.y - lhs.position.y;
  const double dz = rhs.position.z - lhs.position.z;
  return std::sqrt((dx * dx) + (dy * dy) + (dz * dz));
}

[[nodiscard]] qrics::common::Vec3 direction_to_target(const qrics::common::Pose& current,
                                                      const qrics::common::Pose& target,
                                                      double speed_mps) noexcept {
  const double dx = target.position.x - current.position.x;
  const double dy = target.position.y - current.position.y;
  const double dz = target.position.z - current.position.z;
  const double norm = std::sqrt((dx * dx) + (dy * dy) + (dz * dz));
  if (norm <= 1.0e-9) {
    return {};
  }
  return qrics::common::Vec3{speed_mps * dx / norm, speed_mps * dy / norm, speed_mps * dz / norm};
}

[[nodiscard]] ActionProposal make_proposal_base(const LocalPlanRequest& request,
                                                ActionType action_type) {
  ActionProposal proposal{};
  proposal.proposal_id = "proposal_" + request.task_node.node_id;
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

}  // namespace

qrics::common::Result<LocalPlan> SimpleLocalPlanner::plan(const LocalPlanRequest& request) const {
  if (request.task_node.node_id.empty()) {
    return fail("TASK_NODE_ID_EMPTY", "Task node id must not be empty");
  }

  LocalPlan plan{};

  switch (request.task_node.type) {
    case qrics::task::TaskNodeType::MoveTo:
    case qrics::task::TaskNodeType::ReturnHome: {
      if (request.target.waypoint_id.empty()) {
        return fail("TARGET_WAYPOINT_EMPTY", "MoveTo/ReturnHome requires a target waypoint");
      }

      const double distance = distance_between(request.robot_state.pose, request.target.pose);
      plan.target_reached = distance <= target_tolerance_m_;
      plan.proposal = make_proposal_base(
          request, plan.target_reached ? ActionType::Stop : ActionType::BodyVelocity);
      if (!plan.target_reached) {
        plan.proposal.desired_body_velocity =
            direction_to_target(request.robot_state.pose, request.target.pose, nominal_speed_mps_);
      }
      plan.reason = plan.target_reached ? "Target waypoint reached" : "Move toward target waypoint";
      return qrics::common::Result<LocalPlan>::success(std::move(plan));
    }

    case qrics::task::TaskNodeType::Dwell:
      plan.proposal = make_proposal_base(request, ActionType::Stop);
      plan.reason = "Hold position during dwell";
      return qrics::common::Result<LocalPlan>::success(std::move(plan));

    case qrics::task::TaskNodeType::Stop:
      plan.proposal = make_proposal_base(request, ActionType::Stop);
      plan.target_reached = true;
      plan.reason = "Terminal stop action";
      return qrics::common::Result<LocalPlan>::success(std::move(plan));

    case qrics::task::TaskNodeType::Inspect:
      plan.proposal = make_proposal_base(request, ActionType::SafeStand);
      plan.reason = "Inspect placeholder uses SafeStand";
      return qrics::common::Result<LocalPlan>::success(std::move(plan));
  }

  return fail("TASK_NODE_TYPE_UNSUPPORTED", "Unsupported task node type");
}

}  // namespace qrics::control