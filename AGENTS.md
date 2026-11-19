# Project operations

- The current deployment and operations entry point is [HOWTOSTART.md](HOWTOSTART.md), including the verified default Docker network and explicit local debugging configuration.
- Keep that guide, the Chinese/English README summaries, Compose files, startup scripts and `tsbot.env.example` consistent when changing deployment defaults.
- Distinguish source development, container deployment, remote build/test, production and disaster recovery. Repository checks do not verify a live deployment; do not invent host addresses or replace historical environment records.
- Multi-server operations are documented in HOWTOSTART.md under “一个项目连接多个 TeamSpeak 服务器”. Keep the server catalog generator, Web selector, cookie isolation and that guide consistent. Generated instance data and credentials must remain untracked and outside Docker build contexts.
