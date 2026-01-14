use std::env;
use std::fs;
use std::collections::VecDeque;
use std::process::Stdio;
use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::{anyhow, Result};
use audiopus::coder::Encoder;
use futures::{FutureExt, StreamExt};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, BufReader};
use tokio::sync::{broadcast, mpsc, watch, Mutex};
use tokio_stream::wrappers::{BroadcastStream, TcpListenerStream};
use tokio_util::sync::CancellationToken;
use tonic::{Request, Response, Status};
use tracing::{error, info};

use tsclientlib::{Connection, DisconnectOptions, Identity, StreamItem};
use tsproto_packets::packets::{AudioData, CodecType, Direction, Flags, OutAudio, OutCommand, OutPacket, PacketType};
use tsclientlib::{events, MessageTarget};

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
}

struct PlaybackControl {
    cancel: CancellationToken,
    paused_tx: watch::Sender<bool>,
    handle: tokio::task::JoinHandle<()>,
}

#[derive(Clone)]
struct VoiceServiceImpl {
    status: Arc<Mutex<SharedStatus>>,
    playback: Arc<Mutex<Option<PlaybackControl>>>,
    ts3_audio_tx: mpsc::Sender<OutPacket>,
    ts3_notice_tx: mpsc::Sender<String>,
    events_tx: broadcast::Sender<voicev1::Event>,
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

fn emit_chat(
    events_tx: &broadcast::Sender<voicev1::Event>,
    target_mode: i32,
    invoker_uid: impl Into<String>,
    invoker_name: impl Into<String>,
    msg: impl Into<String>,
) {
    let _ = events_tx.send(voicev1::Event {
        unix_ms: now_unix_ms(),
        payload: Some(voicev1::event::Payload::Chat(voicev1::ChatEvent {
            target_mode,
            invoker_unique_id: invoker_uid.into(),
            invoker_name: invoker_name.into(),
            message: msg.into(),
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
            let _ = self.ts3_notice_tx.try_send(r.notice.clone());
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
            let _ = self.ts3_notice_tx.try_send(r.message);
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
        let mut st = self.status.lock().await;
        st.volume_percent = v;

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
            p.handle.abort();
        }
    }
}

fn get_env(key: &str, def: &str) -> String {
    match env::var(key) {
        Ok(v) if !v.is_empty() => v,
        _ => def.to_string(),
    }
}

async fn ts3_actor(
    mut audio_rx: mpsc::Receiver<OutPacket>,
    mut notice_rx: mpsc::Receiver<String>,
    events_tx: broadcast::Sender<voicev1::Event>,
) -> Result<()> {
    let host = get_env("TSBOT_TS3_HOST", "127.0.0.1");
    let port = get_env("TSBOT_TS3_PORT", "9987");
    let nickname = get_env("TSBOT_TS3_NICKNAME", "tsbot");
    let server_password = get_env("TSBOT_TS3_SERVER_PASSWORD", "");
    let channel_password = get_env("TSBOT_TS3_CHANNEL_PASSWORD", "");
    let channel_path = get_env("TSBOT_TS3_CHANNEL_PATH", "");
    let channel_id = get_env("TSBOT_TS3_CHANNEL_ID", "");
    let identity_str = get_env("TSBOT_TS3_IDENTITY", "");
    let identity_file = get_env("TSBOT_TS3_IDENTITY_FILE", "./logs/identity.txt");

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
            if let Some(parent) = std::path::Path::new(&identity_file).parent() {
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

    let mut con = opts.connect().map_err(|e| anyhow!("connect failed: {e}"))?;
    let mut logged_connected = false;
    let mut last_muted_warn = Instant::now() - Duration::from_secs(60);

    let mut out_buf: VecDeque<OutPacket> = VecDeque::with_capacity(400);

    // Process events periodically without holding a long-lived mutable borrow of `con`.
    let mut event_tick = tokio::time::interval(std::time::Duration::from_millis(50));
    let mut send_tick = tokio::time::interval(std::time::Duration::from_millis(20));
    loop {
        tokio::select! {
            _ = event_tick.tick() => {
                // Drain any events that are immediately ready.
                let mut events = con.events();
                loop {
                    match events.next().now_or_never() {
                        Some(Some(Ok(StreamItem::BookEvents(evts)))) => {
                            if !logged_connected {
                                info!("ts3 connected");
                                logged_connected = true;
                                // LogEvent.Level: INFO=2
                                emit_log(&events_tx, 2, "ts3 connected");
                            }
                            for e in evts {
                                if let events::Event::Message { target, invoker, message } = e {
                                    let mode = match target {
                                        // ChatEvent.TargetMode: PRIVATE=1, CHANNEL=2, SERVER=3
                                        MessageTarget::Client(_) | MessageTarget::Poke(_) => 1,
                                        MessageTarget::Channel => 2,
                                        MessageTarget::Server => 3,
                                    };
                                    let uid = invoker
                                        .uid
                                        .as_ref()
                                        .map(|u| u.as_ref().to_string())
                                        .unwrap_or_default();
                                    emit_chat(&events_tx, mode, uid, invoker.name, message);
                                }
                            }
                        }
                        Some(Some(Ok(StreamItem::AudioChange(a)))) => {
                            if let tsclientlib::AudioEvent::CanSendAudio(can) = a {
                                emit_log(
                                    &events_tx,
                                    // LogEvent.Level: INFO=2, WARN=3
                                    if can { 2 } else { 3 },
                                    format!("can_send_audio={}", can),
                                );
                            }
                        }
                        Some(Some(Ok(_))) => {}
                        Some(Some(Err(e))) => {
                            // LogEvent.Level: ERROR=4
                            emit_log(&events_tx, 4, format!("ts3 error: {e}"));
                            return Err(anyhow!("ts3 event error: {e}"));
                        }
                        Some(None) => {
                            // LogEvent.Level: ERROR=4
                            emit_log(&events_tx, 4, "ts3 disconnected");
                            return Err(anyhow!("ts3 disconnected"));
                        }
                        None => break,
                    }
                }
            }

            _ = send_tick.tick() => {
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
                    } else {
                        con.send_audio(pkt).map_err(|e| anyhow!("send_audio failed: {e}"))?;
                    }
                }
            }

            msg = notice_rx.recv() => {
                if let Some(text) = msg {
                    // Send a channel chat message (targetmode=2). This uses the raw TS3 command.
                    let mut cmd = OutCommand::new(Direction::C2S, Flags::empty(), PacketType::Command, "sendtextmessage");
                    cmd.write_arg("targetmode", &2);
                    cmd.write_arg("msg", &text);

                    if let Ok(client) = con.get_tsproto_client_mut() {
                        client
                            .send_packet(cmd.into_packet())
                            .map_err(|e| anyhow!("sendtextmessage failed: {e}"))?;
                    }
                } else {
                    break;
                }
            }

            pkt = audio_rx.recv() => {
                if let Some(p) = pkt {
                    // Keep a bounded buffer to avoid unbounded growth if TS3 cannot accept audio.
                    if out_buf.len() >= 800 {
                        out_buf.pop_front();
                    }
                    out_buf.push_back(p);
                } else {
                    break;
                }
            }
            _ = tokio::signal::ctrl_c() => {
                break;
            }
        }
    }

    con.disconnect(DisconnectOptions::new()).ok();
    Ok(())
}

async fn playback_loop(
    source_url: String,
    ts3_audio_tx: mpsc::Sender<OutPacket>,
    mut paused_rx: watch::Receiver<bool>,
    cancel: CancellationToken,
    status: Arc<Mutex<SharedStatus>>,
) -> Result<()> {
    let mut child = tokio::process::Command::new("ffmpeg")
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

    if let Some(stderr) = child.stderr.take() {
        let src = source_url.clone();
        tokio::spawn(async move {
            let mut lines = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                info!(source_url = %src, "ffmpeg: {line}");
            }
        });
    }

    let mut stdout = child
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

    // Reader task: continuously read PCM frames from ffmpeg.
    // On EOF or error, it will stop sending and close the channel.
    let reader_cancel = cancel.clone();
    tokio::spawn(async move {
        let mut buf = vec![0u8; frame_bytes];
        loop {
            if reader_cancel.is_cancelled() {
                break;
            }
            if stdout.read_exact(&mut buf).await.is_err() {
                break;
            }
            if pcm_tx.send(buf.clone()).await.is_err() {
                break;
            }
        }
    });

    let mut ticker = tokio::time::interval(frame_duration);
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    let mut underruns: u64 = 0;

    loop {
        if cancel.is_cancelled() {
            break;
        }

        while *paused_rx.borrow() {
            tokio::select! {
                _ = cancel.cancelled() => { return Ok(()); }
                r = paused_rx.changed() => {
                    if r.is_err() {
                        return Ok(());
                    }
                }
            }
        }

        tokio::select! {
            _ = cancel.cancelled() => { break; }
            _ = ticker.tick() => {}
        }

        // Prefer real PCM frame; fall back to silence to keep cadence stable.
        match pcm_rx.try_recv() {
            Ok(frame) => {
                if frame.len() == frame_bytes {
                    pcm.copy_from_slice(&frame);
                } else {
                    pcm.fill(0);
                    underruns += 1;
                }
            }
            Err(tokio::sync::mpsc::error::TryRecvError::Empty) => {
                pcm.fill(0);
                underruns += 1;
            }
            Err(tokio::sync::mpsc::error::TryRecvError::Disconnected) => {
                // ffmpeg finished / failed. Stop playback.
                break;
            }
        }

        if underruns > 0 && underruns % 50 == 0 {
            info!(%underruns, "playback underrun (sending silence frames to keep cadence)");
        }

        let vol = {
            let st = status.lock().await;
            (st.volume_percent as f32 / 100.0).clamp(0.0, 2.0)
        };

        for i in 0..(frame_samples_per_channel * channels) {
            let lo = pcm[i * 2];
            let hi = pcm[i * 2 + 1];
            let s = i16::from_le_bytes([lo, hi]) as f32;
            float_buf[i] = (s / 32768.0) * vol;
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
    }

    // Signal end-of-stream to clients (flush/stop decoder).
    let eos = OutAudio::new(&AudioData::C2S {
        id: 0,
        codec: CodecType::OpusMusic,
        data: &[],
    });
    let _ = ts3_audio_tx.send(eos).await;

    let _ = child.kill().await;
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();

    let addr = env::args().nth(1).unwrap_or_else(|| "127.0.0.1:50051".to_string());

    let (ts3_audio_tx, ts3_audio_rx) = mpsc::channel::<OutPacket>(200);
    let (ts3_notice_tx, ts3_notice_rx) = mpsc::channel::<String>(50);

    let (events_tx, _events_rx) = broadcast::channel::<voicev1::Event>(512);

    {
        let events_tx = events_tx.clone();
        tokio::spawn(async move {
            if let Err(e) = ts3_actor(ts3_audio_rx, ts3_notice_rx, events_tx).await {
            error!(%e, "ts3 actor exited");
            }
        });
    }

    let svc = VoiceServiceImpl {
        status: Arc::new(Mutex::new(SharedStatus {
            state: 1, // STATE_IDLE
            now_playing_title: String::new(),
            now_playing_source_url: String::new(),
            volume_percent: 100,
        })),
        playback: Arc::new(Mutex::new(None)),
        ts3_audio_tx,
        ts3_notice_tx,
        events_tx,
    };

    let addr: std::net::SocketAddr = addr.parse()?;
    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .map_err(|e| anyhow!("grpc listen failed on {addr}: {e}"))?;

    info!("voice-service listening on {}", listener.local_addr()?);

    tonic::transport::Server::builder()
        .add_service(VoiceServiceServer::new(svc))
        .serve_with_incoming(TcpListenerStream::new(listener))
        .await
        .map_err(|e| anyhow!("grpc server failed: {e:?}"))?;

    Ok(())
}
