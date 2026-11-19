use std::sync::Arc;

pub const STATE_IDLE: i32 = 1;
pub const STATE_PLAYING: i32 = 2;
pub const STATE_PAUSED: i32 = 3;

pub struct PlaybackId(Arc<()>);

#[derive(Default)]
pub struct SharedStatus {
    pub state: i32,
    pub now_playing_title: String,
    pub now_playing_source_url: String,
    pub volume_percent: i32,
    pub fx_pan: f32,
    pub fx_width: f32,
    pub fx_swap_lr: bool,
    pub fx_bass_db: f32,
    pub fx_reverb_mix: f32,
    active: Option<Arc<()>>,
}

impl SharedStatus {
    pub fn idle() -> Self {
        Self {
            state: STATE_IDLE,
            volume_percent: 100,
            fx_width: 1.0,
            ..Self::default()
        }
    }

    pub fn begin(&mut self, track: (String, String), paused: bool) -> PlaybackId {
        let id = Arc::new(());
        self.active = Some(id.clone());
        (self.now_playing_title, self.now_playing_source_url) = track;
        self.state = if paused { STATE_PAUSED } else { STATE_PLAYING };
        PlaybackId(id)
    }

    pub fn finish(&mut self, id: &PlaybackId) -> bool {
        if !self
            .active
            .as_ref()
            .is_some_and(|active| Arc::ptr_eq(active, &id.0))
        {
            return false;
        }
        self.stop();
        true
    }

    pub fn stop(&mut self) {
        self.active = None;
        self.state = STATE_IDLE;
        self.now_playing_title.clear();
        self.now_playing_source_url.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn track() -> (String, String) {
        ("song".into(), "same-url".into())
    }

    #[test]
    fn completion_clears_track_and_keeps_audio_settings() {
        let mut status = SharedStatus::default();
        status.volume_percent = 70;
        status.fx_width = 0.5;
        let id = status.begin(track(), false);
        assert!(status.finish(&id));
        assert_eq!(status.state, STATE_IDLE);
        assert!(status.now_playing_title.is_empty());
        assert!(status.now_playing_source_url.is_empty());
        assert_eq!(status.volume_percent, 70);
        assert_eq!(status.fx_width, 0.5);
        assert!(!status.finish(&id));
    }

    #[test]
    fn replay_or_seek_cannot_be_cleared_by_previous_task() {
        let mut status = SharedStatus::default();
        let previous = status.begin(track(), false);
        let current = status.begin(track(), true);
        assert!(!status.finish(&previous));
        assert_eq!(status.state, STATE_PAUSED);
        assert_eq!(status.now_playing_source_url, "same-url");
        assert!(status.finish(&current));
    }

    #[test]
    fn explicit_stop_invalidates_completion() {
        let mut status = SharedStatus::idle();
        let id = status.begin(track(), false);
        status.stop();
        assert!(!status.finish(&id));
        assert_eq!(status.state, STATE_IDLE);
        assert!(status.now_playing_source_url.is_empty());
    }
}
