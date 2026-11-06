"""Private, conservative polling-based TeamSpeak level accounting."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid
from urllib.parse import urlsplit

import httpx

from .logger import logger


def ids(value):
    return {int(part.strip()) for part in value.split(",") if part.strip()}


class LevelService:
    def __init__(self, settings):
        self.settings = settings
        self.owner = uuid.uuid4().hex
        self.interval = settings.levels_poll_seconds
        thresholds = json.loads(settings.levels_thresholds)
        if not isinstance(thresholds, dict) or any(type(g) is not int for g in thresholds.values()):
            raise ValueError("Thresholds must map hours to integer group IDs")
        self.thresholds = sorted((float(h) * 3600, g) for h, g in thresholds.items())
        self.protected = ids(settings.levels_protected_groups)
        self.managed = {g for _, g in self.thresholds}
        self.afk = ids(settings.levels_afk_channels)
        self.excluded = {x.strip() for x in settings.levels_excluded_uids.split(",") if x.strip()}
        url = urlsplit(settings.levels_webquery_url)
        if (self.interval < 5 or not self.thresholds or not settings.levels_api_key
                or settings.levels_server_id < 1 or url.scheme not in {"http", "https"}
                or not url.hostname or url.username or url.password or url.query or url.fragment
                or self.managed & self.protected or len(self.managed) != len(self.thresholds)
                or any(not math.isfinite(h) or h <= 0 or g <= 0 for h, g in self.thresholds)
                or len({h for h, _ in self.thresholds}) != len(self.thresholds)):
            raise ValueError("Invalid level configuration (check thresholds, protected groups and WebQuery credentials)")
        Path(settings.levels_db).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS level_users (
                    uid TEXT PRIMARY KEY, seconds REAL NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 0, session TEXT,
                    sampled REAL, owner TEXT, eligible INTEGER NOT NULL DEFAULT 0,
                    synced INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS level_lease (
                    id INTEGER PRIMARY KEY CHECK(id=1), owner TEXT, expires REAL);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.settings.levels_db, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    async def command(self, client, command, **params):
        path = f"/{self.settings.levels_server_id}/{command}"
        if command in {"servergroupaddclient", "servergroupdelclient"}:
            # Keep the write boundary restricted even if a caller bypasses tick().
            if int(params.get("sgid", 0)) not in self.managed or int(params["sgid"]) in self.protected:
                raise ValueError("Cannot modify membership of a non-level group")
            # WebQuery's documented POST format is an array of parameter sets,
            # including when this operation targets only one membership.
            response = await client.post(path, json=[params])
        elif command in {"clientlist", "servergrouplist", "servergrouppermlist", "servergroupsbyclientid"}:
            response = await client.get(path, params=params)
        else:
            raise ValueError("Unsupported level WebQuery command")
        response.raise_for_status()
        payload = response.json()
        if int(payload["status"]["code"]) != 0:
            raise RuntimeError("WebQuery command failed: " + command)
        data = payload.get("body") or []
        if not isinstance(data, list):
            raise ValueError("Invalid WebQuery response")
        return data

    def claim(self, now):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM level_lease WHERE id=1").fetchone()
            if row and row["owner"] != self.owner and row["expires"] > now:
                return False
            db.execute("INSERT OR REPLACE INTO level_lease VALUES (1,?,?)",
                       (self.owner, now + self.interval * 3))
            return True

    def account(self, clients, now):
        """One atomic snapshot. Only adjacent eligible observations earn time."""
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            lease = db.execute("SELECT * FROM level_lease WHERE id=1").fetchone()
            if not lease or lease["owner"] != self.owner or lease["expires"] <= now:
                return []
            previous = {r["uid"]: r for r in db.execute("SELECT * FROM level_users")}
            db.execute("UPDATE level_users SET eligible=0")
            targets = []
            seen = set()
            for c in clients:
                if int(c["client_type"]) != 0:
                    continue
                uid = c["client_unique_identifier"]
                if not uid or uid in seen:
                    raise ValueError("Missing or duplicate Unique ID")
                seen.add(uid)
                eligible = uid not in self.excluded and int(c["cid"]) not in self.afk
                connection = f'{c["clid"]}:{c["client_lastconnected"]}'
                old = previous.get(uid)
                total = old["seconds"] if old else 0
                if (old and eligible and old["eligible"] and old["owner"] == self.owner
                        and old["session"] == connection and old["sampled"] is not None):
                    elapsed = now - old["sampled"]
                    if 0 < elapsed <= self.interval * 2:
                        total += elapsed
                    elif elapsed < 0:
                        eligible = False  # break continuity on wall-clock rollback
                level = sum(total >= h for h, _ in self.thresholds)
                db.execute("INSERT OR REPLACE INTO level_users VALUES (?,?,?,?,?,?,?,?)",
                           (uid, total, level, connection, now, self.owner, int(eligible), 0,))
                if eligible:
                    targets.append((uid, int(c["client_database_id"]), level))
            return targets

    async def tick(self, client):
        if not self.claim(time.time()):
            return
        try:
            # Only regular server groups may be assigned, never template/query groups.
            groups = await self.command(client, "servergrouplist")
            group_types = {int(g["sgid"]): int(g["type"]) for g in groups}
            if any(group_types.get(group) != 1 for group in self.managed):
                raise ValueError("Level groups must be regular server groups (type=1)")
            # Protection thresholds constrain who may modify a group; they do not
            # grant its members the corresponding powers. Keep capability grants denied.
            badge_permissions = {
                "i_icon_id", "i_group_sort_id", "i_group_show_name_in_tree",
                "i_group_needed_modify_power", "i_group_needed_member_add_power",
                "i_group_needed_member_remove_power", "b_group_is_permanent",
            }
            for group in sorted(self.managed):
                permissions = await self.command(client, "servergrouppermlist", sgid=group,
                                                 **{"-permsid": ""})
                if any(p.get("permsid") not in badge_permissions
                       and int(p["permvalue"]) != 0 for p in permissions):
                    raise ValueError("Level groups must contain only badge/protection permissions")
            clients = await self.command(client, "clientlist", **{"-uid": "", "-times": ""})
            targets = self.account(clients, time.time())
        except Exception:
            with self.db() as db:
                db.execute("UPDATE level_users SET eligible=0 WHERE owner=?", (self.owner,))
            raise
        for uid, database_id, level in targets:
            # Refresh actual membership on every retry; DB flags never stand in for TS state.
            if not self.claim(time.time()):
                return
            try:
                groups = await self.command(client, "servergroupsbyclientid", cldbid=database_id)
                present = {int(g["sgid"]) for g in groups}
                desired = self.thresholds[level - 1][1] if level else None
                if desired is not None and desired not in present:
                    await self.command(client, "servergroupaddclient", sgid=desired, cldbid=database_id)
                for group in sorted((present & self.managed) - {desired}):
                    await self.command(client, "servergroupdelclient", sgid=group, cldbid=database_id)
            except Exception as exc:
                # account() left this user unsynced. Retry next poll without
                # preventing unrelated users from receiving their level group.
                logger.warning("Level membership sync failed: %s", type(exc).__name__)
                continue
            with self.db() as db:
                db.execute("UPDATE level_users SET synced=1 WHERE uid=?", (uid,))

    async def run(self):
        # No redirects or environment proxies: never forward the API key elsewhere.
        async with httpx.AsyncClient(base_url=self.settings.levels_webquery_url.rstrip("/"),
                                     headers={"x-api-key": self.settings.levels_api_key},
                                     timeout=10, trust_env=False, follow_redirects=False) as client:
            try:
                while True:
                    try:
                        await self.tick(client)
                    except Exception as exc:
                        # Exception text may contain request URLs or secrets; log only type.
                        logger.warning("Level polling failed: %s", type(exc).__name__)
                    await asyncio.sleep(self.interval)
            finally:
                with self.db() as db:
                    db.execute("UPDATE level_users SET eligible=0 WHERE owner=?", (self.owner,))
                    db.execute("DELETE FROM level_lease WHERE owner=?", (self.owner,))
