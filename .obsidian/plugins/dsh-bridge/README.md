# DSH Bridge（Obsidian 插件）

把 Obsidian 当前笔记或选中内容发送给本机运行的 **DeepSeek Harness (DSH)**，由 DSH 侧的 Host 插件接收并注入对话，实现 Obsidian ↔ DSH 双向协作。

> 插件 id 为 `dsh-bridge`，在 Obsidian 里显示的插件名为 **DSH**，因此命令面板中显示为 `DSH: 发送当前笔记`、`DSH: 发送选中内容`（Obsidian 会自动在命令名前加「插件名: 」前缀）。

- 纯 CommonJS 单文件，**无构建步骤、无第三方依赖**
- 仅支持 Obsidian **桌面端**（Electron / macOS），`manifest.json` 里 `isDesktopOnly: true`
- 网络请求使用 Obsidian 自带 `requestUrl`（不受 CORS 限制），不发 `fetch`

## 文件

| 文件 | 说明 |
| --- | --- |
| `manifest.json` | 插件清单（id `dsh-bridge`，minAppVersion 1.4.0，桌面端专用） |
| `main.js` | 全部逻辑：命令 / Ribbon / 指令 Modal / 设置页 / HTTP 发送 |
| `styles.css` | 发送 Modal 的少量样式 |
| `README.md` | 本文件 |

安装位置：`<vault>/.obsidian/plugins/dsh-bridge/`

## 首次使用（用户需要做什么）

1. 打开 Obsidian → **设置 → 第三方插件（社区插件）** → 关闭「安全模式 / 限制模式」（若尚未关闭）。
2. 在「已安装插件」列表里找到 **DSH**，打开开关。（本仓库已把 `dsh-bridge` 写入 `.obsidian/community-plugins.json`，仍需要在 UI 里确认启用。）
3. 启动 **DeepSeek Harness** 桌面应用，并确认 DSH 侧的 Obsidian 集成（Host 插件）已加载，监听默认 `http://127.0.0.1:50070`。
4. 若 DSH 已生成 `~/.dsh/integrations/dsh-obsidian/bridge.json`（形如 `{"token":"...","url":"http://127.0.0.1:50070","route":"/dsh-obsidian/note"}`），插件会**自动读取 token**，无需手动填写；否则在设置里手动填 token。
5. 点左侧 Ribbon 的「书」图标，或命令面板执行 **DSH: 发送当前笔记**，在弹窗里填（或留空）指令后回车发送。

## 功能

- **Ribbon 图标**（`book-open`）：发送当前笔记。
- **命令面板**
  - `DSH: 发送当前笔记`
  - `DSH: 发送选中内容`（没有选中时提示并回退整篇）
  - `DSH: 打开 DeepSeek Harness`
  - `DSH: 测试 DSH 连接`
  - `DSH: 新建会话（清除 sessionId）`
- **发送前 Modal**：显示笔记名与内容长度，指令输入框默认值取设置；`Enter` 直接发送，`Shift+Enter` 换行；可留空发送。
- **设置页**（设置 → DSH）
  - Endpoint（默认 `http://127.0.0.1:50070`）
  - Route（默认 `/dsh-obsidian/note`）
  - Token（留空则自动读 token 文件）
  - Token 文件路径（默认 `~/.dsh/integrations/dsh-obsidian/bridge.json`，只读）
  - 默认指令
  - 最大字符数（默认 100000，超出截断并在 Notice 说明）
  - 「测试连接」「打开 DSH」按钮

## HTTP 契约（与 DSH 侧一致）

健康检查：

```
GET {endpoint}/dsh-obsidian/ping
-> 200 {"ok":true,"version":1}
```

发送：

```
POST {endpoint}{route}
content-type: application/json
x-dsh-bridge-token: <token>

{
  "notePath": "相对 vault 的路径.md",
  "vaultPath": "/abs/path/to/vault",
  "noteTitle": "笔记名（不含 .md）",
  "content": "markdown 正文",
  "instruction": "用户指令，可为空串",
  "sessionId": "可选，上次成功返回的会话 id"
}
```

响应：成功 `200 {"ok":true,"sessionId":"session-..."}`；未授权 `401 {"ok":false,"error":"unauthorized"}`；其他失败 `{"ok":false,"error":"..."}`。

插件行为：发送前先 ping，ping 失败给出 Notice「DSH 未运行或端口不对，请先打开 DeepSeek Harness」；401 提示 token 无效；成功 Notice 显示会话 id。

## 已知限制 / 排错

- 仅桌面端；移动端 Obsidian 不加载（`isDesktopOnly`）。
- `bridge.json` 由 DSH 生成，插件**只读**，不会创建或修改它；文件不存在时静默回退到设置里的 token。
- token 文件路径支持 `~` 展开与绝对路径；iCloud 路径含中文/空格时无需转义（直接读文件，不走 shell）。
- 若 DSH 侧实际端口/路由与默认不同，优先改设置；设置里 endpoint/route 保持默认值时，插件也会采用 `bridge.json` 里的 `url`/`route`。
- 请求全部发往 `127.0.0.1`，不经过任何外部服务。

## 本地验证（开发者）

```bash
node --check main.js                     # 语法检查（require('obsidian') 只在 Obsidian 内解析）
node /tmp/dsh-obsidian-test/mock-server.js   # 本地 mock（127.0.0.1:8899），把设置 endpoint 指过去即可联调
```

mock 实现 `GET /dsh-obsidian/ping` 与 `POST /dsh-obsidian/note`，把收到的请求体追加写入 `/tmp/dsh-obsidian-test/requests.jsonl`，便于核对契约字段与 token 头。
## 验证记录（真实执行，非推断）

环境：macOS + Obsidian 1.13.7（Electron 39.8.3）+ Node v24.15.0，通过 CDP（`--remote-debugging-port=9222`）驱动真实 Obsidian 窗口。

- `node --check main.js` 通过；`manifest.json` JSON 解析通过。
- 插件被 Obsidian 成功加载：`app.plugins.plugins['dsh-bridge']` 存在，注册命令 `send-note` / `send-selection` / `open-dsh` / `test-connection` / `new-session`，Ribbon 图标 aria-label 为「DSH: 发送当前笔记」。
- 命令面板真实显示：`DSH: 发送当前笔记`、`DSH: 发送选中内容`、`DSH: 测试 DSH 连接`、`DSH: 打开 DeepSeek Harness`、`DSH: 新建会话（清除 sessionId）`。
- 发送整篇 + 选区（mock 服务）：mock 收到 `POST /dsh-obsidian/note`，header `content-type: application/json`、`x-dsh-bridge-token: test-token-abc`，body 字段 `notePath`/`vaultPath`/`noteTitle`/`content`/`instruction` 全部符合契约；成功 Notice =「DSH: 已发送（会话 session-mock-123）」。
- 超长截断：`maxChars=20` 时 Notice「内容 111 字符超过上限 20，已截断后发送」，实际 body 长度 20。
- 401：token 错误时 Notice「token 无效（401）…」；DSH 关闭时 Notice 精确为「DSH 未运行或端口不对，请先打开 DeepSeek Harness」。
- 无选中内容时发送选中：Notice「没有选中内容，改为发送整篇笔记」并回退整篇。
- 真实 DSH（无 data.json、只读 `bridge.json`）：解析出 endpoint `http://127.0.0.1:50070`、route `/dsh-obsidian/note`、64 位 token（与文件一致），命令「测试 DSH 连接」返回 Notice「连接正常（version 1）」。
- 桌面端页面 console 无 error。

截图（临时目录，可删除）：`/tmp/dsh-obsidian-test/screenshots/`（命令面板、指令 Modal、成功/401/离线 Notice、设置页、真实 ping）。
