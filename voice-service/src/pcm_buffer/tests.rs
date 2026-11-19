use super::*;

#[test]
fn configured_seconds_have_safe_bounds_and_default() {
    for (value, frames) in [("1", 50), ("5", 250), ("30", 1500), (" 12 ", 600)] {
        assert_eq!(max_frames_from_config(Some(value)), frames);
    }
    for value in [None, Some(""), Some("0"), Some("31"), Some("-1"),
        Some("1.5"), Some("NaN"), Some("０"), Some("99999999999999999999999999999999")] {
        assert_eq!(max_frames_from_config(value), DEFAULT_BUFFERED_FRAMES);
    }
}

#[tokio::test]
async fn configured_capacity_blocks_and_resumes_without_losing_frames() {
    for seconds in ["1", "30"] {
        let capacity = max_frames_from_config(Some(seconds));
        let (sender, mut buffer) = PcmBuffer::channel(capacity);
        for index in 0..capacity {
            sender.try_send(index.to_le_bytes().to_vec()).unwrap();
        }
        let producer = tokio::spawn(async move {
            sender.send(capacity.to_le_bytes().to_vec()).await.unwrap();
        });
        tokio::task::yield_now().await;
        assert!(!producer.is_finished());
        assert!(matches!(buffer.next_frame().await, PcmFrame::Audio(frame) if frame == 0usize.to_le_bytes()));
        producer.await.unwrap();
        for index in 1..=capacity {
            assert!(matches!(buffer.next_frame().await, PcmFrame::Audio(frame) if frame == index.to_le_bytes()));
        }
        assert!(matches!(buffer.next_frame().await, PcmFrame::Finished));
    }
}

async fn drain_track(seconds: usize) {
    let frame_count = seconds * FRAMES_PER_SECOND;
    let (sender, mut buffer) = PcmBuffer::channel(max_frames_from_config(Some("1")));
    let producer = tokio::spawn(async move {
        for index in 0..frame_count {
            sender.send(index.to_le_bytes().to_vec()).await.unwrap();
        }
    });
    let mut consumed = 0usize;
    loop {
        match buffer.next_frame().await {
            PcmFrame::Audio(frame) => {
                assert_eq!(frame, consumed.to_le_bytes());
                consumed += 1;
            }
            PcmFrame::Pending => tokio::task::yield_now().await,
            PcmFrame::Finished => break,
        }
    }
    producer.await.unwrap();
    assert_eq!(consumed, frame_count);
}

#[tokio::test]
async fn ten_minute_track_delivers_every_frame_in_order() {
    drain_track(600).await;
}

#[tokio::test]
async fn sixty_eight_minute_track_delivers_every_frame_in_order() {
    drain_track(4105).await;
}

#[tokio::test]
async fn fast_producer_stays_bounded_and_preserves_order() {
    let (sender, mut buffer) = PcmBuffer::channel(DEFAULT_BUFFERED_FRAMES);
    for index in 0..DEFAULT_BUFFERED_FRAMES {
        sender.try_send(index.to_le_bytes().to_vec()).unwrap();
    }
    assert!(matches!(
        sender.try_send(vec![]),
        Err(mpsc::error::TrySendError::Full(_))
    ));
    for expected in 0..DEFAULT_BUFFERED_FRAMES {
        let PcmFrame::Audio(frame) = buffer.next_frame().await else {
            panic!("lost frame")
        };
        assert_eq!(frame, expected.to_le_bytes());
        assert_eq!(sender.capacity(), expected + 1);
    }
}

#[tokio::test]
async fn waits_for_prebuffer_while_source_is_open() {
    let (sender, mut buffer) = PcmBuffer::channel(DEFAULT_BUFFERED_FRAMES);
    sender.send(vec![1]).await.unwrap();
    assert!(buffer.has_audio());
    assert!(matches!(buffer.next_frame().await, PcmFrame::Pending));
    for _ in 1..PREBUFFER_FRAMES {
        sender.send(vec![2]).await.unwrap();
    }
    assert!(matches!(buffer.next_frame().await, PcmFrame::Audio(frame) if frame == [1]));
}

#[tokio::test]
async fn short_clip_drains_at_eof_without_waiting_for_prebuffer() {
    let (sender, mut buffer) = PcmBuffer::channel(DEFAULT_BUFFERED_FRAMES);
    sender.send(vec![1]).await.unwrap();
    drop(sender);
    assert!(matches!(buffer.next_frame().await, PcmFrame::Audio(frame) if frame == [1]));
    assert!(matches!(buffer.next_frame().await, PcmFrame::Finished));
}

#[tokio::test]
async fn empty_source_finishes_immediately() {
    let (sender, mut buffer) = PcmBuffer::channel(DEFAULT_BUFFERED_FRAMES);
    drop(sender);
    assert!(!buffer.has_audio());
    assert!(matches!(buffer.next_frame().await, PcmFrame::Finished));
}

#[tokio::test]
async fn temporary_underrun_does_not_end_stream() {
    let (sender, mut buffer) = PcmBuffer::channel(DEFAULT_BUFFERED_FRAMES);
    for _ in 0..PREBUFFER_FRAMES {
        sender.send(vec![1]).await.unwrap();
    }
    for _ in 0..PREBUFFER_FRAMES {
        assert!(matches!(buffer.next_frame().await, PcmFrame::Audio(_)));
    }
    assert!(matches!(buffer.next_frame().await, PcmFrame::Pending));
    sender.send(vec![2]).await.unwrap();
    assert!(matches!(buffer.next_frame().await, PcmFrame::Audio(frame) if frame == [2]));
}

#[tokio::test]
async fn dropping_playback_releases_a_backpressured_producer() {
    let (sender, buffer) = PcmBuffer::channel(DEFAULT_BUFFERED_FRAMES);
    for _ in 0..DEFAULT_BUFFERED_FRAMES {
        sender.try_send(vec![1]).unwrap();
    }
    let producer = tokio::spawn(async move { sender.send(vec![2]).await });
    tokio::task::yield_now().await;
    assert!(!producer.is_finished());
    drop(buffer);
    assert!(producer.await.unwrap().is_err());
}
