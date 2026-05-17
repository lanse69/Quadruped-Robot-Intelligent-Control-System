function(qrics_apply_common_options target_name)
  target_compile_options(${target_name}
    PRIVATE
      $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall>
      $<$<CXX_COMPILER_ID:GNU,Clang>:-Wextra>
      $<$<CXX_COMPILER_ID:GNU,Clang>:-Wpedantic>
      $<$<CXX_COMPILER_ID:GNU,Clang>:-Wconversion>
      $<$<CXX_COMPILER_ID:GNU,Clang>:-Wsign-conversion>
  )

  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(${target_name}
      PRIVATE
        $<$<CONFIG:Debug>:-O0>
        $<$<CONFIG:Debug>:-g>
        $<$<CONFIG:Release>:-O3>
    )
  endif()
endfunction()

find_program(CCACHE_PROGRAM ccache)
if(CCACHE_PROGRAM)
  set(CMAKE_CXX_COMPILER_LAUNCHER "${CCACHE_PROGRAM}" CACHE STRING "CXX compiler launcher")
endif()