use super::*;
use std::io::Write;

struct TestAudio(PathBuf);

impl Drop for TestAudio {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}

fn silent_wav(seconds: u32) -> TestAudio {
    let path = env::temp_dir().join(format!("tsbot-pcm-{}-{}.wav", std::process::id(), now_unix_ms()));
    let mut file = fs::File::create(&path).unwrap();
    let data_bytes = seconds * 48_000 * 2 * 2;
    file.write_all(b"RIFF").unwrap();
    file.write_all(&(data_bytes + 36).to_le_bytes()).unwrap();
    file.write_all(b"WAVEfmt ").unwrap();
    file.write_all(&16u32.to_le_bytes()).unwrap();
    file.write_all(&1u16.to_le_bytes()).unwrap();
    file.write_all(&2u16.to_le_bytes()).unwrap();
    file.write_all(&48_000u32.to_le_bytes()).unwrap();
    file.write_all(&192_000u32.to_le_bytes()).unwrap();
    file.write_all(&4u16.to_le_bytes()).unwrap();
    file.write_all(&16u16.to_le_bytes()).unwrap();
    file.write_all(b"data").unwrap();
    file.write_all(&data_bytes.to_le_bytes()).unwrap();
    file.set_len(44 + u64::from(data_bytes)).unwrap();
    TestAudio(path)
}

#[tokio::test]
#[ignore = "requires ffmpeg and ten minutes of real-time playback"]
async fn ten_minute_playback_completes_with_bounded_pcm() {
    let audio = silent_wav(600);
    let (sender, mut receiver) = mpsc::channel(200);
    let sink = tokio::spawn(async move {
        let mut packets = 0usize;
        while receiver.recv().await.is_some() {
            packets += 1;
        }
        packets
    });
    let (_paused_sender, paused_receiver) = watch::channel(false);
    let status = Arc::new(Mutex::new(SharedStatus {
        volume_percent: 100,
        ..Default::default()
    }));
    let started = Instant::now();
    tokio::time::timeout(
        Duration::from_secs(630),
        playback_loop(
            audio.0.to_string_lossy().into_owned(),
            0.0,
            sender,
            paused_receiver,
            CancellationToken::new(),
            status,
        ),
    )
    .await
    .expect("ten-minute track timed out")
    .expect("ten-minute track failed");
    let packets = sink.await.unwrap();
    assert!(started.elapsed() >= Duration::from_secs(600), "playback ended prematurely");
    // 30,000 audio frames, the end-of-stream packet, and a small startup silence allowance.
    assert!((30_001..=30_150).contains(&packets), "unexpected packet count: {packets}");
    eprintln!("ten-minute playback completed: packets={packets}, elapsed={:?}", started.elapsed());
}

#[tokio::test]
#[ignore = "requires ffmpeg and a 30-second real-time memory check"]
async fn long_track_memory_stays_bounded_and_stop_remains_responsive() {
    fn rss_kib() -> u64 {
        fs::read_to_string("/proc/self/status")
            .unwrap()
            .lines()
            .find_map(|line| line.strip_prefix("VmRSS:").map(|v| v.split_whitespace().next().unwrap().parse().unwrap()))
            .unwrap()
    }
    let audio = silent_wav(4105);
    let (sender, mut receiver) = mpsc::channel(200);
    let sink = tokio::spawn(async move {
        while receiver.recv().await.is_some() {}
    });
    let (_paused_sender, paused_receiver) = watch::channel(false);
    let cancel = CancellationToken::new();
    let playback_cancel = cancel.clone();
    let source = audio.0.to_string_lossy().into_owned();
    let initial_rss = rss_kib();
    let playback = tokio::spawn(playback_loop(
        source,
        0.0,
        sender,
        paused_receiver,
        playback_cancel,
        Arc::new(Mutex::new(SharedStatus::default())),
    ));
    let mut peak_rss = initial_rss;
    for _ in 0..6 {
        tokio::time::sleep(Duration::from_secs(5)).await;
        assert!(!playback.is_finished(), "long track stopped before cancellation");
        let rss = rss_kib();
        peak_rss = peak_rss.max(rss);
        eprintln!("long-track RSS: {rss} KiB");
        assert!(rss <= initial_rss + 32 * 1024, "long track exceeded its PCM memory budget");
    }
    cancel.cancel();
    tokio::time::timeout(Duration::from_secs(3), playback)
        .await.expect("stop was blocked by the full PCM buffer")
        .unwrap().unwrap();
    sink.await.unwrap();
    eprintln!("long-track stop passed: initial_rss={initial_rss} KiB, peak_rss={peak_rss} KiB");
}
