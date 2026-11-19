use std::time::Duration;

use tokio::sync::mpsc;

const FRAMES_PER_SECOND: usize = 50;
const DEFAULT_BUFFER_SECONDS: usize = 5;
const MIN_BUFFER_SECONDS: usize = 1;
const MAX_BUFFER_SECONDS: usize = 30;
pub const DEFAULT_BUFFERED_FRAMES: usize = DEFAULT_BUFFER_SECONDS * FRAMES_PER_SECOND;

pub fn max_frames_from_config(raw: Option<&str>) -> usize {
    let seconds = raw
        .map(str::trim)
        .filter(|value| !value.is_empty() && value.bytes().all(|byte| byte.is_ascii_digit()))
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|seconds| (MIN_BUFFER_SECONDS..=MAX_BUFFER_SECONDS).contains(seconds))
        .unwrap_or(DEFAULT_BUFFER_SECONDS);
    seconds * FRAMES_PER_SECOND
}
const PREBUFFER_FRAMES: usize = if cfg!(windows) { 15 } else { 5 };
const LATE_FRAME_WAIT: Duration = Duration::from_millis(if cfg!(windows) { 8 } else { 3 });

pub enum PcmFrame {
    Audio(Vec<u8>),
    Pending,
    Finished,
}

/// The bounded channel is the entire prebuffer. Reading one frame per tick
/// propagates backpressure to FFmpeg instead of accumulating decoded audio.
pub struct PcmBuffer {
    receiver: mpsc::Receiver<Vec<u8>>,
    prebuffering: bool,
}

impl PcmBuffer {
    pub fn channel(max_frames: usize) -> (mpsc::Sender<Vec<u8>>, Self) {
        let (sender, receiver) = mpsc::channel(max_frames);
        (
            sender,
            Self {
                receiver,
                prebuffering: true,
            },
        )
    }

    pub fn has_audio(&self) -> bool {
        !self.receiver.is_empty()
    }

    pub async fn next_frame(&mut self) -> PcmFrame {
        if self.prebuffering {
            // EOF must drain even clips shorter than the prebuffer target.
            if self.receiver.len() < PREBUFFER_FRAMES && !self.receiver.is_closed() {
                return PcmFrame::Pending;
            }
            self.prebuffering = false;
        }
        match tokio::time::timeout(LATE_FRAME_WAIT, self.receiver.recv()).await {
            Ok(Some(frame)) => PcmFrame::Audio(frame),
            Ok(None) => PcmFrame::Finished,
            Err(_) => PcmFrame::Pending,
        }
    }
}

#[cfg(test)]
mod tests;
