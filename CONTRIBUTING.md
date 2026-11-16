# 参与贡献 / Contributing

欢迎用中文或英文提交 Issue 和 PR。部署验证、复现问题、改进文档和翻译都属于贡献，无需同时掌握 Python、Vue 和 Rust。

Issues and pull requests in English or Chinese are welcome. Deployment reports, bug reproduction, documentation, and translations are useful contributions too. You can work on one component at a time.

## 适合第一次贡献的任务 / Starter tasks

下面是可讨论的任务建议，不代表已有认领或已发布的 Issue。先搜索 [现有 Issue](https://github.com/yichen11818/NeteaseTSBot/issues)，避免重复；小型文档修正可以直接提交 PR。涉及行为或接口的改动，请先开 Issue 说明方案。

These are proposed starting points, not assigned issues. Search existing issues first. Small documentation fixes can go straight to a PR; discuss behavior or API changes in an issue first.

| 任务 / Task | 范围 / Scope | 验收标准 / Acceptance criteria |
| --- | --- | --- |
| 补充首次部署排障 / First-install troubleshooting | `HOWTOSTART.md` | 在干净 Linux 环境走一次预构建镜像部署；记录系统、版本、失败现象、诊断命令和有效解决步骤，隐去凭据。 / Document one reproducible setup problem, environment, diagnostic command, and verified fix without credentials. |
| 翻译外部 API 入门示例 / Translate an external API example | 新增 `docs/API.en.md`，链接至 `docs/API.md` / Add an English guide linked to the existing API reference | 覆盖 `/external/status`、`/external/search`、`/external/queue`；对照现有 API 文档核实方法、字段和 Token 用法，给出占位符请求与响应示例。 / Verify methods, fields, and token usage against the current reference; include placeholder requests and example responses. |
| 补充聊天指令示例 / Add chat-command examples | `README.en.md` | 对照中文 README 与实际指令处理代码，补充 `help`、`playlist`、`select`、`clear`、`shuffle`、`order`、`play` 的英文表格；注明歌单仅支持网易云以及选择结果的有效期。 / Check against the implementation and Chinese README; document the Netease-only playlist scope and result expiry. |

也欢迎提交 TS3/TS6 部署兼容性报告：版本、部署方式、是否成功进频道、是否成功播放、异常现象。请注明实际验证的环境，不要把未测试的平台写为已支持。

Compatibility reports are welcome: include server version, deployment method, channel join result, playback result, and any failure. Report only environments you actually tested.

## 开始修改 / Getting started

Fork 后克隆自己的仓库，从最新 `main` 创建分支。 / Fork the repository, clone your fork, and branch from an up-to-date `main`.

```bash
git clone https://github.com/<your-user>/NeteaseTSBot.git
cd NeteaseTSBot
git switch -c docs/your-change
```

| 修改内容 / Change | 主要位置 / Location | 需要的检查 / Validation |
| --- | --- | --- |
| 文档、翻译 / Docs, translations | `README*.md`, `HOWTOSTART.md`, `docs/` | 核对命令、链接和对应功能；预览 Markdown。 / Check commands, links, and feature accuracy; preview Markdown. |
| 前端 / Web UI | `web/` | `npm --prefix web ci`，然后 / then `npm --prefix web run typecheck`、`npm --prefix web test`、`npm --prefix web run build`、`npm --prefix web run build:demo`；附界面截图和手工验证步骤。 / Include screenshots and manual verification steps. |
| 后端 / Backend | `backend/`, `tests/` | 运行下方回归测试；业务行为变更补充相关用例。 / Run the regression tests below; add coverage for behavior changes. |
| 语音 / Voice | `voice-service/`, `proto/`, `vendor/` | `cargo check --manifest-path voice-service/Cargo.toml`；连接或播放改动还需 TS 实机验证。 / Also verify connection or playback changes against a real TS server. |
| 部署 / Deployment | Compose files, `Dockerfile.*`, scripts | 对改动的部署方式执行配置检查和实际启动；记录环境。 / Validate configuration and start the affected deployment; record the environment. |

### 后端开发 / Backend development

以下命令在 Linux 项目根目录执行，推荐 Python 3.11（与后端 Docker 镜像一致）。 / Run from the project root on Linux; Python 3.11 matches the backend Docker image.

```bash
python3.11 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

回归测试使用临时数据库和 mock；不需要真实 TeamSpeak 服务器或平台账号。测试通过不等于已验证真实音频播放。 / The regression tests use temporary databases and mocks; no real TeamSpeak server or platform account is needed. Passing them does not verify real audio playback.

只在验证 B 站扫码或浏览器字幕链路时额外安装 Chromium： / Install Chromium when testing Bilibili QR login or browser-based subtitle retrieval:

```bash
backend/.venv/bin/python -m playwright install chromium
```

完整服务运行方式见 [中文 README](README.md) 或 [English README](README.en.md)。 / See either README for running the full stack.

只修改前端时可使用[离线演示构建](docs/DEMO.md)，无需真实服务器或平台账号。PR 会自动运行后端回归、前端测试及类型检查、两种前端构建和 Voice 协议检查。 / The offline demo build lets you develop UI without a real server or platform account. Pull requests run regression tests, frontend tests and type checks, both web builds, and a Voice protocol check.

## 发布版本 / Publishing a release

发布说明保存在 `docs/releases/<tag>.md`（例如 `v1.0.0.md`），汇总上一版本以来的改动、关联 Issue、升级方法和实际验证范围。未实现的 Issue 子需求必须单独注明。推送版本标签前先确认同一提交的自动检查通过。

`v*` 标签触发三个服务镜像及 Linux amd64 安装包构建；两者成功后发布任务上传安装包和校验文件，并使用对应文件中的发布说明。安装包通过 `git archive` 包含全部跟踪源码，再加入 Voice 二进制和 Web 产物，因此不得把环境文件、数据库或实例数据加入 Git。

Store release notes in `docs/releases/<tag>.md`, including linked issues, upgrade instructions and the actual validation scope. Verify checks for the exact commit before pushing its version tag. Release publication waits for all three service images and the Linux bundle; the bundle contains tracked sources plus compiled assets.

## 提交 PR / Submitting a PR

- 一次解决一个问题；解释修改前后的行为，并关联对应 Issue（如有）。 / Keep one problem per PR; describe the before/after behavior and link an issue if applicable.
- 写明实际执行的检查；未验证的部分直接说明，UI 改动附截图。 / List checks you actually ran and any untested behavior; include screenshots for UI changes.
- 不提交 `tsbot.env`、数据库、真实 Cookie、Token、密码、运行日志或构建产物；示例使用占位符。 / Keep credentials, databases, runtime logs, and build output out of commits; use placeholders in examples.
- 大范围重构、新依赖、多机器人管理或协议改动先讨论边界和兼容性。 / Discuss large refactors, new dependencies, multi-bot management, or protocol changes before implementation.
- 如使用 AI 辅助，请自行理解并验证改动；描述受影响的行为和验证结果。 / If you use AI assistance, understand and verify the changes yourself; explain the affected behavior and validation.

提交代码即表示你同意按项目的 [MIT License](LICENSE) 授权该贡献。 / Contributions are provided under the project's MIT License.
