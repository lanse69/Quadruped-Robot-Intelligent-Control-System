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