use super::*;

#[tokio::test]
async fn fast_producer_stays_bounded_and_preserves_order() {
    let (sender, mut buffer) = PcmBuffer::channel();
    for index in 0..PCM_CHANNEL_CAPACITY {
        sender.try_send(index.to_le_bytes().to_vec()).unwrap();
    }
    assert!(matches!(
        sender.try_send(vec![]),
        Err(mpsc::error::TrySendError::Full(_))
    ));
    for expected in 0..PCM_CHANNEL_CAPACITY {
        let PcmFrame::Audio(frame) = buffer.next_frame().await else {
            panic!("lost frame")
        };
        assert_eq!(frame, expected.to_le_bytes());
        assert_eq!(sender.capacity(), expected + 1);
    }
}

#[tokio::test]
async fn waits_for_prebuffer_while_source_is_open() {
    let (sender, mut buffer) = PcmBuffer::channel();
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
    let (sender, mut buffer) = PcmBuffer::channel();
    sender.send(vec![1]).await.unwrap();
    drop(sender);
    assert!(matches!(buffer.next_frame().await, PcmFrame::Audio(frame) if frame == [1]));
    assert!(matches!(buffer.next_frame().await, PcmFrame::Finished));
}

#[tokio::test]
async fn empty_source_finishes_immediately() {
    let (sender, mut buffer) = PcmBuffer::channel();
    drop(sender);
    assert!(!buffer.has_audio());
    assert!(matches!(buffer.next_frame().await, PcmFrame::Finished));
}

#[tokio::test]
async fn temporary_underrun_does_not_end_stream() {
    let (sender, mut buffer) = PcmBuffer::channel();
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
    let (sender, buffer) = PcmBuffer::channel();
    for _ in 0..PCM_CHANNEL_CAPACITY {
        sender.try_send(vec![1]).unwrap();
    }
    let producer = tokio::spawn(async move { sender.send(vec![2]).await });
    tokio::task::yield_now().await;
    assert!(!producer.is_finished());
    drop(buffer);
    assert!(producer.await.unwrap().is_err());
}
