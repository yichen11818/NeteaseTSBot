cmake_minimum_required(VERSION 3.20)
project(tsbot_voice_service LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Protobuf REQUIRED)
find_package(PkgConfig REQUIRED)

set(PROTO_FILE "${CMAKE_CURRENT_LIST_DIR}/../proto/voice.proto")

get_filename_component(PROTO_DIR "${PROTO_FILE}" DIRECTORY)

set(GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}")
set(PROTO_SRCS "${GENERATED_DIR}/voice.pb.cc")
set(PROTO_HDRS "${GENERATED_DIR}/voice.pb.h")
set(GRPC_SRCS "${GENERATED_DIR}/voice.grpc.pb.cc")
set(GRPC_HDRS "${GENERATED_DIR}/voice.grpc.pb.h")

if(NOT Protobuf_PROTOC_EXECUTABLE)
  message(FATAL_ERROR "protoc not found. Install protobuf-compiler")
endif()

pkg_check_modules(GRPCPP REQUIRED grpc++)
pkg_check_modules(GRPC REQUIRED grpc)
find_program(GRPC_CPP_PLUGIN_EXECUTABLE grpc_cpp_plugin)

if(NOT GRPC_CPP_PLUGIN_EXECUTABLE)
  message(FATAL_ERROR "grpc_cpp_plugin not found. On Ubuntu try: sudo apt install protobuf-compiler-grpc libgrpc++-dev")
endif()

add_custom_command(
  OUTPUT "${PROTO_SRCS}" "${PROTO_HDRS}"
  COMMAND "${Protobuf_PROTOC_EXECUTABLE}"
    --proto_path=${PROTO_DIR}
    --cpp_out=${GENERATED_DIR}
    ${PROTO_FILE}
  DEPENDS "${PROTO_FILE}"
  VERBATIM
)

add_custom_command(
  OUTPUT "${GRPC_SRCS}" "${GRPC_HDRS}"
  COMMAND "${Protobuf_PROTOC_EXECUTABLE}"
    --proto_path=${PROTO_DIR}
    --proto_path=${Protobuf_INCLUDE_DIRS}
    --grpc_out=${GENERATED_DIR}
    --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN_EXECUTABLE}
    ${PROTO_FILE}
  DEPENDS "${PROTO_FILE}" "${PROTO_SRCS}"
  VERBATIM
)

add_executable(voice-service
  src/main.cpp
  ${PROTO_SRCS}
  ${GRPC_SRCS}
)

target_include_directories(voice-service PRIVATE
  ${CMAKE_CURRENT_BINARY_DIR}
  ${Protobuf_INCLUDE_DIRS}
  ${GRPCPP_INCLUDE_DIRS}
)

target_link_directories(voice-service PRIVATE
  ${GRPCPP_LIBRARY_DIRS}
  ${GRPC_LIBRARY_DIRS}
)

target_link_libraries(voice-service PRIVATE
  ${GRPCPP_LIBRARIES}
  ${GRPC_LIBRARIES}
)

if(TARGET protobuf::libprotobuf)
  target_link_libraries(voice-service PRIVATE protobuf::libprotobuf)
else()
  target_link_libraries(voice-service PRIVATE ${Protobuf_LIBRARIES})
endif()

set(TS3_SDK_DIR "${CMAKE_CURRENT_LIST_DIR}/../ts3sdk" CACHE PATH "Path to TeamSpeak 3 SDK root (contains include/ and bin/)")

if(EXISTS "${TS3_SDK_DIR}/include/teamspeak/clientlib.h")
  target_include_directories(voice-service PRIVATE "${TS3_SDK_DIR}/include")
  add_compile_definitions(TSBOT_HAS_TS3_SDK=1)

  find_library(TS3CLIENT_LIB
    NAMES ts3client
    PATHS
      "${TS3_SDK_DIR}/bin/linux/amd64"
      "${TS3_SDK_DIR}/bin/linux/x86_64"
      "${TS3_SDK_DIR}/bin/linux"
    NO_DEFAULT_PATH
  )

  if(TS3CLIENT_LIB)
    target_link_libraries(voice-service PRIVATE "${TS3CLIENT_LIB}")

    get_filename_component(_ts3client_dir "${TS3CLIENT_LIB}" DIRECTORY)
    set_target_properties(voice-service PROPERTIES
      BUILD_RPATH "${_ts3client_dir}"
    )
  else()
    message(WARNING "TS3 SDK found but libts3client.so not found under ${TS3_SDK_DIR}/bin/linux/*")
  endif()
endif()
