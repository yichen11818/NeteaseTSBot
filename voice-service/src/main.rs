use std::collections::VecDeque;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::pin::Pin;
use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::{anyhow, Result};
use audiopus::coder::Encoder;
use futures::{FutureExt, StreamExt};
use serde::{Deserialize, Serialize};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, BufReader};
use tokio::sync::{broadcast, mpsc, watch, Mutex};
use tokio_stream::wrappers::{BroadcastStream, TcpListenerStream};
use tokio_util::sync::CancellationToken;
use tonic::{Request, Response, Status};
use tracing::{error, info, warn};

mod logger;

use tsclientlib::{Connection, DisconnectOptions, Identity, StreamItem};
use tsproto_packets::packets::{AudioData, CodecType, Direction, Flags, OutAudio, OutCommand, OutPacket, PacketType};
use tsclientlib::{events, MessageTarget};
use tsclientlib::ChannelId;

pub mod tsbot {
    pub mod voice {
        pub mod v1 {
            tonic::include_proto!("tsbot.voice.v1");
        }
    }
}

use tsbot::voice::v1 as voicev1;
use voicev1::voice_service_server::{VoiceService, VoiceServiceServer};

#[derive(Default)]
struct SharedStatus {
    state: i32,
    now_playing_title: String,
    now_playing_source_url: String,
    volume_percent: i32,
    fx_pan: f32,
    fx_width: f32,
    fx_swap_lr: bool,
    fx_bass_db: f32,
    fx_reverb_mix: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
struct PersistedVoiceState {
    volume_percent: i32,
    fx_pan: f32,
    fx_width: f32,
    fx_swap_lr: bool,
    fx_bass_db: f32,
    fx_reverb_mix: f32,
}

impl Default for PersistedVoiceState {
    fn default() -> Self {
        Self {
            volume_percent: 100,
            fx_pan: 0.0,
            fx_width: 1.0,
            fx_swap_lr: false,
            fx_bass_db: 0.0,
            fx_reverb_mix: 0.0,
        }
    }
}

impl PersistedVoiceState {
    fn from_status(st: &SharedStatus) -> Self {
        Self {
            volume_percent: st.volume_percent,
            fx_pan: st.fx_pan,
            fx_width: st.fx_width,
            fx_swap_lr: st.fx_swap_lr,
            fx_bass_db: st.fx_bass_db,
            fx_reverb_mix: st.fx_reverb_mix,
        }
    }
}

struct ReverbChannel {
    comb_bufs: [Vec<f32>; 2],
    comb_idx: [usize; 2],
    allpass_buf: Vec<f32>,
    allpass_idx: usize,
}

impl ReverbChannel {
    fn new(comb_lens: [usize; 2], allpass_len: usize) -> Self {
        Self {
            comb_bufs: [vec![0.0; comb_lens[0]], vec![0.0; comb_lens[1]]],
            comb_idx: [0, 0],
            allpass_buf: vec![0.0; allpass_len],
            allpass_idx: 0,
        }
    }

    fn process(&mut self, x: f32) -> f32 {
        let comb_feedback = 0.78f32;
        let mut s = 0.0f32;
        for i in 0..2 {
            let idx = self.comb_idx[i];
            let y = self.comb_bufs[i][idx];
            self.comb_bufs[i][idx] = x + y * comb_feedback;
            self.comb_idx[i] = (idx + 1) % self.comb_bufs[i].len();
            s += y;
        }
        s *= 0.5;

        let ap_feedback = 0.5f32;
        let idx = self.allpass_idx;
        let buf = self.allpass_buf[idx];
        let y = -s + buf;
        self.allpass_buf[idx] = s + buf * ap_feedback;
        self.allpass_idx = (idx + 1) % self.allpass_buf.len();
        y
    }
}

struct SimpleReverb {
    l: ReverbChannel,
    r: ReverbChannel,
}

impl SimpleReverb {
    fn new() -> Self {
        Self {
            l: ReverbChannel::new([1487, 1601], 556),
            r: ReverbChannel::new([1559, 1699], 579),
        }
    }

    fn process_stereo(&mut self, l: f32, r: f32, mix: f32) -> (f32, f32) {
        if mix <= 0.0001 {
            return (l, r);
        }
        let mix = mix.clamp(0.0, 1.0);
        let wet_gain = 0.28f32;
        let in_l = l;
        let in_r = r;
        let wet_l = self.l.process(in_l);
        let wet_r = self.r.process(in_r);
        (
            in_l * (1.0 - mix) + wet_l * (mix * wet_gain),
            in_r * (1.0 - mix) + wet_r * (mix * wet_gain),
        )
    }
}

struct PlaybackControl {
    cancel: CancellationToken,
    paused_tx: watch::Sender<bool>,
    handle: tokio::task::JoinHandle<()>,
}

struct AvatarUploadState {
    handle: tsclientlib::FiletransferHandle,
    local_path: PathBuf,
    md5_hex: String,
}

fn pick_avatar_file(dir: &Path) -> Option<PathBuf> {
    let mut files: Vec<PathBuf> = Vec::new();
    let rd = fs::read_dir(dir).ok()?;
    for e in rd.flatten() {
        let p = e.path();
        if !p.is_file() {
            continue;
        }
        let ext = p
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        if ext == "png" || ext == "jpg" || ext == "jpeg" || ext == "gif" {
            files.push(p);
        }
    }
    files.sort();
    files.into_iter().next()
}

fn md5_hex_of_file(path: &Path) -> Result<String> {
    let bs = fs::read(path).map_err(|e| anyhow!("read avatar file failed: {e}"))?;
    let digest = md5::compute(&bs);
    Ok(format!("{:x}", digest))
}

struct ChildKillOnDrop {
    child: Option<tokio::process::Child>,
}

impl ChildKillOnDrop {
    fn new(child: tokio::process::Child) -> Self {
        Self { child: Some(child) }
    }

    fn child_mut(&mut self) -> &mut tokio::process::Child {
        self.child.as_mut().expect("child missing")
    }
}

impl Drop for ChildKillOnDrop {
    fn drop(&mut self) {
        if let Some(child) = self.child.as_mut() {
            let _ = child.start_kill();
        }
    }
}

#[derive(Clone)]
struct VoiceServiceImpl {
    status: Arc<Mutex<SharedStatus>>,
    playback: Arc<Mutex<Option<PlaybackControl>>>,
    ts3_audio_tx: mpsc::Sender<OutPacket>,
    ts3_notice_tx: mpsc::Sender<(i32, String)>,
    ts3_cmd_tx: mpsc::Sender<OutCommand>,
    events_tx: broadcast::Sender<voicev1::Event>,
    persist_tx: mpsc::Sender<PersistedVoiceState>,
}

fn load_persisted_voice_state(path: &Path) -> Option<PersistedVoiceState> {
    let raw = fs::read_to_string(path).ok()?;
    let raw = raw.trim();
    if raw.is_empty() {
        return None;
    }
    serde_json::from_str::<PersistedVoiceState>(raw).ok()
}

fn now_unix_ms() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(d) => d.as_millis() as i64,
        Err(_) => 0,
    }
}

fn emit_log(events_tx: &broadcast::Sender<voicev1::Event>, level: i32, msg: impl Into<String>) {
    let _ = events_tx.send(voicev1::Event {
        unix_ms: now_unix_ms(),
        payload: Some(voicev1::event::Payload::Log(voicev1::LogEvent {
            level,
            message: msg.into(),
        })),
    });
}

fn emit_playback(
    events_tx: &broadcast::Sender<voicev1::Event>,
    ty: i32,
    title: impl Into<String>,
    source_url: impl Into<String>,
    detail: impl Into<String>,
) {
    let _ = events_tx.send(voicev1::Event {
        unix_ms: now_unix_ms(),
        payload: Some(voicev1::event::Payload::Playback(voicev1::PlaybackEvent {
            r#type: ty,
            title: title.into(),
            source_url: source_url.into(),
            detail: detail.into(),
        })),
    });
}

#[tonic::async_trait]
impl VoiceService for VoiceServiceImpl {
    async fn ping(
        &self,
        _req: Request<voicev1::Empty>,
    ) -> std::result::Result<Response<voicev1::PingResponse>, Status> {
        Ok(Response::new(voicev1::PingResponse {
            version: "0.1.0".to_string(),
        }))
    }

    async fn play(
        &self,
        req: Request<voicev1::PlayRequest>,
    ) -> std::result::Result<Response<voicev1::CommandResponse>, Status> {
        let r = req.into_inner();

        if !r.notice.is_empty() {
            let _ = self.ts3_notice_tx.try_send((2, r.notice.clone()));
        }

        {
            let mut st = self.status.lock().await;
            st.now_playing_title = r.title.clone();
            st.now_playing_source_url = r.source_url.clone();
            st.state = 2; // STATE_PLAYING
        }

        // PlaybackEvent.Type: STARTED=1
        emit_playback(&self.events_tx, 1, r.title.clone(), r.source_url.clone(), "");

        self.stop_internal().await;

        let (paused_tx, paused_rx) = watch::channel(false);
        let cancel = CancellationToken::new();

        let status = self.status.clone();
        let tx = self.ts3_audio_tx.clone();
        let events_tx = self.events_tx.clone();
        let title = r.title.clone();
        let source_url = r.source_url;
        let cancel_child = cancel.clone();

        let handle = tokio::spawn(async move {
            let r = playback_loop(source_url.clone(), tx, paused_rx, cancel_child, status).await;
            match r {
                Ok(()) => {
                    // PlaybackEvent.Type: FINISHED=2
                    emit_playback(&events_tx, 2, title, source_url, "");
                }
                Err(e) => {
                    error!(%e, "playback loop failed");
                    // PlaybackEvent.Type: ERROR=3
                    emit_playback(&events_tx, 3, title, source_url, format!("{e}"));
                }
            }
        });

        let mut pb = self.playback.lock().await;
        *pb = Some(PlaybackControl {
            cancel,
            paused_tx,
            handle,
        });

        Ok(Response::new(voicev1::CommandResponse {
            ok: true,
            message: "accepted".to_string(),
        }))
    }

    async fn pause(
        &self,
        _req: Request<voicev1::Empty>,
    ) -> std::result::Result<Response<voicev1::CommandResponse>, Status> {
        {
            let mut st = self.status.lock().await;
            if st.state == 2 {
                st.state = 3; // STATE_PAUSED
            }
        }

        if let Some(pb) = self.playback.lock().await.as_ref() {
            let _ = pb.paused_tx.send(true);
        }

        // LogEvent.Level: INFO=2
        emit_log(&self.events_tx, 2, "paused");

        Ok(Response::new(voicev1::CommandResponse {
            ok: true,
            message: "ok".to_string(),
        }))
    }

    async fn set_client_description(
        &self,
        req: Request<voicev1::SetClientDescriptionRequest>,
    ) -> std::result::Result<Response<voicev1::CommandResponse>, Status> {
        let r = req.into_inner();
        let desc = r.description;
        if desc.len() > 700 {
            return Ok(Response::new(voicev1::CommandResponse {
                ok: false,
                message: "description too long".to_string(),
            }));
        }

        // Send a raw TS3 command: clientupdate client_description=...
        let mut cmd = OutCommand::new(Direction::C2S, Flags::empty(), PacketType::Command, "clientupdate");
        cmd.write_arg("client_description", &desc);

        self.ts3_cmd_tx
            .send(cmd)
            .await
            .map_err(|e| Status::internal(format!("send failed: {e}")))?;

        Ok(Response::new(voicev1::CommandResponse {
            ok: true,
            message: "ok".to_string(),
        }))
    }

    async fn resume(
        &self,
        _req: Request<voicev1::Empty>,
    ) -> std::result::Result<Response<voicev1::CommandResponse>, Status> {
        {
            let mut st = self.status.lock().await;
            if st.state == 3 {
                st.state = 2; // STATE_PLAYING
            }
        }

        if let Some(pb) = self.playback.lock().await.as_ref() {
            let _ = pb.paused_tx.send(false);
        }

        // LogEvent.Level: INFO=2
        emit_log(&self.events_tx, 2, "resumed");

        Ok(Response::new(voicev1::CommandResponse {
            ok: true,
            message: "ok".to_string(),
        }))
    }

    async fn stop(
        &self,
        _req: Request<voicev1::Empty>,
    ) -> std::result::Result<Response<voicev1::CommandResponse>, Status> {
        self.stop_internal().await;

        {
            let mut st = self.status.lock().await;
            st.state = 1; // STATE_IDLE
            st.now_playing_title.clear();
            st.now_playing_source_url.clear();
        }

        // LogEvent.Level: INFO=2
        emit_log(&self.events_tx, 2, "stopped");

        Ok(Response::new(voicev1::CommandResponse {
            ok: true,
            message: "ok".to_string(),
        }))
    }

    async fn skip(
        &self,
        _req: Request<voicev1::Empty>,
    ) -> std::result::Result<Response<voicev1::CommandResponse>, Status> {
        self.stop(_req).await
    }

    async fn send_notice(
        &self,
        req: Request<voicev1::NoticeRequest>,
    ) -> std::result::Result<Response<voicev1::CommandResponse>, Status> {
        let r = req.into_inner();
        if !r.message.is_empty() {
            let mode = if r.target_mode == 3 { 3 } else { 2 };
            let _ = self.ts3_notice_tx.try_send((mode, r.message));
        }
        Ok(Response::new(voicev1::CommandResponse {
            ok: true,
            message: "ok".to_string(),
        }))
    }

    async fn set_volume(
        &self,
        req: Request<voicev1::SetVolumeRequest>,
    ) -> std::result::Result<Response<voicev1::CommandResponse>, Status> {
        let v = req.into_inner().volume_percent.clamp(0, 200);
        let snapshot = {
            let mut st = self.status.lock().await;
            st.volume_percent = v;
            PersistedVoiceState::from_status(&st)
        };
        let _ = self.persist_tx.try_send(snapshot);

        Ok(Response::new(voicev1::CommandResponse {
            ok: true,
            message: "ok".to_string(),
        }))
    }

    async fn get_status(
        &self,
        _req: Request<voicev1::Empty>,
    ) -> std::result::Result<Response<voicev1::StatusResponse>, Status> {
        let st = self.status.lock().await;
        Ok(Response::new(voicev1::StatusResponse {
            state: st.state,
            now_playing_title: st.now_playing_title.clone(),
            now_playing_source_url: st.now_playing_source_url.clone(),
            volume_percent: st.volume_percent,
        }))
    }

    async fn set_audio_fx(
        &self,
        req: Request<voicev1::SetAudioFxRequest>,
    ) -> std::result::Result<Response<voicev1::CommandResponse>, Status> {
        let r = req.into_inner();
        let snapshot = {
            let mut st = self.status.lock().await;

            if let Some(p) = r.pan {
                st.fx_pan = p.clamp(-1.0, 1.0);
            }
            if let Some(w) = r.width {
                st.fx_width = w.clamp(0.0, 3.0);
            }
            if let Some(s) = r.swap_lr {
                st.fx_swap_lr = s;
            }

            if let Some(b) = r.bass_db {
                st.fx_bass_db = b.clamp(0.0, 18.0);
            }
            if let Some(m) = r.reverb_mix {
                st.fx_reverb_mix = m.clamp(0.0, 1.0);
            }

            PersistedVoiceState::from_status(&st)
        };
        let _ = self.persist_tx.try_send(snapshot);

        Ok(Response::new(voicev1::CommandResponse {
            ok: true,
            message: "ok".to_string(),
        }))
    }

    async fn get_audio_fx(
        &self,
        _req: Request<voicev1::Empty>,
    ) -> std::result::Result<Response<voicev1::AudioFxResponse>, Status> {
        let st = self.status.lock().await;
        Ok(Response::new(voicev1::AudioFxResponse {
            pan: st.fx_pan,
            width: st.fx_width,
            swap_lr: st.fx_swap_lr,
            bass_db: st.fx_bass_db,
            reverb_mix: st.fx_reverb_mix,
        }))
    }

    async fn subscribe_events(
        &self,
        req: Request<voicev1::SubscribeRequest>,
    ) -> std::result::Result<Response<Self::SubscribeEventsStream>, Status> {
        let cfg = req.into_inner();
        let rx = self.events_tx.subscribe();
        let stream = BroadcastStream::new(rx).filter_map(move |r| {
            let include_chat = cfg.include_chat;
            let include_playback = cfg.include_playback;
            let include_log = cfg.include_log;
            async move {
                match r {
                    Ok(ev) => {
                        let ok = match ev.payload {
                            Some(voicev1::event::Payload::Chat(_)) => include_chat,
                            Some(voicev1::event::Payload::Playback(_)) => include_playback,
                            Some(voicev1::event::Payload::Log(_)) => include_log,
                            None => false,
                        };
                        if ok { Some(Ok(ev)) } else { None }
                    }
                    Err(_) => None,
                }
            }
        });
        Ok(Response::new(Box::pin(stream) as Self::SubscribeEventsStream))
    }

    type SubscribeEventsStream = std::pin::Pin<Box<dyn tokio_stream::Stream<Item = std::result::Result<voicev1::Event, Status>> + Send>>;
}

impl VoiceServiceImpl {
    async fn stop_internal(&self) {
        let mut pb = self.playback.lock().await;
        if let Some(p) = pb.take() {
            p.cancel.cancel();
            let abort_handle = p.handle.abort_handle();
            let join = p.handle;
            let r = tokio::time::timeout(Duration::from_secs(2), join).await;
            if r.is_err() {
                abort_handle.abort();
            }
        }
    }
}

fn get_env(key: &str, def: &str) -> String {
    match env::var(key) {
        Ok(v) => {
            let v = v.trim();
            if !v.is_empty() {
                v.to_string()
            } else {
                def.to_string()
            }
        }
        Err(_) => def.to_string(),
    }
}

fn resolve_repo_relative(path: &str) -> PathBuf {
    let p = Path::new(path);
    if p.is_absolute() {
        return p.to_path_buf();
    }

    let rel = PathBuf::from(path);
    let mut cwd = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let mut last;
    loop {
        last = cwd.clone();
        if cwd.join(".git").exists() {
            return cwd.join(&rel);
        }

        if !cwd.pop() {
            break;
        }
    }

    last.join(rel)
}

async fn ts3_actor(
    mut audio_rx: mpsc::Receiver<OutPacket>,
    mut notice_rx: mpsc::Receiver<(i32, String)>,
    mut cmd_rx: mpsc::Receiver<OutCommand>,
    events_tx: broadcast::Sender<voicev1::Event>,
    shutdown_token: CancellationToken,
) -> Result<()> {
    let host = get_env("TSBOT_TS3_HOST", "127.0.0.1");
    let port = get_env("TSBOT_TS3_PORT", "9987");
    let port = port.trim_start_matches(':').to_string();
    let nickname = get_env("TSBOT_TS3_NICKNAME", "tsbot");
    let server_password = get_env("TSBOT_TS3_SERVER_PASSWORD", "");
    let channel_password = get_env("TSBOT_TS3_CHANNEL_PASSWORD", "");
    let channel_path = get_env("TSBOT_TS3_CHANNEL_PATH", "");
    let channel_id = get_env("TSBOT_TS3_CHANNEL_ID", "");
    let identity_str = get_env("TSBOT_TS3_IDENTITY", "");
    let identity_file = resolve_repo_relative(&get_env("TSBOT_TS3_IDENTITY_FILE", "./logs/identity.json"));
    let avatar_dir = get_env("TSBOT_TS3_AVATAR_DIR", "");
    let avatar_dir = avatar_dir.trim();
    let avatar_dir = if avatar_dir.is_empty() {
        None
    } else {
        Some(resolve_repo_relative(avatar_dir))
    };

    let address = format!("{}:{}", host, port);

    let mut opts = Connection::build(address)
        .name(nickname)
        .input_muted(false)
        .output_muted(false)
        .input_hardware_enabled(true)
        .output_hardware_enabled(true);

    if !server_password.is_empty() {
        opts = opts.password(server_password);
    }

    if !channel_password.is_empty() {
        opts = opts.channel_password(channel_password);
    }

    if !channel_id.is_empty() {
        if let Ok(id) = channel_id.parse::<u64>() {
            opts = opts.channel_id(tsclientlib::ChannelId(id));
        }
    } else if !channel_path.is_empty() {
        opts = opts.channel(channel_path);
    }

    if !identity_str.is_empty() {
        if let Ok(id) = Identity::new_from_str(&identity_str) {
            opts = opts.identity(id);
        }
    } else {
        let mut ident: Option<Identity> = None;

        if let Ok(s) = fs::read_to_string(&identity_file) {
            let s = s.trim();
            if !s.is_empty() {
                // Prefer JSON-serialized identity for stability.
                if let Ok(id) = serde_json::from_str::<Identity>(s) {
                    ident = Some(id);
                } else if let Ok(id) = Identity::new_from_str(s) {
                    ident = Some(id);
                }
            }
        }

        if ident.is_none() {
            if let Some(parent) = identity_file.parent() {
                let _ = fs::create_dir_all(parent);
            }
            let id = Identity::create();
            let _ = fs::write(&identity_file, serde_json::to_string(&id).unwrap_or_default());
            ident = Some(id);
        }

        if let Some(id) = ident {
            opts = opts.identity(id);
        }
    }

    let mut out_buf: VecDeque<OutPacket> = VecDeque::with_capacity(400);
    let mut avatar_set_done = false;
    let mut backoff = Duration::from_secs(1);
    let max_backoff = Duration::from_secs(60);

    'outer: loop {
        if shutdown_token.is_cancelled() {
            break;
        }

        let mut connect_handle = tokio::task::spawn_blocking({
            let o = opts.clone();
            move || -> anyhow::Result<Connection> { Ok(o.connect()?) }
        });

        let mut con = match tokio::select! {
            res = &mut connect_handle => {
                match res {
                    Ok(r) => r,
                    Err(e) => Err(anyhow!("ts3 connect join failed: {e}")),
                }
            }
            _ = shutdown_token.cancelled() => {
                connect_handle.abort();
                break 'outer;
            }
        } {
            Ok(c) => {
                backoff = Duration::from_secs(1);
                out_buf.clear();
                c
            }
            Err(e) => {
                let msg = format!("{e}");
                emit_log(&events_tx, 3, format!("ts3 connect failed: {msg}"));
                let wait = if msg.contains("ClientTooManyClonesConnected") {
                    std::cmp::max(backoff, Duration::from_secs(30))
                } else {
                    backoff
                };
                tokio::select! {
                    _ = tokio::time::sleep(wait) => {}
                    _ = shutdown_token.cancelled() => { break 'outer; }
                }
                backoff = std::cmp::min(backoff.saturating_mul(2), max_backoff);
                continue;
            }
        };

        let mut logged_connected = false;
        let mut last_muted_warn = Instant::now() - Duration::from_secs(60);
        let mut avatar_upload: Option<AvatarUploadState> = None;
        let mut conn_err: Option<String> = None;

        let mut send_last_tick = Instant::now();
        let mut send_jitter_max_ms: u128 = 0;
        let mut out_buf_max: usize = 0;
        let mut out_buf_drops: u64 = 0;
        let mut send_audio_errs: u64 = 0;
        let mut diag_next = Instant::now() + Duration::from_secs(5);

        let mut event_tick = tokio::time::interval(std::time::Duration::from_millis(50));
        let mut send_tick = tokio::time::interval(std::time::Duration::from_millis(20));

        'inner: loop {
            tokio::select! {
                _ = shutdown_token.cancelled() => {
                    if let Err(e) = con.disconnect(DisconnectOptions::new()) {
                        emit_log(&events_tx, 3, format!("ts3 disconnect failed: {e}"));
                    }
                    let drain = async {
                        con.events()
                            .for_each(|_| futures::future::ready(()))
                            .await;
                    };
                    let _ = tokio::time::timeout(Duration::from_secs(2), drain).await;
                    conn_err = None;
                    break 'inner;
                }

                _ = event_tick.tick() => {
                    loop {
                        let next_item = {
                            let mut evs = con.events();
                            evs.next().now_or_never()
                        };

                        match next_item {
                            Some(Some(Ok(StreamItem::BookEvents(evts)))) => {
                                if !logged_connected {
                                    logged_connected = true;
                                    emit_log(&events_tx, 2, "ts3 connected");

                                    if !avatar_set_done {
                                        if let Some(dir) = avatar_dir.as_ref() {
                                            if dir.is_dir() {
                                                if let Some(p) = pick_avatar_file(dir) {
                                                    match fs::metadata(&p) {
                                                        Ok(md) => {
                                                            let size = md.len();
                                                            match md5_hex_of_file(&p) {
                                                                Ok(md5_hex) => {
                                                                    let remote_path = format!("/avatar_{}", md5_hex);
                                                                    match con.upload_file(ChannelId(0), &remote_path, None, size, true, false) {
                                                                        Ok(h) => {
                                                                            avatar_upload = Some(AvatarUploadState { handle: h, local_path: p.clone(), md5_hex: md5_hex.clone() });
                                                                            emit_log(&events_tx, 2, format!("avatar upload started: {} -> {}", p.display(), remote_path));
                                                                        }
                                                                        Err(e) => {
                                                                            emit_log(&events_tx, 3, format!("avatar upload start failed: {e}"));
                                                                        }
                                                                    }
                                                                }
                                                                Err(e) => {
                                                                    emit_log(&events_tx, 3, format!("avatar md5 failed: {e}"));
                                                                }
                                                            }
                                                        }
                                                        Err(e) => {
                                                            emit_log(&events_tx, 3, format!("avatar stat failed: {e}"));
                                                        }
                                                    }
                                                } else {
                                                    emit_log(&events_tx, 3, format!("avatar dir has no supported images: {}", dir.display()));
                                                }
                                            } else {
                                                emit_log(&events_tx, 3, format!("avatar dir not found: {}", dir.display()));
                                            }
                                        }
                                    }
                                }

                                for e in evts {
                                    if let events::Event::Message { target, invoker, message } = e {
                                        let mode = match target {
                                            MessageTarget::Client(_) | MessageTarget::Poke(_) => 1,
                                            MessageTarget::Channel => 2,
                                            MessageTarget::Server => 3,
                                        };

                                        let uid = invoker
                                            .uid
                                            .as_ref()
                                            .map(|u| u.as_ref().to_string())
                                            .unwrap_or_default();

                                        let mut avatar_hash = String::new();
                                        let mut description = String::new();
                                        if !uid.is_empty() {
                                            if let Ok(st) = con.get_state() {
                                                for c in st.clients.values() {
                                                    if let Some(cuid) = c.uid.as_ref() {
                                                        if cuid.to_string() == uid {
                                                            avatar_hash = c.avatar_hash.clone();
                                                            description = c.description.clone();
                                                            break;
                                                        }
                                                    }
                                                }
                                            }
                                        }

                                        let _ = events_tx.send(voicev1::Event {
                                            unix_ms: now_unix_ms(),
                                            payload: Some(voicev1::event::Payload::Chat(voicev1::ChatEvent {
                                                target_mode: mode,
                                                invoker_unique_id: uid,
                                                invoker_name: invoker.name,
                                                message,
                                                invoker_avatar_hash: avatar_hash,
                                                invoker_description: description,
                                            })),
                                        });
                                    }
                                }
                            }

                            Some(Some(Ok(StreamItem::FileUpload(h, r)))) => {
                                if let Some(st) = avatar_upload.as_ref() {
                                    if st.handle.0 == h.0 {
                                        let local_path = st.local_path.clone();
                                        let md5_hex = st.md5_hex.clone();

                                        match tokio::fs::File::open(&local_path).await {
                                            Ok(mut file) => {
                                                let mut stream = r.stream;
                                                if let Err(e) = tokio::io::copy(&mut file, &mut stream).await {
                                                    emit_log(&events_tx, 3, format!("upload avatar failed: {e}"));
                                                    avatar_upload = None;
                                                    continue;
                                                }

                                                let mut cmd = OutCommand::new(
                                                    Direction::C2S,
                                                    Flags::empty(),
                                                    PacketType::Command,
                                                    "clientupdate",
                                                );
                                                cmd.write_arg("client_flag_avatar", &md5_hex);
                                                if let Ok(client) = con.get_tsproto_client_mut() {
                                                    if let Err(e) = client.send_packet(cmd.into_packet()) {
                                                        emit_log(&events_tx, 3, format!("set avatar flag failed: {e}"));
                                                        avatar_upload = None;
                                                        continue;
                                                    }
                                                }

                                                emit_log(&events_tx, 2, format!("avatar updated: {}", md5_hex));
                                                avatar_set_done = true;
                                                avatar_upload = None;
                                            }
                                            Err(e) => {
                                                emit_log(&events_tx, 3, format!("open avatar file failed: {e}"));
                                                avatar_upload = None;
                                            }
                                        }
                                    }
                                }
                            }

                            Some(Some(Ok(StreamItem::FiletransferFailed(h, e)))) => {
                                if let Some(st) = avatar_upload.as_ref() {
                                    if st.handle.0 == h.0 {
                                        emit_log(&events_tx, 3, format!("avatar filetransfer failed: {e}"));
                                        avatar_upload = None;
                                    }
                                }
                            }

                            Some(Some(Ok(_))) => {}

                            Some(Some(Err(e))) => {
                                emit_log(&events_tx, 4, format!("ts3 error: {e}"));
                                conn_err = Some(format!("ts3 event error: {e}"));
                                break;
                            }
                            Some(None) => {
                                emit_log(&events_tx, 4, "ts3 disconnected");
                                conn_err = Some("ts3 disconnected".to_string());
                                break;
                            }
                            None => break,
                        }
                    }

                    if conn_err.is_some() {
                        break 'inner;
                    }
                }

                _ = send_tick.tick() => {
                    let now = Instant::now();
                    let dt = now.duration_since(send_last_tick);
                    send_last_tick = now;
                    let dt_ms = dt.as_millis();
                    if dt_ms > send_jitter_max_ms {
                        send_jitter_max_ms = dt_ms;
                    }
                    if out_buf.len() > out_buf_max {
                        out_buf_max = out_buf.len();
                    }

                    if let Some(pkt) = out_buf.pop_front() {
                        if !con.can_send_audio() {
                            if last_muted_warn.elapsed() >= Duration::from_secs(3) {
                                last_muted_warn = Instant::now();
                                emit_log(
                                    &events_tx,
                                    3,
                                    "cannot send audio (muted / insufficient talk power / away / input muted)".to_string(),
                                );
                            }
                        } else if let Err(e) = con.send_audio(pkt) {
                            send_audio_errs += 1;
                            emit_log(
                                &events_tx,
                                3,
                                format!("send_audio failed (errs={}): {e}", send_audio_errs),
                            );
                            conn_err = Some(format!("send_audio failed: {e}"));
                            break 'inner;
                        }
                    }

                    if now >= diag_next {
                        diag_next = now + Duration::from_secs(5);
                        let msg = format!(
                            "audio_send_diag: out_buf_max={} drops={} send_jitter_max_ms={} send_audio_errs={}",
                            out_buf_max, out_buf_drops, send_jitter_max_ms, send_audio_errs
                        );
                        emit_log(&events_tx, 2, msg.clone());
                        info!("{msg}");
                        out_buf_max = out_buf.len();
                        send_jitter_max_ms = 0;
                        send_audio_errs = 0;
                    }
                }

                msg = notice_rx.recv() => {
                    if let Some((mode, text)) = msg {
                        let target_mode = if mode == 3 { 3 } else { 2 };
                        let mut cmd = OutCommand::new(Direction::C2S, Flags::empty(), PacketType::Command, "sendtextmessage");
                        cmd.write_arg("targetmode", &target_mode);
                        cmd.write_arg("msg", &text);
                        if let Ok(client) = con.get_tsproto_client_mut() {
                            if let Err(e) = client.send_packet(cmd.into_packet()) {
                                conn_err = Some(format!("sendtextmessage failed: {e}"));
                                break 'inner;
                            }
                        }
                    } else {
                        break 'outer;
                    }
                }

                cmd = cmd_rx.recv() => {
                    if let Some(c) = cmd {
                        if let Ok(client) = con.get_tsproto_client_mut() {
                            if let Err(e) = client.send_packet(c.into_packet()) {
                                conn_err = Some(format!("send_packet failed: {e}"));
                                break 'inner;
                            }
                        }
                    } else {
                        break 'outer;
                    }
                }

                pkt = audio_rx.recv() => {
                    if let Some(p) = pkt {
                        if out_buf.len() >= 800 {
                            out_buf.pop_front();
                            out_buf_drops += 1;
                        }
                        out_buf.push_back(p);
                    } else {
                        break 'outer;
                    }
                }
            }
        }

        if send_audio_errs > 0 {
            emit_log(
                &events_tx,
                3,
                format!("audio_send_errs_total: {}", send_audio_errs),
            );
        }

        if let Err(e) = con.disconnect(DisconnectOptions::new()) {
            emit_log(&events_tx, 3, format!("ts3 disconnect failed: {e}"));
        }

        let drain = async {
            con.events().for_each(|_| futures::future::ready(())).await;
        };
        let _ = tokio::time::timeout(Duration::from_millis(500), drain).await;

        if shutdown_token.is_cancelled() {
            break;
        }

        let mut wait = backoff;
        if let Some(msg) = conn_err {
            if msg.contains("ClientTooManyClonesConnected") {
                wait = std::cmp::max(wait, Duration::from_secs(30));
            }
            emit_log(&events_tx, 3, format!("ts3 connection lost: {msg}; retry in {:?}", wait));
        } else {
            emit_log(&events_tx, 3, format!("ts3 disconnected; retry in {:?}", wait));
        }

        tokio::select! {
            _ = tokio::time::sleep(wait) => {}
            _ = shutdown_token.cancelled() => { break; }
        }

        backoff = std::cmp::min(backoff.saturating_mul(2), max_backoff);
    }

    Ok(())
}

async fn playback_loop(
    source_url: String,
    ts3_audio_tx: mpsc::Sender<OutPacket>,
    mut paused_rx: watch::Receiver<bool>,
    cancel: CancellationToken,
    status: Arc<Mutex<SharedStatus>>,
) -> Result<()> {
    let playback_started = Instant::now();
    info!(source_url = %source_url, "playback starting");

    let child = tokio::process::Command::new("ffmpeg")
        .arg("-nostdin")
        .arg("-loglevel")
        .arg("error")
        .arg("-reconnect")
        .arg("1")
        .arg("-reconnect_streamed")
        .arg("1")
        .arg("-reconnect_delay_max")
        .arg("5")
        .arg("-rw_timeout")
        .arg("15000000")
        .arg("-i")
        .arg(&source_url)
        .arg("-f")
        .arg("s16le")
        .arg("-ar")
        .arg("48000")
        .arg("-ac")
        .arg("2")
        .arg("pipe:1")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| anyhow!("failed to start ffmpeg: {e}"))?;

    let mut child = ChildKillOnDrop::new(child);

    if let Some(stderr) = child.child_mut().stderr.take() {
        let src = source_url.clone();
        tokio::spawn(async move {
            let mut lines = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                info!(source_url = %src, "ffmpeg: {line}");
            }
        });
    }

    let mut stdout = child
        .child_mut()
        .stdout
        .take()
        .ok_or_else(|| anyhow!("ffmpeg stdout missing"))?;

    // Encode/send loop must keep a stable 20ms cadence to prevent TS3 jitter buffer underruns.
    // We decouple ffmpeg reads from the send cadence via a small PCM frame queue.
    let (pcm_tx, mut pcm_rx) = mpsc::channel::<Vec<u8>>(50);

    let encoder = Encoder::new(
        audiopus::SampleRate::Hz48000,
        audiopus::Channels::Stereo,
        audiopus::Application::Audio,
    )
    .map_err(|e| anyhow!("opus encoder init failed: {e}"))?;

    let frame_samples_per_channel = 48000 / 50;
    let channels = 2usize;
    let bytes_per_sample = 2usize;
    let frame_bytes = frame_samples_per_channel * channels * bytes_per_sample;
    let frame_duration = Duration::from_millis(20);

    let mut pcm = vec![0u8; frame_bytes];
    let mut float_buf = vec![0f32; frame_samples_per_channel * channels];
    let mut opus_out = [0u8; 1275];

    let mut reverb = SimpleReverb::new();
    let bass_cutoff_hz: f32 = 150.0;
    let fs: f32 = 48000.0;
    let bass_alpha: f32 = (2.0 * std::f32::consts::PI * bass_cutoff_hz)
        / (fs + 2.0 * std::f32::consts::PI * bass_cutoff_hz);
    let mut bass_lp_l: f32 = 0.0;
    let mut bass_lp_r: f32 = 0.0;

    // Reader task: continuously read PCM frames from ffmpeg.
    // On EOF or error, it will stop sending and close the channel.
    let reader_cancel = cancel.clone();
    let reader_src = source_url.clone();
    tokio::spawn(async move {
        let mut buf = vec![0u8; frame_bytes];
        loop {
            if reader_cancel.is_cancelled() {
                break;
            }
            let t0 = Instant::now();
            if stdout.read_exact(&mut buf).await.is_err() {
                break;
            }
            let dt = t0.elapsed();
            if dt >= Duration::from_millis(200) {
                warn!(source_url = %reader_src, read_ms = %dt.as_millis(), "ffmpeg pcm read stalled");
            }
            if pcm_tx.send(buf.clone()).await.is_err() {
                break;
            }
        }
    });

    let mut ticker = tokio::time::interval(frame_duration);
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    let mut underruns_total: u64 = 0;
    let mut underruns_window: u64 = 0;
    let mut underruns_consecutive: u64 = 0;
    let mut logged_first_pcm = false;

    let mut pcm_buf: VecDeque<Vec<u8>> = VecDeque::new();

    let prebuffer_target: usize = 5;
    let mut prebuffering = true;

    let mut last_tick = Instant::now();
    let mut tick_jitter_max_ms: u128 = 0;
    let mut clipped_samples: u64 = 0;
    let mut max_abs_sample: f32 = 0.0;
    let mut diag_next = Instant::now() + Duration::from_secs(5);

    let fade_total_samples_per_channel: usize = 48000 / 1000 * 80;
    let mut fade_pos_samples_per_channel: usize = 0;

    'main: loop {
        if cancel.is_cancelled() {
            break;
        }

        while *paused_rx.borrow() {
            tokio::select! {
                _ = cancel.cancelled() => { break 'main; }
                r = paused_rx.changed() => {
                    if r.is_err() {
                        break 'main;
                    }
                }
            }
        }

        tokio::select! {
            _ = cancel.cancelled() => { break; }
            _ = ticker.tick() => {}
        }

        while let Ok(frame) = pcm_rx.try_recv() {
            if frame.len() == frame_bytes {
                pcm_buf.push_back(frame);
            }
        }

        if !logged_first_pcm {
            if !pcm_buf.is_empty() {
                logged_first_pcm = true;
                info!(source_url = %source_url, first_pcm_ms = %playback_started.elapsed().as_millis(), "first pcm frame received");
            } else if playback_started.elapsed() >= Duration::from_secs(5) {
                return Err(anyhow!("no pcm received from ffmpeg"));
            }
        }

        if prebuffering {
            prebuffering = pcm_buf.len() < prebuffer_target;
        }

        let now = Instant::now();
        let dt = now.duration_since(last_tick);
        last_tick = now;
        let dt_ms = dt.as_millis();
        if dt_ms > tick_jitter_max_ms {
            tick_jitter_max_ms = dt_ms;
        }

        // Prefer real PCM frame; fall back to silence to keep cadence stable.
        // Allow a tiny wait to reduce false underruns when the PCM frame arrives slightly after the tick.
        let mut got_real_frame = false;
        if !prebuffering {
            if let Some(frame) = pcm_buf.pop_front() {
                if frame.len() == frame_bytes {
                    pcm.copy_from_slice(&frame);
                    got_real_frame = true;
                }
            } else {
                match tokio::time::timeout(Duration::from_millis(3), pcm_rx.recv()).await {
                    Ok(Some(frame)) => {
                        if frame.len() == frame_bytes {
                            pcm.copy_from_slice(&frame);
                            got_real_frame = true;
                        }
                    }
                    Ok(None) => {
                        // ffmpeg finished / failed. Stop playback.
                        break;
                    }
                    Err(_) => {}
                }
            }
        }

        if got_real_frame {
            underruns_consecutive = 0;
        } else {
            pcm.fill(0);
            underruns_total += 1;
            underruns_window += 1;
            underruns_consecutive += 1;
        }

        // If we keep sending silence for too long, treat it as a playback failure.
        // The backend will auto-skip/delete on Playback ERROR.
        if logged_first_pcm && underruns_consecutive >= 150 {
            return Err(anyhow!(
                "sustained pcm underrun ({} frames, {} ms)",
                underruns_consecutive,
                underruns_consecutive * 20
            ));
        }

        if underruns_total > 0 && underruns_total % 50 == 0 {
            info!(underruns_total = %underruns_total, "playback underrun (sending silence frames to keep cadence)");
        }

        let (vol, fx_pan, fx_width, fx_swap_lr, fx_bass_db, fx_reverb_mix) = {
            let st = status.lock().await;
            let r = (st.volume_percent as f32 / 100.0).clamp(0.0, 2.0);
            let vol = if r <= 1.0 { r.powf(1.6) } else { r };
            (
                vol,
                st.fx_pan.clamp(-1.0, 1.0),
                st.fx_width.clamp(0.0, 3.0),
                st.fx_swap_lr,
                st.fx_bass_db.clamp(0.0, 18.0),
                st.fx_reverb_mix.clamp(0.0, 1.0),
            )
        };

        for i in 0..(frame_samples_per_channel * channels) {
            let lo = pcm[i * 2];
            let hi = pcm[i * 2 + 1];
            let s = i16::from_le_bytes([lo, hi]) as f32;
            let v = (s / 32768.0) * vol;
            float_buf[i] = v;
        }

        if got_real_frame && fade_pos_samples_per_channel < fade_total_samples_per_channel {
            let denom = fade_total_samples_per_channel as f32;
            for i in 0..frame_samples_per_channel {
                let s = fade_pos_samples_per_channel + i;
                let g = ((s as f32) / denom).clamp(0.0, 1.0);
                let idx = i * 2;
                float_buf[idx] *= g;
                float_buf[idx + 1] *= g;
            }
            fade_pos_samples_per_channel = (fade_pos_samples_per_channel + frame_samples_per_channel)
                .min(fade_total_samples_per_channel);
        }

        let bass_gain = 10.0_f32.powf(fx_bass_db / 20.0);
        if (bass_gain - 1.0).abs() > 0.0001 || fx_reverb_mix > 0.0001 {
            for i in 0..frame_samples_per_channel {
                let idx = i * 2;
                let mut l = float_buf[idx];
                let mut r = float_buf[idx + 1];

                if (bass_gain - 1.0).abs() > 0.0001 {
                    bass_lp_l += bass_alpha * (l - bass_lp_l);
                    bass_lp_r += bass_alpha * (r - bass_lp_r);
                    let low_l = bass_lp_l;
                    let low_r = bass_lp_r;
                    l = (l - low_l) + low_l * bass_gain;
                    r = (r - low_r) + low_r * bass_gain;
                }

                let (l2, r2) = reverb.process_stereo(l, r, fx_reverb_mix);
                float_buf[idx] = l2;
                float_buf[idx + 1] = r2;
            }
        }

        // Apply FX on interleaved stereo: swap, width (mid/side), then pan (balance).
        // Note: pan here is implemented as a simple balance control to keep center gain at 1.0.
        if fx_swap_lr || (fx_width - 1.0).abs() > 0.0001 || fx_pan.abs() > 0.0001 {
            let pan = fx_pan;
            let (lg, rg) = if pan >= 0.0 {
                ((1.0 - pan).clamp(0.0, 1.0), 1.0)
            } else {
                (1.0, (1.0 + pan).clamp(0.0, 1.0))
            };
            for i in 0..frame_samples_per_channel {
                let idx = i * 2;
                let mut l = float_buf[idx];
                let mut r = float_buf[idx + 1];
                if fx_swap_lr {
                    std::mem::swap(&mut l, &mut r);
                }
                if (fx_width - 1.0).abs() > 0.0001 {
                    let m = 0.5 * (l + r);
                    let s = 0.5 * (l - r) * fx_width;
                    l = m + s;
                    r = m - s;
                }
                l *= lg;
                r *= rg;
                float_buf[idx] = l;
                float_buf[idx + 1] = r;

                let a_l = l.abs();
                let a_r = r.abs();
                let a = if a_l > a_r { a_l } else { a_r };
                if a > max_abs_sample {
                    max_abs_sample = a;
                }
                if a_l > 1.0 {
                    clipped_samples += 1;
                }
                if a_r > 1.0 {
                    clipped_samples += 1;
                }
            }
        } else {
            for i in 0..(frame_samples_per_channel * channels) {
                let v = float_buf[i];
                let a = v.abs();
                if a > max_abs_sample {
                    max_abs_sample = a;
                }
                if a > 1.0 {
                    clipped_samples += 1;
                }
            }
        }

        let len = encoder
            .encode_float(&float_buf, &mut opus_out)
            .map_err(|e| anyhow!("opus encode failed: {e}"))?;

        let packet = OutAudio::new(&AudioData::C2S {
            id: 0,
            codec: CodecType::OpusMusic,
            data: &opus_out[..len],
        });

        let _ = ts3_audio_tx.send(packet).await;

        if now >= diag_next {
            diag_next = now + Duration::from_secs(5);
            if underruns_window > 0 || clipped_samples > 0 || tick_jitter_max_ms > 25 {
                warn!(
                    source_url = %source_url,
                    underruns_total = %underruns_total,
                    underruns_window = %underruns_window,
                    tick_jitter_max_ms = %tick_jitter_max_ms,
                    clipped_samples = %clipped_samples,
                    max_abs_sample = %max_abs_sample,
                    "audio_encode_diag"
                );
            } else {
                info!(
                    source_url = %source_url,
                    underruns_total = %underruns_total,
                    underruns_window = %underruns_window,
                    tick_jitter_max_ms = %tick_jitter_max_ms,
                    clipped_samples = %clipped_samples,
                    max_abs_sample = %max_abs_sample,
                    "audio_encode_diag"
                );
            }
            tick_jitter_max_ms = 0;
            clipped_samples = 0;
            max_abs_sample = 0.0;
            underruns_window = 0;
        }
    }

    // Signal end-of-stream to clients (flush/stop decoder).
    let eos = OutAudio::new(&AudioData::C2S {
        id: 0,
        codec: CodecType::OpusMusic,
        data: &[],
    });
    let _ = ts3_audio_tx.send(eos).await;

    if let Some(mut c) = child.child.take() {
        let _ = c.start_kill();
        let _ = c.wait().await;
    }
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    logger::init_logger();

    let addr = env::args().nth(1).unwrap_or_else(|| "127.0.0.1:50051".to_string());

    let (ts3_audio_tx, ts3_audio_rx) = mpsc::channel::<OutPacket>(200);
    let (ts3_notice_tx, ts3_notice_rx) = mpsc::channel::<(i32, String)>(50);
    let (ts3_cmd_tx, ts3_cmd_rx) = mpsc::channel::<OutCommand>(50);

    let (events_tx, _events_rx) = broadcast::channel::<voicev1::Event>(512);

    // Create shutdown signal handler
    let shutdown_token = CancellationToken::new();
    let shutdown_token_clone = shutdown_token.clone();
    
    tokio::spawn(async move {
        tokio::signal::ctrl_c().await.expect("Failed to listen for ctrl+c");
        info!("Received Ctrl+C, shutting down gracefully...");
        shutdown_token_clone.cancel();
    });

    let ts3_task = {
        let events_tx_clone = events_tx.clone();
        let shutdown_token_clone = shutdown_token.clone();
        tokio::spawn(async move {
            if let Err(e) = ts3_actor(ts3_audio_rx, ts3_notice_rx, ts3_cmd_rx, events_tx_clone, shutdown_token_clone).await {
                error!(%e, "ts3 actor exited");
            }
        })
    };

    let persist_file = resolve_repo_relative(&get_env("TSBOT_VOICE_STATE_FILE", "./logs/voice_state.json"));

    let mut init_status = SharedStatus {
        state: 1, // STATE_IDLE
        now_playing_title: String::new(),
        now_playing_source_url: String::new(),
        volume_percent: 100,
        fx_pan: 0.0,
        fx_width: 1.0,
        fx_swap_lr: false,
        fx_bass_db: 0.0,
        fx_reverb_mix: 0.0,
    };

    if let Some(ps) = load_persisted_voice_state(&persist_file) {
        init_status.volume_percent = ps.volume_percent.clamp(0, 200);
        init_status.fx_pan = ps.fx_pan.clamp(-1.0, 1.0);
        init_status.fx_width = ps.fx_width.clamp(0.0, 3.0);
        init_status.fx_swap_lr = ps.fx_swap_lr;
        init_status.fx_bass_db = ps.fx_bass_db.clamp(0.0, 18.0);
        init_status.fx_reverb_mix = ps.fx_reverb_mix.clamp(0.0, 1.0);
    }

    let (persist_tx, mut persist_rx) = mpsc::channel::<PersistedVoiceState>(32);
    {
        let persist_file = persist_file.clone();
        tokio::spawn(async move {
            let mut pending: Option<PersistedVoiceState> = None;
            let mut debounce: Option<Pin<Box<tokio::time::Sleep>>> = None;

            loop {
                tokio::select! {
                    r = persist_rx.recv() => {
                        match r {
                            Some(st) => {
                                pending = Some(st);
                                debounce = Some(Box::pin(tokio::time::sleep(Duration::from_millis(200))));
                            }
                            None => {
                                break;
                            }
                        }
                    }
                    _ = async {
                        if let Some(t) = debounce.as_mut() {
                            t.as_mut().await;
                        } else {
                            futures::future::pending::<()>().await;
                        }
                    } => {
                        if let Some(st) = pending.take() {
                            debounce = None;
                            if let Some(parent) = persist_file.parent() {
                                let _ = tokio::fs::create_dir_all(parent).await;
                            }
                            if let Ok(s) = serde_json::to_string_pretty(&st) {
                                let _ = tokio::fs::write(&persist_file, s).await;
                            }
                        }
                    }
                }
            }

            if let Some(st) = pending.take() {
                if let Some(parent) = persist_file.parent() {
                    let _ = tokio::fs::create_dir_all(parent).await;
                }
                if let Ok(s) = serde_json::to_string_pretty(&st) {
                    let _ = tokio::fs::write(&persist_file, s).await;
                }
            }
        });
    }

    let svc = VoiceServiceImpl {
        status: Arc::new(Mutex::new(init_status)),
        playback: Arc::new(Mutex::new(None)),
        ts3_audio_tx,
        ts3_notice_tx,
        ts3_cmd_tx,
        events_tx,
        persist_tx,
    };

    let addr: std::net::SocketAddr = addr.parse()?;
    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .map_err(|e| anyhow!("grpc listen failed on {addr}: {e}"))?;

    info!("voice-service listening on {}", listener.local_addr()?);

    let server = tonic::transport::Server::builder()
        .add_service(VoiceServiceServer::new(svc))
        .serve_with_incoming_shutdown(
            TcpListenerStream::new(listener),
            shutdown_token.cancelled()
        );

    tokio::select! {
        result = server => {
            if let Err(e) = result {
                error!("gRPC server failed: {e:?}");
            }
        }
        _ = shutdown_token.cancelled() => {
            info!("Server shutting down...");
        }
    }

    // Wait for TS3 task to finish
    if let Err(e) = ts3_task.await {
        error!("Failed to wait for TS3 task: {e}");
    }

    info!("Voice service shutdown complete");
    Ok(())
}
