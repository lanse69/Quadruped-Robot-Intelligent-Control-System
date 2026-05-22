// 顺序任务图规划器

#include <cstddef>
#include <string>
#include <utility>

#include "qrics/task/task_graph_planner.hpp"

namespace qrics::task {

namespace {

void add_edge_if_needed(TaskGraph& graph, const std::string& previous_node_id,
                        const std::string& next_node_id) {
  if (previous_node_id.empty()) {
    return;
  }
  TaskEdge edge{};
  edge.from_node_id = previous_node_id;
  edge.to_node_id = next_node_id;
  edge.condition = "completed";
  graph.edges.push_back(std::move(edge));
}

}  // namespace

qrics::common::Result<TaskGraph> SequentialTaskGraphPlanner::plan(
    const TaskScript& task_script, const std::vector<PolicySelection>& selections) const {
  if (task_script.task_id.empty() || task_script.version.empty()) {
    return qrics::common::Result<TaskGraph>::failure(
        {qrics::common::Error{"TASK_REF_EMPTY", "TaskScript task_id/version must not be empty"}});
  }
  if (task_script.waypoints.empty()) {
    return qrics::common::Result<TaskGraph>::failure(
        {qrics::common::Error{"NO_WAYPOINTS", "TaskScript must contain at least one waypoint"}});
  }
  if (selections.size() != task_script.waypoints.size()) {
    return qrics::common::Result<TaskGraph>::failure({qrics::common::Error{
        "POLICY_SELECTION_SIZE_MISMATCH", "Policy selections must match waypoint count"}});
  }

  TaskGraph graph{};
  graph.graph_id = "graph_" + task_script.task_id + "_" + task_script.version;
  graph.task_ref = qrics::common::ResourceRef{task_script.task_id, task_script.version};
  graph.checksum.algorithm = "placeholder";
  graph.checksum.value = graph.graph_id;

  std::string previous_node_id{};
  for (std::size_t index = 0U; index < task_script.waypoints.size(); ++index) {
    const auto& waypoint = task_script.waypoints[index];

    TaskNode move_node{};
    move_node.node_id = "node_" + std::to_string(index + 1U) + "_move_to_" + waypoint.waypoint_id;
    move_node.type = TaskNodeType::MoveTo;
    move_node.target_waypoint_id = waypoint.waypoint_id;
    move_node.policy_tag = selections[index].policy_tag;
    move_node.fallback_action = task_script.fallback_action;

    if (graph.entry_node_id.empty()) {
      graph.entry_node_id = move_node.node_id;
    }

    add_edge_if_needed(graph, previous_node_id, move_node.node_id);
    previous_node_id = move_node.node_id;
    graph.nodes.push_back(std::move(move_node));

    if (waypoint.dwell_time_s > 0.0) {
      TaskNode dwell_node{};
      dwell_node.node_id = "node_" + std::to_string(index + 1U) + "_dwell_" + waypoint.waypoint_id;
      dwell_node.type = TaskNodeType::Dwell;
      dwell_node.target_waypoint_id = waypoint.waypoint_id;
      dwell_node.policy_tag = selections[index].policy_tag;
      dwell_node.fallback_action = task_script.fallback_action;
      add_edge_if_needed(graph, previous_node_id, dwell_node.node_id);
      previous_node_id = dwell_node.node_id;
      graph.nodes.push_back(std::move(dwell_node));
    }
  }

  TaskNode stop_node{};
  stop_node.node_id = "node_terminal_stop";
  stop_node.type = TaskNodeType::Stop;
  stop_node.fallback_action = task_script.fallback_action;
  add_edge_if_needed(graph, previous_node_id, stop_node.node_id);
  graph.terminal_node_id = stop_node.node_id;
  graph.nodes.push_back(std::move(stop_node));

  return qrics::common::Result<TaskGraph>::success(std::move(graph));
}

}  // namespace qrics::task