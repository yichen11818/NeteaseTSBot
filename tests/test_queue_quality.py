import unittest

from backend.queue_quality import encode_qqmusic_source, qqmusic_queue_quality, strip_qqmusic_source


class QueueQualityTests(unittest.TestCase):
    def test_requested_quality_survives_missing_or_opaque_playback_url(self):
        for quality in ('m4a', '128', '320'):
            for url in ('', 'https://audio.example.test/opaque?key=a|b'):
                encoded = encode_qqmusic_source(quality, url)
                self.assertEqual(quality, qqmusic_queue_quality(encoded))
                self.assertEqual(url, strip_qqmusic_source(encoded))

    def test_existing_qq_urls_retain_their_original_quality(self):
        for url, quality in [
            ('https://audio.example.test/C400track.m4a', 'm4a'),
            ('https://audio.example.test/M500track.mp3', '128'),
            ('https://audio.example.test/M800track.mp3', '320'),
        ]:
            self.assertEqual(quality, qqmusic_queue_quality(url))
            self.assertEqual(url, strip_qqmusic_source(url))

    def test_invalid_new_quality_is_rejected(self):
        with self.assertRaises(ValueError):
            encode_qqmusic_source('lossless')
