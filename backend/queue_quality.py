"""Requested QQ quality independent of an expiring or not-yet-resolved URL."""

QQMUSIC_QUALITIES = ('m4a', '128', '320')
_PREFIX = 'tsbot-qqmusic-quality:'


def encode_qqmusic_source(quality: str, url: str = '') -> str:
    if quality not in QQMUSIC_QUALITIES:
        raise ValueError('Unsupported QQ Music quality')
    return f'{_PREFIX}{quality}|{url}'


def qqmusic_queue_quality(source: str) -> str:
    if source.startswith(_PREFIX):
        quality = source[len(_PREFIX):].partition('|')[0]
        return quality if quality in QQMUSIC_QUALITIES else '320'
    # Compatibility with queue entries created before explicit metadata existed.
    return 'm4a' if '/C400' in source else '128' if '/M500' in source else '320'


def strip_qqmusic_source(source: str) -> str:
    return source[len(_PREFIX):].partition('|')[2] if source.startswith(_PREFIX) else source
