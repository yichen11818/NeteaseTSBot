use super::*;
use crate::{voicev1, SharedStatus};
use std::sync::Arc;
use tokio::sync::{broadcast, mpsc, Mutex};

fn service() -> VoiceServiceImpl {
    VoiceServiceImpl {
        status: Arc::new(Mutex::new(SharedStatus::idle())),
        playback: Arc::new(Mutex::new(None)),
        ts3_audio_tx: mpsc::channel(1).0,
        ts3_notice_tx: mpsc::channel(1).0,
        ts3_cmd_tx: mpsc::channel(1).0,
        events_tx: broadcast::channel(4).0,
        persist_tx: mpsc::channel(1).0,
    }
}

fn request() -> PlaybackRequest {
    PlaybackRequest {
        title: "song".into(),
        source_url: "same-url".into(),
        notice: String::new(),
        start_time_s: 0.0,
        paused: false,
    }
}

#[tokio::test]
async fn idle_is_observable_when_finished_or_error_event_arrives() {
    for result in [Ok(()), Err(anyhow::anyhow!("decoder failed"))] {
        let service = service();
        let mut events = service.events_tx.subscribe();
        let request = request();
        let id = service
            .status
            .lock()
            .await
            .begin((request.title.clone(), request.source_url.clone()), false);
        let expected_event = if result.is_ok() { 2 } else { 3 };
        service.complete_playback(id, request, result).await;
        let event = events.try_recv().unwrap();
        let Some(voicev1::event::Payload::Playback(event)) = event.payload else {
            panic!("expected playback event");
        };
        assert_eq!(event.r#type, expected_event);
        let status = service.status.lock().await;
        assert_eq!(status.state, 1);
        assert!(status.now_playing_source_url.is_empty());
        assert_eq!(event.source_url, "same-url");
    }
}

#[tokio::test]
async fn stale_task_cannot_clear_replay_or_publish_completion() {
    let service = service();
    let mut events = service.events_tx.subscribe();
    let previous = service
        .status
        .lock()
        .await
        .begin(("song".into(), "same-url".into()), false);
    service
        .status
        .lock()
        .await
        .begin(("song".into(), "same-url".into()), false);
    service.complete_playback(previous, request(), Ok(())).await;
    assert!(events.try_recv().is_err());
    assert_eq!(service.status.lock().await.state, 2);
    service.stop_internal().await;
    assert_eq!(service.status.lock().await.state, 1);
}
