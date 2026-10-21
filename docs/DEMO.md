# GitHub Pages 在线体验

前端可以静态部署到 GitHub Pages。Pages 不运行 Python 后端、Rust Voice 或 TeamSpeak 连接；这里发布的是同一套 Vue 界面的交互演示。

## 本地运行

在项目根目录执行：

```bash
npm --prefix web ci
npm --prefix web run build:demo
npm --prefix web run preview:demo
```

访问终端显示的地址，并保留 `/NeteaseTSBot/` 子目录。演示默认使用哈希路由，例如 `/NeteaseTSBot/#/queue`，直接打开或刷新子页面都不需要服务器路由重写。

演示支持三平台模拟搜索、添加/移除/重排队列、模拟播放暂停和进度、歌词、示例歌单、历史记录、本地收藏和部署向导。队列与配置只保存在当前页面内存中，刷新即重置；收藏、搜索历史和主题使用浏览器本地存储。

界面明确标注模拟数据，不播放真实音频，不连接音乐平台或 TeamSpeak。演示构建中的 API 只调用本地适配器；未实现的接口会明确报错，不会回退到真实请求。平台登录界面不展示，也不接收 Cookie、密码或上传文件。

## 发布到 GitHub Pages

1. 合入 `.github/workflows/pages.yml` 与前端改动。
2. 在 GitHub 仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。
3. 在 **Actions → Demo on GitHub Pages → Run workflow** 运行，或在 `main` 上推送前端变更。
4. 工作流通过测试、类型检查和演示构建后发布 `web/dist-demo`。部署成功时，以 Actions 返回的 `page_url` 为准，再将地址加入 README 和仓库 About。

本仓库的[在线体验](https://yichen11818.github.io/NeteaseTSBot/)已通过 GitHub Actions 发布。Fork 的工作流会根据仓库名设置子目录；如果使用用户根站点或自定义域名，需要将工作流中的 `VITE_BASE_PATH` 改为 `/`。

## 真实部署保持独立

`npm --prefix web run build` 仍输出 `web/dist`，使用真实 `/api` 和 history 路由；现有 Docker/Nginx 路径不变。`build:demo` 单独输出 `web/dist-demo`，避免将演示产物混入生产容器。

`VITE_DEMO_MODE` 是构建时开关，不能用 URL 参数打开或关闭。不要给演示构建配置真实 API Token、Cookie 或平台凭据；公开前端构建不应包含这些信息。

## 部署向导与连接诊断

真实部署首次登录改密后进入“设置 → 部署向导”（`/settings?group=setup`），已有管理员可以在设置内切换到部署向导。旧 `/setup` 地址自动跳转到该分类。前两步只保存 TeamSpeak 与网易云 API 配置，最后一步应用所有已保存的配置，等待 Voice 确认配置版本后检查连接。

`GET /admin/diagnostics` 仅管理员会话可访问，分别检查数据库、待应用配置、Voice gRPC、TeamSpeak 会话和可选的网易云 API。Voice 检查最多等待 3 秒；音乐 API 使用 4 秒 HTTP 超时，两者并发执行。错误响应不会包含上游异常文本、地址中的凭据或 Cookie。

TeamSpeak 状态由 Voice 通过新增的可选 protobuf 字段报告：旧版 Voice 会显示“无法确认”，不会把 gRPC 可达当作 TeamSpeak 已连接。连接成功也不保证已进入预期频道或歌曲可播放，最后仍需点播一首具备账号权限的曲目验证。

QQ 音乐和 B 站不依赖网易云 API；暂不使用网易云时，该项警告不会阻止必要连接显示就绪。

## 验证命令

```bash
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run build
npm --prefix web run build:demo
python -m unittest discover -s tests -p 'test_*.py'
cargo check --manifest-path voice-service/Cargo.toml
```

后端命令使用已安装 `backend/requirements.txt` 的 Python 环境。PR 的 `Pull request checks` 工作流自动执行后端回归测试、前端检查与两种构建，以及 Voice 协议构建检查；无需访问真实平台账号。
