#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <memory>
#include <string>

#include <grpcpp/grpcpp.h>
#include <google/protobuf/empty.pb.h>

#include "voice.grpc.pb.h"

namespace voicev1 = tsbot::voice::v1;

class VoiceServiceImpl final : public voicev1::VoiceService::Service {
 public:
  grpc::Status Ping(grpc::ServerContext*, const google::protobuf::Empty*, voicev1::PingResponse* out) override {
    out->set_version("0.1.0");
    return grpc::Status::OK;
  }

  grpc::Status Play(grpc::ServerContext*, const voicev1::PlayRequest* req, voicev1::CommandResponse* out) override {
    now_playing_title_ = req->title();
    now_playing_url_ = req->source_url();
    state_ = voicev1::StatusResponse::STATE_PLAYING;
    out->set_ok(true);
    out->set_message("accepted");
    return grpc::Status::OK;
  }

  grpc::Status Pause(grpc::ServerContext*, const google::protobuf::Empty*, voicev1::CommandResponse* out) override {
    if (state_ == voicev1::StatusResponse::STATE_PLAYING) state_ = voicev1::StatusResponse::STATE_PAUSED;
    out->set_ok(true);
    out->set_message("ok");
    return grpc::Status::OK;
  }

  grpc::Status Resume(grpc::ServerContext*, const google::protobuf::Empty*, voicev1::CommandResponse* out) override {
    if (state_ == voicev1::StatusResponse::STATE_PAUSED) state_ = voicev1::StatusResponse::STATE_PLAYING;
    out->set_ok(true);
    out->set_message("ok");
    return grpc::Status::OK;
  }

  grpc::Status Stop(grpc::ServerContext*, const google::protobuf::Empty*, voicev1::CommandResponse* out) override {
    state_ = voicev1::StatusResponse::STATE_IDLE;
    now_playing_title_.clear();
    now_playing_url_.clear();
    out->set_ok(true);
    out->set_message("ok");
    return grpc::Status::OK;
  }

  grpc::Status Skip(grpc::ServerContext*, const google::protobuf::Empty*, voicev1::CommandResponse* out) override {
    state_ = voicev1::StatusResponse::STATE_IDLE;
    now_playing_title_.clear();
    now_playing_url_.clear();
    out->set_ok(true);
    out->set_message("ok");
    return grpc::Status::OK;
  }

  grpc::Status SetVolume(grpc::ServerContext*, const voicev1::SetVolumeRequest* req, voicev1::CommandResponse* out) override {
    volume_percent_ = std::clamp(req->volume_percent(), 0, 200);
    out->set_ok(true);
    out->set_message("ok");
    return grpc::Status::OK;
  }

  grpc::Status GetStatus(grpc::ServerContext*, const google::protobuf::Empty*, voicev1::StatusResponse* out) override {
    out->set_state(state_);
    out->set_now_playing_title(now_playing_title_);
    out->set_now_playing_source_url(now_playing_url_);
    out->set_volume_percent(volume_percent_);
    return grpc::Status::OK;
  }

  grpc::Status SubscribeEvents(grpc::ServerContext*, const voicev1::SubscribeRequest*, grpc::ServerWriter<voicev1::Event>*) override {
    return grpc::Status(grpc::StatusCode::UNIMPLEMENTED, "event stream not implemented");
  }

 private:
  voicev1::StatusResponse::State state_ = voicev1::StatusResponse::STATE_IDLE;
  std::string now_playing_title_;
  std::string now_playing_url_;
  int volume_percent_ = 100;
};

int main(int argc, char** argv) {
  std::string addr = "127.0.0.1:50051";
  if (argc >= 2) addr = argv[1];

  VoiceServiceImpl service;

  grpc::ServerBuilder builder;
  builder.AddListeningPort(addr, grpc::InsecureServerCredentials());
  builder.RegisterService(&service);

  std::unique_ptr<grpc::Server> server(builder.BuildAndStart());
  if (!server) {
    std::cerr << "failed to start grpc server" << std::endl;
    return 1;
  }

  std::cout << "voice-service listening on " << addr << std::endl;
  server->Wait();
  return 0;
}
