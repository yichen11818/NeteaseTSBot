use super::{emit_playback, playback_loop, PlaybackControl, VoiceServiceImpl};
use std::time::Duration;
use tokio::sync::watch;
use tokio_util::sync::CancellationToken;
use tonic::Status;
use tracing::error;
use voice_service::playback_status::PlaybackId;

const STOP_TIMEOUT: Duration = Duration::from_secs(2);

pub(super) struct PlaybackRequest {
    pub title: String,
    pub source_url: String,
    pub notice: String,
    pub start_time_s: f64,
    pub paused: bool,
}

impl VoiceServiceImpl {
    pub(super) async fn start_playback_internal(
        &self,
        request: PlaybackRequest,
    ) -> Result<(), Status> {
        // Serialize replacement through handle registration, including concurrent Play RPCs.
        let mut playback = self.playback.lock().await;
        cancel_playback(playback.take()).await;
        if !request.notice.is_empty() {
            let _ = self.ts3_notice_tx.try_send((2, request.notice.clone()));
        }
        let id = self.status.lock().await.begin(
            (request.title.clone(), request.source_url.clone()),
            request.paused,
        );
        emit_playback(
            &self.events_tx,
            1,
            request.title.clone(),
            request.source_url.clone(),
            "",
        );
        let (paused_tx, paused_rx) = watch::channel(request.paused);
        let cancel = CancellationToken::new();
        let task_cancel = cancel.clone();
        let service = self.clone();
        let handle = tokio::spawn(async move {
            let result = playback_loop(
                request.source_url.clone(),
                request.start_time_s,
                service.ts3_audio_tx.clone(),
                paused_rx,
                task_cancel.clone(),
                service.status.clone(),
            )
            .await;
            if !task_cancel.is_cancelled() {
                service.complete_playback(id, request, result).await;
            }
        });
        *playback = Some(PlaybackControl {
            cancel,
            paused_tx,
            handle,
        });
        Ok(())
    }

    async fn complete_playback(
        &self,
        id: PlaybackId,
        request: PlaybackRequest,
        result: anyhow::Result<()>,
    ) {
        let mut status = self.status.lock().await;
        if !status.finish(&id) {
            return;
        }
        // Publish after cleanup while still holding the status lock, before another start.
        match result {
            Ok(()) => emit_playback(&self.events_tx, 2, request.title, request.source_url, ""),
            Err(error) => {
                error!(%error, "playback loop failed");
                emit_playback(
                    &self.events_tx,
                    3,
                    request.title,
                    request.source_url,
                    error.to_string(),
                );
            }
        }
    }

    pub(super) async fn stop_internal(&self) {
        let mut playback = self.playback.lock().await;
        cancel_playback(playback.take()).await;
        self.status.lock().await.stop();
    }
}

async fn cancel_playback(control: Option<PlaybackControl>) {
    let Some(control) = control else { return };
    control.cancel.cancel();
    let abort_handle = control.handle.abort_handle();
    if tokio::time::timeout(STOP_TIMEOUT, control.handle)
        .await
        .is_err()
    {
        abort_handle.abort();
    }
}

#[cfg(test)]
mod tests;
