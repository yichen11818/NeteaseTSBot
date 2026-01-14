#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include <grpcpp/grpcpp.h>
#include <google/protobuf/empty.pb.h>

#if defined(TSBOT_HAS_TS3_SDK)
#include <teamlog/logtypes.h>
#include <teamspeak/clientlib.h>
#include <teamspeak/public_definitions.h>
#endif

#include "voice.grpc.pb.h"

namespace voicev1 = tsbot::voice::v1;

#if defined(TSBOT_HAS_TS3_SDK)
namespace {

std::string get_env(std::string_view key, std::string_view def = "") {
  if (const char* v = std::getenv(std::string(key).c_str()); v && *v) return std::string(v);
  return std::string(def);
}

std::mutex g_print_mu;

template <typename... Args>
void ts3_print(Args&&... args) {
  std::lock_guard<std::mutex> lk(g_print_mu);
  (std::cout << ... << std::forward<Args>(args)) << std::endl;
}

std::optional<uint64> parse_u64(std::string_view s) {
  if (s.empty()) return std::nullopt;
  try {
    return static_cast<uint64>(std::stoull(std::string(s)));
  } catch (...) {
    return std::nullopt;
  }
}

std::string ts3_err(unsigned int code) {
  char* msg = nullptr;
  if (ts3client_getErrorMessage(code, &msg) != 0 || !msg) {
    return "unknown";
  }
  std::string out = msg;
  ts3client_freeMemory(msg);
  return out;
}

struct Ts3Str {
  char* p = nullptr;
  ~Ts3Str() {
    if (p) ts3client_freeMemory(p);
  }
  Ts3Str() = default;
  Ts3Str(const Ts3Str&) = delete;
  Ts3Str& operator=(const Ts3Str&) = delete;
};

struct Ts3StrArray {
  char** p = nullptr;
  ~Ts3StrArray() {
    if (!p) return;
    // Some SDK builds do not allocate individual members separately.
    // Freeing each element may crash with heap corruption. Free the array only.
    ts3client_freeMemory(p);
  }
  Ts3StrArray() = default;
  Ts3StrArray(const Ts3StrArray&) = delete;
  Ts3StrArray& operator=(const Ts3StrArray&) = delete;
};

struct Ts3Config {
  std::string host;
  unsigned int port = 9987;
  std::string nickname;
  std::string identity;
  std::string identity_file;
  std::string server_password;
  std::string channel_password;
  std::vector<std::string> channel_path;
  std::optional<uint64> channel_id;
  std::string resources_folder;
  std::string log_folder;
};

class Ts3Client {
 public:
  Ts3Client() = default;

  bool start() {
    cfg_ = load_config();

    std::error_code ec;
    if (!cfg_.log_folder.empty()) {
      std::filesystem::create_directories(std::filesystem::path(cfg_.log_folder), ec);
    }

    if (!cfg_.identity_file.empty()) {
      std::filesystem::create_directories(std::filesystem::path(cfg_.identity_file).parent_path(), ec);
    }

    ui_.onConnectStatusChangeEvent = &Ts3Client::onConnectStatusChangeEvent;
    ui_.onTextMessageEvent = &Ts3Client::onTextMessageEvent;
    ui_.onServerErrorEvent = &Ts3Client::onServerErrorEvent;

    const int log_types = LogType_CONSOLE | LogType_FILE;
    unsigned int err = ts3client_initClientLib(&ui_, nullptr, log_types, cfg_.log_folder.c_str(), cfg_.resources_folder.c_str());
    if (err != 0) {
      std::cerr << "ts3client_initClientLib failed: " << err << " (" << ts3_err(err) << ")" << std::endl;
      ts3_print("WARNING: TS3 SDK initialization failed, continuing without TS3 connection");
      return true; // Continue without TS3 connection for development
    }

    initialized_ = true;

    if (cfg_.identity.empty()) {
      if (!cfg_.identity_file.empty() && std::filesystem::exists(std::filesystem::path(cfg_.identity_file))) {
        std::ifstream in(cfg_.identity_file);
        std::string line;
        if (in.good() && std::getline(in, line) && !line.empty()) {
          cfg_.identity = line;
        }
      }
    }

    if (cfg_.identity.empty()) {
      char* ident = nullptr;
      err = ts3client_createIdentity(&ident);
      if (err != 0) {
        std::cerr << "ts3client_createIdentity failed: " << err << " (" << ts3_err(err) << ")" << std::endl;
        return false;
      }
      cfg_.identity = ident;
      ts3client_freeMemory(ident);
      ts3_print("TS3_IDENTITY=", cfg_.identity);

      if (!cfg_.identity_file.empty()) {
        std::ofstream out(cfg_.identity_file, std::ios::trunc);
        if (out.good()) {
          out << cfg_.identity;
        }
      }
    }

    uint64 sch_id = 0;
    err = ts3client_spawnNewServerConnectionHandler(0, &sch_id);
    if (err != 0) {
      std::cerr << "ts3client_spawnNewServerConnectionHandler failed: " << err << " (" << ts3_err(err) << ")" << std::endl;
      return false;
    }
    sch_id_ = sch_id;

    {
      std::lock_guard<std::mutex> lk(mu_);
      active_instance_ = this;
    }

    // Many TS3 SDK setups require opening playback/capture devices before connecting.
    // We try to open explicit default mode/device first for better compatibility.
    {
      Ts3Str pb_mode;
      unsigned int e = ts3client_getDefaultPlayBackMode(&pb_mode.p);
      if (e != 0) ts3_print("ts3client_getDefaultPlayBackMode failed: ", e, " (", ts3_err(e), ")");
      pb_mode_ = (pb_mode.p && *pb_mode.p) ? pb_mode.p : "";
      const char* pb_mode_id = pb_mode_.c_str();
      ts3_print("TS3 playback mode=", pb_mode_id);

      Ts3StrArray pb_dev;
      e = ts3client_getDefaultPlaybackDevice(pb_mode_id, &pb_dev.p);
      if (e != 0) ts3_print("ts3client_getDefaultPlaybackDevice failed: ", e, " (", ts3_err(e), ")");

      pb_device_id_ = (pb_dev.p && pb_dev.p[1]) ? pb_dev.p[1] : "";
      pb_device_name_ = (pb_dev.p && pb_dev.p[0]) ? pb_dev.p[0] : "";
      const char* pb_try1 = pb_device_id_.c_str();
      const char* pb_try2 = pb_device_name_.c_str();
      ts3_print("TS3 playback device(name)=", pb_try2, " id=", pb_try1);

      e = ts3client_openPlaybackDevice(sch_id_, pb_mode_id, pb_try1);
      if (e == 0) {
        ts3_print("ts3client_openPlaybackDevice (id) ok");
      } else {
        ts3_print("ts3client_openPlaybackDevice (id) failed: ", e, " (", ts3_err(e), ")");
        e = ts3client_openPlaybackDevice(sch_id_, pb_mode_id, pb_try2);
        if (e == 0) {
          ts3_print("ts3client_openPlaybackDevice (name) ok");
        } else {
          ts3_print("ts3client_openPlaybackDevice (name) failed: ", e, " (", ts3_err(e), ")");
          e = ts3client_openPlaybackDevice(sch_id_, "", "");
          if (e == 0) {
            ts3_print("ts3client_openPlaybackDevice (fallback empty) ok");
          } else {
            ts3_print("ts3client_openPlaybackDevice (fallback empty) failed: ", e, " (", ts3_err(e), ")");
          }
        }
      }

      Ts3Str cap_mode;
      e = ts3client_getDefaultCaptureMode(&cap_mode.p);
      if (e != 0) ts3_print("ts3client_getDefaultCaptureMode failed: ", e, " (", ts3_err(e), ")");
      cap_mode_ = (cap_mode.p && *cap_mode.p) ? cap_mode.p : "";
      const char* cap_mode_id = cap_mode_.c_str();
      ts3_print("TS3 capture mode=", cap_mode_id);

      Ts3StrArray cap_dev;
      e = ts3client_getDefaultCaptureDevice(cap_mode_id, &cap_dev.p);
      if (e != 0) ts3_print("ts3client_getDefaultCaptureDevice failed: ", e, " (", ts3_err(e), ")");

      cap_device_id_ = (cap_dev.p && cap_dev.p[1]) ? cap_dev.p[1] : "";
      cap_device_name_ = (cap_dev.p && cap_dev.p[0]) ? cap_dev.p[0] : "";
      const char* cap_try1 = cap_device_id_.c_str();
      const char* cap_try2 = cap_device_name_.c_str();
      ts3_print("TS3 capture device(name)=", cap_try2, " id=", cap_try1);

      e = ts3client_openCaptureDevice(sch_id_, cap_mode_id, cap_try1);
      if (e == 0) {
        ts3_print("ts3client_openCaptureDevice (id) ok");
      } else {
        ts3_print("ts3client_openCaptureDevice (id) failed: ", e, " (", ts3_err(e), ")");
        e = ts3client_openCaptureDevice(sch_id_, cap_mode_id, cap_try2);
        if (e == 0) {
          ts3_print("ts3client_openCaptureDevice (name) ok");
        } else {
          ts3_print("ts3client_openCaptureDevice (name) failed: ", e, " (", ts3_err(e), ")");
          e = ts3client_openCaptureDevice(sch_id_, "", "");
          if (e == 0) {
            ts3_print("ts3client_openCaptureDevice (fallback empty) ok");
          } else {
            ts3_print("ts3client_openCaptureDevice (fallback empty) failed: ", e, " (", ts3_err(e), ")");
          }
        }
      }
    }

    std::vector<const char*> chan_ptrs;
    if (!cfg_.channel_path.empty()) {
      chan_ptrs.reserve(cfg_.channel_path.size() + 1);
      for (auto& p : cfg_.channel_path) chan_ptrs.push_back(p.c_str());
      chan_ptrs.push_back(nullptr);
    }

    const char** default_channel_array = chan_ptrs.empty() ? nullptr : chan_ptrs.data();
    err = ts3client_startConnection(
        sch_id_,
        cfg_.identity.c_str(),
        cfg_.host.c_str(),
        cfg_.port,
        cfg_.nickname.c_str(),
        default_channel_array,
        cfg_.channel_password.c_str(),
        cfg_.server_password.c_str());
    if (err != 0) {
      std::cerr << "ts3client_startConnection failed: " << err << " (" << ts3_err(err) << ")" << std::endl;
      ts3_print("WARNING: TS3 connection failed, continuing without TS3 connection");
      return true; // Continue without TS3 connection for development
    }

    ts3_print("TS3 connecting to ", cfg_.host, ":", cfg_.port, " as ", cfg_.nickname);
    return true;
  }

  void stop() {
    if (initialized_ && sch_id_) {
      ts3client_closeCaptureDevice(sch_id_);
      ts3client_closePlaybackDevice(sch_id_);
      ts3client_stopConnection(sch_id_, "");
      ts3client_destroyServerConnectionHandler(sch_id_);
    }
    if (initialized_) {
      ts3client_destroyClientLib();
    }
    initialized_ = false;
  }

 private:
  ClientUIFunctions ui_{};
  std::string pb_mode_;
  std::string pb_device_name_;
  std::string pb_device_id_;
  std::string cap_mode_;
  std::string cap_device_name_;
  std::string cap_device_id_;
  static Ts3Client* instance() {
    std::lock_guard<std::mutex> lk(mu_);
    return active_instance_;
  }

  static void onConnectStatusChangeEvent(uint64 serverConnectionHandlerID, int newStatus, unsigned int errorNumber) {
    if (errorNumber != 0) {
      ts3_print("TS3 status(", serverConnectionHandlerID, "): ", newStatus, " err=", errorNumber, " (", ts3_err(errorNumber), ")");
    } else {
      ts3_print("TS3 status(", serverConnectionHandlerID, "): ", newStatus);
    }

    auto* self = instance();
    if (!self) return;
    if (self->sch_id_ != serverConnectionHandlerID) return;

    if (newStatus == STATUS_CONNECTION_ESTABLISHED && self->cfg_.channel_id.has_value()) {
      anyID my_id = 0;
      unsigned int err = ts3client_getClientID(serverConnectionHandlerID, &my_id);
      if (err != 0) {
        std::cerr << "ts3client_getClientID failed: " << err << " (" << ts3_err(err) << ")" << std::endl;
        return;
      }
      const anyID ids[2] = {my_id, 0};
      err = ts3client_requestClientMove(serverConnectionHandlerID, ids, self->cfg_.channel_id.value(), self->cfg_.channel_password.c_str(), "");
      if (err != 0) {
        std::cerr << "ts3client_requestClientMove failed: " << err << " (" << ts3_err(err) << ")" << std::endl;
      }
    }
  }

  static void onTextMessageEvent(uint64 serverConnectionHandlerID, anyID targetMode, anyID toID, anyID fromID,
                                 const char* fromName, const char* fromUniqueIdentifier, const char* message) {
    (void)toID;
    (void)fromID;
    ts3_print(
        "TS3 msg(",
        serverConnectionHandlerID,
        ") mode=",
        targetMode,
        " from=",
        (fromName ? fromName : ""),
        " uid=",
        (fromUniqueIdentifier ? fromUniqueIdentifier : ""),
        ": ",
        (message ? message : ""));
  }

  static void onServerErrorEvent(uint64 serverConnectionHandlerID, const char* errorMessage, unsigned int error,
                                 const char* returnCode, const char* extraMessage) {
    ts3_print(
        "TS3 serverError(",
        serverConnectionHandlerID,
        ") error=",
        error,
        " (",
        ts3_err(error),
        ") msg=",
        (errorMessage ? errorMessage : ""),
        " returnCode=",
        (returnCode ? returnCode : ""),
        " extra=",
        (extraMessage ? extraMessage : ""));
  }

  static Ts3Config load_config() {
    Ts3Config c;
    c.host = get_env("TSBOT_TS3_HOST", "127.0.0.1");
    c.nickname = get_env("TSBOT_TS3_NICKNAME", "tsbot");
    c.identity = get_env("TSBOT_TS3_IDENTITY");
    c.identity_file = get_env("TSBOT_TS3_IDENTITY_FILE", "./logs/identity.txt");
    c.server_password = get_env("TSBOT_TS3_SERVER_PASSWORD");
    c.channel_password = get_env("TSBOT_TS3_CHANNEL_PASSWORD");
    c.resources_folder = get_env("TSBOT_TS3_RESOURCES", "./ts3sdk/bin/linux/amd64");
    c.log_folder = get_env("TSBOT_TS3_LOG", "./logs");

    if (auto port = parse_u64(get_env("TSBOT_TS3_PORT", "9987")); port.has_value()) {
      c.port = static_cast<unsigned int>(port.value());
    }

    const auto ch_id = parse_u64(get_env("TSBOT_TS3_CHANNEL_ID"));
    if (ch_id.has_value()) c.channel_id = ch_id;

    const std::string ch_path = get_env("TSBOT_TS3_CHANNEL_PATH");
    if (!ch_path.empty()) {
      std::string cur;
      for (char ch : ch_path) {
        if (ch == '/' || ch == '\\') {
          if (!cur.empty()) {
            c.channel_path.push_back(cur);
            cur.clear();
          }
          continue;
        }
        cur.push_back(ch);
      }
      if (!cur.empty()) c.channel_path.push_back(cur);
    }
    return c;
  }

  Ts3Config cfg_;
  uint64 sch_id_ = 0;
  bool initialized_ = false;

  static inline std::mutex mu_;
  static inline Ts3Client* active_instance_ = nullptr;
};

}  // namespace
#endif

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

#if defined(TSBOT_HAS_TS3_SDK)
  Ts3Client ts3;
  ts3.start();
#endif

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

#if defined(TSBOT_HAS_TS3_SDK)
  ts3.stop();
#endif
  return 0;
}
