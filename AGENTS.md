# Project operations

- The current deployment and operations entry point is [HOWTOSTART.md](HOWTOSTART.md), including the verified default Docker network and explicit local debugging configuration.
- Keep that guide, the Chinese/English README summaries, Compose files, startup scripts and `tsbot.env.example` consistent when changing deployment defaults.
- Distinguish source development, container deployment, remote build/test, production and disaster recovery. Repository checks do not verify a live deployment; do not invent host addresses or replace historical environment records.
