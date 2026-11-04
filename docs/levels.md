# TS6 用户等级（后端）

默认关闭，无前端接口，不依赖 Rust 音频服务。使用现有 httpx 依赖。
在后端环境配置以下变量并重启；门槛为累计小时数，值为预先创建的普通服务器组 ID：

```dotenv
TSBOT_LEVELS_ENABLED=true
TSBOT_LEVELS_DB=./data/levels.db
TSBOT_LEVELS_WEBQUERY_URL=http://127.0.0.1:10080
TSBOT_LEVELS_API_KEY=replace-with-dedicated-query-api-key
TSBOT_LEVELS_SERVER_ID=1
TSBOT_LEVELS_POLL_SECONDS=60
TSBOT_LEVELS_THRESHOLDS={"1":20,"10":21,"30":22,"100":23,"300":24}
TSBOT_LEVELS_PROTECTED_GROUPS=6,7
TSBOT_LEVELS_EXCLUDED_UIDS=music-bot-unique-id,other-bot-unique-id
TSBOT_LEVELS_AFK_CHANNELS=9,10
```

组 ID 均为示例。必须将所有管理员、默认、访客等不能撤销的组加入保护列表，
只能把专用等级组填入 thresholds。配置冲突时等级任务不启动，音乐服务继续运行。
等级组仅支持装饰权限（i_icon_id、i_group_sort_id、i_group_show_name_in_tree）；
每轮读取 servergrouppermlist，发现其他非零权限时停止本轮统计和变更，防止误填管理组。
机器人普通客户端无法自动识别，请明确填写 Unique ID；Query 客户端自动排除。
AFK 按频道 ID 精确匹配，子频道需要逐一配置。

## 安全部署

WebQuery 仅用于服务端出站请求，不新增 HTTP 路由，不进入现有前端设置接口。
TS6 的 `query.http.ip` 应绑定回环地址，或绑定容器私网并在防火墙仅允许后端访问；
不要发布 10080/10443 到公网。容器里的 127.0.0.1 指容器自身，应改成受限私网主机名。
IP allow list 是防洪豁免列表，不能当作访问控制。
关闭 TS6 WebQuery guest 访问，使用限定虚拟服务器、最小权限、独立 API key。
只授予读取 clientlist、读取成员组与组权限、管理专用等级组的权限；不要使用 serveradmin key。
若跨主机部署，优先 HTTPS 或加密隧道，代码保留 TLS 证书校验。
不要把含 key 的环境文件提交到版本库。

## 统计语义与恢复

独立 SQLite 文件包含 level_users（Unique ID 主键、累计秒、计算等级、连接标识、
采样时间、统计进程、是否符合统计条件、组同步状态）和 level_lease（单进程租约）。
持久化该文件，勿让不同 TS 服务器共用；SQLite 应放本机磁盘，不支持网络共享盘。
服务重启保留累计值，但新进程首个采样不计停机时长。
异常退出后其他进程最多等待三个采样周期接管。多 worker 必须使用同一绝对数据库路径。

仅两端均在线、非排除状态、连接 ID 和 lastconnected 相同的连续成功采样区间计时。
失败、缺席、AFK、重启和超过两倍轮询间隔均切断连续性；重复时间戳不会再次累计。
时钟回拨的区间不计时，应保持主机时间同步。
轮询不是精确在线事件日志：采样内 AFK 往返不可观察；上下线边界和故障期间可能少计。
不要将此数据用于需要秒级精确计费的用途。

达到门槛先添加目标组，再只移除 thresholds 中其他组；添加失败保留旧组。
每轮读取真实组状态，能恢复添加成功后进程崩溃、删除失败等部分成功情况。
synced=0 表示尚待同步；排除用户不执行组变更。离线用户下次上线再同步。
改变门槛会根据原累计秒重新计算等级。移出 thresholds 的组不再受管理，需人工处理历史组。
仅从服务端环境修改配置并重启；不提供公开的累计时间修改或组操作 API。

测试：`python -m unittest discover -s tests -p "test_levels.py"`。
全量后端回归：`python -m unittest discover -s tests`（Python 3.10+，安装 backend/requirements.txt）。
上线前在测试 TS6 实例确认当前版本支持 clientlist 的 -uid/-times 与对应组管理权限。
