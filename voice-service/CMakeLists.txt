cmake_minimum_required(VERSION 3.20)
project(tsbot_voice_service LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Protobuf CONFIG REQUIRED)
find_package(gRPC CONFIG REQUIRED)

set(PROTO_FILE "${CMAKE_CURRENT_LIST_DIR}/../proto/voice.proto")

protobuf_generate_cpp(PROTO_SRCS PROTO_HDRS ${PROTO_FILE})
grpc_generate_cpp(GRPC_SRCS GRPC_HDRS ${PROTO_FILE})

add_executable(voice-service
  src/main.cpp
  ${PROTO_SRCS}
  ${GRPC_SRCS}
)

target_include_directories(voice-service PRIVATE
  ${CMAKE_CURRENT_BINARY_DIR}
)

target_link_libraries(voice-service PRIVATE
  protobuf::libprotobuf
  gRPC::grpc++
  gRPC::grpc++_reflection
)

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
