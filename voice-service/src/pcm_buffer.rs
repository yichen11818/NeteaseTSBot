use std::collections::VecDeque;

use tokio::sync::mpsc;

// Five seconds of 20 ms PCM frames, independent of the track's total duration.
pub const DEFAULT_BUFFERED_FRAMES: usize = 250;

pub fn max_frames_from_config(raw: Option<&str>) -> usize {
    let seconds = raw
        .map(str::trim)
        .filter(|value| !value.is_empty() && value.bytes().all(|byte| byte.is_ascii_digit()))
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|seconds| (1..=30).contains(seconds))
        .unwrap_or(DEFAULT_BUFFERED_FRAMES / 50);
    seconds * 50
}

pub fn fill_pcm_buffer(
    buffer: &mut VecDeque<Vec<u8>>,
    receiver: &mut mpsc::Receiver<Vec<u8>>,
    frame_bytes: usize,
    max_frames: usize,
) {
    // Leave excess frames in the bounded channel, backpressuring the reader/FFmpeg.
    while buffer.len() < max_frames {
        let Ok(frame) = receiver.try_recv() else {
            break;
        };
        if frame.len() == frame_bytes {
            buffer.push_back(frame);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const FRAME_BYTES: usize = 3840;

    #[test]
    fn configured_seconds_have_safe_bounds_and_fallback() {
        for (value, frames) in [("1", 50), ("5", 250), ("30", 1500), (" 12 ", 600)] {
            assert_eq!(max_frames_from_config(Some(value)), frames);
        }
        for value in [None, Some(""), Some("0"), Some("31"), Some("-1"), Some("1.5"), Some("NaN"), Some("０"), Some("99999999999999999999999999999999")] {
            assert_eq!(max_frames_from_config(value), 250);
        }
    }

    #[test]
    fn full_buffer_leaves_frames_in_the_bounded_channel() {
        let (sender, mut receiver) = mpsc::channel(DEFAULT_BUFFERED_FRAMES + 2);
        for _ in 0..DEFAULT_BUFFERED_FRAMES + 2 {
            sender.try_send(vec![0; FRAME_BYTES]).unwrap();
        }
        let mut buffer = VecDeque::new();
        fill_pcm_buffer(&mut buffer, &mut receiver, FRAME_BYTES, DEFAULT_BUFFERED_FRAMES);
        assert_eq!(buffer.len(), DEFAULT_BUFFERED_FRAMES);
        assert_eq!(receiver.len(), 2);

        buffer.pop_front().unwrap();
        fill_pcm_buffer(&mut buffer, &mut receiver, FRAME_BYTES, DEFAULT_BUFFERED_FRAMES);
        assert_eq!(buffer.len(), DEFAULT_BUFFERED_FRAMES);
        assert_eq!(receiver.len(), 1);
    }

    #[tokio::test]
    async fn full_buffer_applies_backpressure_and_resumes_without_dropping_frames() {
        let (sender, mut receiver) = mpsc::channel(1);
        let mut buffer = VecDeque::from(vec![vec![0; FRAME_BYTES]; DEFAULT_BUFFERED_FRAMES]);
        sender.try_send(vec![1; FRAME_BYTES]).unwrap();
        let blocked_sender = sender.clone();
        let pending = tokio::spawn(async move { blocked_sender.send(vec![2; FRAME_BYTES]).await });
        tokio::task::yield_now().await;

        fill_pcm_buffer(&mut buffer, &mut receiver, FRAME_BYTES, DEFAULT_BUFFERED_FRAMES);
        tokio::task::yield_now().await;
        assert!(!pending.is_finished(), "a full PCM buffer must keep its producer blocked");

        buffer.pop_front().unwrap();
        fill_pcm_buffer(&mut buffer, &mut receiver, FRAME_BYTES, DEFAULT_BUFFERED_FRAMES);
        pending.await.unwrap().unwrap();
        assert_eq!(buffer.len(), DEFAULT_BUFFERED_FRAMES);
        assert_eq!(buffer.back().unwrap()[0], 1);
        assert_eq!(receiver.try_recv().unwrap()[0], 2);
    }

    async fn drain_track(seconds: usize) {
        let frame_count = seconds * 50;
        let (sender, mut receiver) = mpsc::channel(50);
        let producer = tokio::spawn(async move {
            for index in 0..frame_count {
                let mut frame = vec![0; FRAME_BYTES];
                frame[..8].copy_from_slice(&(index as u64).to_le_bytes());
                sender.send(frame).await.unwrap();
            }
        });
        let mut buffer = VecDeque::new();
        let mut consumed = 0;
        let mut peak = 0;
        while consumed < frame_count {
            fill_pcm_buffer(&mut buffer, &mut receiver, FRAME_BYTES, DEFAULT_BUFFERED_FRAMES);
            peak = peak.max(buffer.len());
            assert!(buffer.len() <= DEFAULT_BUFFERED_FRAMES);
            if let Some(frame) = buffer.pop_front() {
                assert_eq!(u64::from_le_bytes(frame[..8].try_into().unwrap()), consumed as u64);
                consumed += 1;
            }
            // Accelerated playback: one frame per iteration, without wall-clock waits.
            tokio::task::yield_now().await;
        }
        producer.await.unwrap();
        assert!(peak > 0);
        assert!(buffer.is_empty());
        assert!(receiver.recv().await.is_none());
    }

    #[tokio::test]
    async fn ten_minute_track_delivers_every_frame_in_order() {
        drain_track(600).await;
    }

    #[test]
    fn custom_buffer_limits_preserve_remaining_channel_frames() {
        for seconds in ["1", "30"] {
            let maximum = max_frames_from_config(Some(seconds));
            let (sender, mut receiver) = mpsc::channel(maximum + 2);
            for _ in 0..maximum + 2 {
                sender.try_send(vec![0; FRAME_BYTES]).unwrap();
            }
            let mut buffer = VecDeque::new();
            fill_pcm_buffer(&mut buffer, &mut receiver, FRAME_BYTES, maximum);
            assert_eq!(buffer.len(), maximum);
            assert_eq!(receiver.len(), 2);
        }
    }

    #[tokio::test]
    async fn sixty_eight_minute_track_delivers_every_frame_in_order() {
        drain_track(4105).await;
    }
}
