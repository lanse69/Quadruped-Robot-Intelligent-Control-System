cmake_minimum_required(VERSION 3.24)

project(
  QRICS
  VERSION 0.1.0
  DESCRIPTION "Simulation-based Quadruped Robot Intelligent Control System"
  LANGUAGES CXX
)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

include(ProjectOptions)

add_library(qrics_core
  src/core/version.cpp
  src/config/config_error.cpp
  src/config/policy_config_loader.cpp
  src/config/scene_config_loader.cpp
  src/config/training_config_loader.cpp
  src/control/simple_local_planner.cpp
  src/control/rule_based_policy_runtime.cpp
  src/control/task_executor.cpp
  src/task/basic_explanation_service.cpp
  src/task/basic_task_constraint_engine.cpp
  src/task/rule_based_chinese_task_parser.cpp
  src/task/rule_based_policy_selector.cpp
  src/task/sequential_task_graph_planner.cpp
  src/task/task_understanding_pipeline.cpp
  src/task/in_memory_task_session_store.cpp
  src/task/task_orchestrator_service.cpp
)

target_include_directories(qrics_core
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(qrics_core PUBLIC cxx_std_20)

qrics_apply_common_options(qrics_core)

add_executable(qrics_cli
  apps/qrics_cli.cpp
)

target_link_libraries(qrics_cli
  PRIVATE
    qrics_core
)

qrics_apply_common_options(qrics_cli)

enable_testing()

add_executable(qrics_version_test
  tests/cpp/test_version.cpp
)

target_link_libraries(qrics_version_test
  PRIVATE
    qrics_core
)

qrics_apply_common_options(qrics_version_test)

add_test(NAME qrics_version_test COMMAND qrics_version_test)

add_executable(qrics_domain_model_test
  tests/cpp/test_domain_model.cpp
)

target_link_libraries(qrics_domain_model_test
  PRIVATE
    qrics_core
)

qrics_apply_common_options(qrics_domain_model_test)

add_test(NAME qrics_domain_model_test COMMAND qrics_domain_model_test)

add_executable(qrics_safety_shield_test
  tests/cpp/test_safety_shield.cpp
)

target_link_libraries(qrics_safety_shield_test
  PRIVATE
    qrics_core
)

qrics_apply_common_options(qrics_safety_shield_test)

add_test(NAME qrics_safety_shield_test COMMAND qrics_safety_shield_test)

add_executable(qrics_control_loop_test
  tests/cpp/test_control_loop.cpp
)

target_link_libraries(qrics_control_loop_test
  PRIVATE
    qrics_core
)

qrics_apply_common_options(qrics_control_loop_test)

add_test(NAME qrics_control_loop_test COMMAND qrics_control_loop_test)

add_executable(qrics_task_understanding_test
  tests/cpp/test_task_understanding.cpp
)

target_link_libraries(qrics_task_understanding_test
  PRIVATE
    qrics_core
)

qrics_apply_common_options(qrics_task_understanding_test)

add_test(NAME qrics_task_understanding_test COMMAND qrics_task_understanding_test)

add_executable(qrics_task_orchestrator_test
  tests/cpp/test_task_orchestrator.cpp
)

target_link_libraries(qrics_task_orchestrator_test
  PRIVATE
    qrics_core
)

qrics_apply_common_options(qrics_task_orchestrator_test)

add_test(NAME qrics_task_orchestrator_test COMMAND qrics_task_orchestrator_test)

add_executable(qrics_scene_config_loader_test
  tests/cpp/test_scene_config_loader.cpp
)

target_link_libraries(qrics_scene_config_loader_test
  PRIVATE
    qrics_core
)

qrics_apply_common_options(qrics_scene_config_loader_test)

add_test(NAME qrics_scene_config_loader_test COMMAND qrics_scene_config_loader_test)

add_executable(qrics_policy_config_loader_test
  tests/cpp/test_policy_config_loader.cpp
)

target_link_libraries(qrics_policy_config_loader_test
  PRIVATE
    qrics_core
)

qrics_apply_common_options(qrics_policy_config_loader_test)

add_test(NAME qrics_policy_config_loader_test COMMAND qrics_policy_config_loader_test)

add_executable(qrics_policy_runtime_test
  tests/cpp/test_policy_runtime.cpp
)

target_link_libraries(qrics_policy_runtime_test
  PRIVATE
    qrics_core
)

qrics_apply_common_options(qrics_policy_runtime_test)

add_test(NAME qrics_policy_runtime_test COMMAND qrics_policy_runtime_test)

add_executable(qrics_task_executor_test
  tests/cpp/test_task_executor.cpp
)

target_link_libraries(qrics_task_executor_test
  PRIVATE
    qrics_core
)

qrics_apply_common_options(qrics_task_executor_test)

add_test(NAME qrics_task_executor_test COMMAND qrics_task_executor_test)