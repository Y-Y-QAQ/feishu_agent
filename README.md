# 飞书招聘助手 Agent

基于 LangGraph ReAct 架构构建的飞书 AI Agent，通过飞书 WebSocket 长连接监听消息，自动完成简历筛选、数据查询、周报生成等招聘相关任务。

## 功能

| Skill | 触发关键词 | 功能描述 |
|-------|-----------|---------|
| `resume_screening` | 简历、筛简历、评估候选人 | 读取飞书文档中的简历，AI 多维度评分，结果写入多维表格，高分自动发起面试审批 |
| `data_query` | 数据、查询、候选人、统计 | 从多维表格读取候选人数据，AI 分析后回复结构化结论 |
| `weekly_report` | 周报、工作总结、生成报告 | 从多维表格读取候选人评估数据，自动生成本周招聘工作周报 |

## 架构

```
用户发飞书消息
    ↓
main.py（WebSocket 接入，消息去重，后台线程池分发）
    ↓
agent/router.py（LLM 路由：扫描 skills/ 目录，选择匹配 Skill）
    ↓
agent/executor.py（加载 Skill 上下文，构建 ReAct Agent，注入工具）
    ↓
tools/（飞书工具：消息、多维表格、文档、审批）
    ↓
飞书 API（发送回复、写入数据、发起审批）
```

### 核心设计

- **WebSocket 长连接**：无需公网 IP，本地运行即可接收飞书消息
- **LLM 路由**：读取各 Skill 的 frontmatter 描述，由 LLM 判断意图，动态路由，新增 Skill 无需改代码
- **ReAct Agent**：基于 LangGraph `create_react_agent`，Agent 自主决定工具调用顺序和次数
- **Skill 按需加载**：路由阶段只读轻量 frontmatter，执行阶段才懒加载完整 skill.md、refs、templates
- **工具幂等设计**：send_message、write_bitable_record、create_approval 均有去重保护，防止 Agent 重复调用产生副作用
- **消息去重**：基于 message_id + threading.Lock 防止飞书 at-least-once 重投导致重复处理
- **递归上限**：Agent 推理轮数限制为 10 轮，防止异常循环

## 目录结构

```
feishu_agent/
├── main.py                  # 主入口，WebSocket 监听
├── agent/
│   ├── router.py            # LLM 路由器
│   └── executor.py          # Skill 执行器（ReAct Agent）
├── tools/
│   ├── __init__.py          # 工具注册中心
│   ├── feishu_message.py    # 消息发送工具
│   ├── feishu_bitable.py    # 多维表格读写工具
│   ├── feishu_document.py   # 飞书文档读取工具
│   └── feishu_approval.py   # 审批发起工具
├── skills/
│   ├── resume_screening/    # 简历筛选 Skill
│   │   ├── skill.md         # 执行步骤与注意事项
│   │   ├── refs/            # 评分标准等参考资料
│   │   └── templates/       # 评估报告模板
│   ├── data_query/          # 数据查询 Skill
│   │   ├── skill.md
│   │   └── refs/            # 表格字段说明
│   └── weekly_report/       # 周报生成 Skill
│       ├── skill.md
│       ├── refs/            # 表格字段说明
│       └── templates/       # 周报模板
├── config/
│   └── settings.py          # 环境变量读取
├── .env                     # 本地环境变量（不提交）
├── .env.example             # 环境变量模板
└── pyproject.toml           # 项目依赖
```

## 快速开始

### 环境要求

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)（推荐）或 pip
- 飞书企业账号，且有权限创建应用、多维表格

### 1. 克隆并安装依赖

```bash
git clone https://github.com/Y-Y-QAQ/feishu_agent.git
cd feishu_agent
pip install uv
uv sync
```

Windows PowerShell 复制环境变量文件：

```powershell
copy .env.example .env
```

macOS / Linux：

```bash
cp .env.example .env
```

### 2. 前置准备

#### 2.1 创建多维表格（候选人评估表）

在飞书中新建一个多维表格，**字段名必须与下表完全一致**（字段名错误会导致写入失败）：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 候选人姓名 | 文本 | |
| 目标岗位 | 文本 | |
| 综合评分 | 数字 | 0-100 |
| 推荐结论 | 单选 | 选项：推荐约面试 / 暂不推荐 / 待补充材料 |
| 评估日期 | 日期 | 代码会自动写入当天日期 |
| 评估报告 | 文本 | AI 生成的完整评估内容 |

**授权应用访问表格：** 打开多维表格 → 右上角「分享」→ 添加你的飞书应用（机器人）为协作者，权限选「可编辑」。未授权时读写 API 会报权限错误。

#### 2.2 获取 BITABLE_APP_TOKEN 和 BITABLE_TABLE_ID

**app_token** 从多维表格 URL 中提取：

```
https://xxx.feishu.cn/base/OAY4bd38sahk1hskYKwcaFqWnSc
                              ↑ 这一段就是 BITABLE_APP_TOKEN
```

**table_id** 不在 URL 里，通过飞书开放平台 API 获取：

1. 打开 [API 调试台](https://open.feishu.cn/api-explorer/)
2. 选择接口：`bitable/v1/apps/:app_token/tables`（列出数据表）
3. 填入上一步的 `app_token`，调用后返回的 `table_id` 即为 `BITABLE_TABLE_ID`

#### 2.3 配置环境变量

编辑 `.env`，填入各项配置：

| 变量 | 必填 | 说明 | 获取方式 |
|------|------|------|---------|
| `FEISHU_APP_ID` | 是 | 飞书应用 App ID | 开放平台 → 凭证与基础信息 |
| `FEISHU_APP_SECRET` | 是 | 飞书应用 App Secret | 开放平台 → 凭证与基础信息 |
| `FEISHU_VERIFICATION_TOKEN` | 是 | 事件验证 Token | 开放平台 → 事件与回调 → 加密策略 |
| `FEISHU_ENCRYPT_KEY` | 否 | 消息加密 Key | 未启用加密时留空 |
| `LLM_BASE_URL` | 是 | LLM API 地址 | 模型服务商提供，需兼容 OpenAI 接口 |
| `LLM_API_KEY` | 是 | LLM API Key | 模型服务商提供 |
| `LLM_MODEL` | 是 | 模型名称 | 如 `deepseek-chat`、`qwen-max` |
| `BITABLE_APP_TOKEN` | 是 | 多维表格 App Token | 见 2.2 |
| `BITABLE_TABLE_ID` | 是 | 数据表 ID | 见 2.2 |
| `APPROVAL_CODE` | 否 | 审批定义 Code | 仅简历筛选发起审批时需要，见 3.4 |

### 3. 飞书应用配置

#### 3.1 开通权限

在飞书开放平台 → 权限管理，为应用开通以下权限（与当前项目实际使用一致）：

| 权限标识 | 说明 | 身份类型 | 用途 |
|---------|------|---------|------|
| `im:message` | 获取与发送单聊、群组消息 | 应用身份 | 机器人收发消息 |
| `im:message.p2p_msg:readonly` | 读取用户发给机器人的单聊消息 | 应用身份 | 接收私聊消息 |
| `im:message.group_at_msg.include_bot:readonly` | 获取群组中 @ 当前机器人的消息 | 应用身份 | 接收群聊 @ 消息 |
| `bitable:app` | 查看、评论、编辑和管理多维表格 | 应用身份 | 读写候选人数据 |
| `docx:document:readonly` | 查看新版文档 | 应用身份 | 读取简历文档内容 |
| `approval:approval` | 查看、创建、更新、删除审批应用相关信息 | 应用身份 | 发起面试邀约审批 |
| `approval:instance:write` | 操作审批实例 | 用户身份 | 创建/操作审批实例 |

> 审批相关权限建议同时开通 `approval:approval`（应用身份）和 `approval:instance:write`（用户身份），避免发起审批时权限不足。

#### 3.2 开启机器人能力

在「应用能力」中开启**机器人**。

#### 3.3 配置事件订阅（WebSocket 长连接）

**重要：必须按以下顺序操作，否则 WebSocket 配置保存会失败。**

1. 先在本地启动服务（见第 4 步），确保终端出现 `飞书 Agent 已启动，等待消息...`
2. 打开飞书开放平台 → 事件与回调 → 选择 **使用长连接接收事件**
3. 订阅事件：`im.message.receive_v1`
4. 点击保存（此时飞书会检测本地是否有活跃的 WebSocket 连接）
5. 将 `FEISHU_VERIFICATION_TOKEN` 填入 `.env`（`FEISHU_ENCRYPT_KEY` 未启用加密时可留空）

#### 3.4 配置审批定义（可选）

仅在使用 `resume_screening` 简历筛选且需要自动发起面试审批时配置。

1. 打开飞书审批后台，创建「面试邀约审批」
2. 表单字段（名称必须一致）：候选人姓名、目标岗位、综合评分、推荐理由
3. 流程设计：审批人设为「指定成员」，选择审批接收人
4. 发布审批，从 URL 中获取 `definitionCode`，填入 `.env` 的 `APPROVAL_CODE`

**注意：** `tools/feishu_approval.py` 中硬编码了审批表单的控件 ID（`WIDGET_MAP`）。如果你新建的审批表单控件 ID 不同，需要调用飞书 API 获取真实 widget ID 并更新代码：

```
GET /open-apis/approval/v4/approvals/{approval_code}
```

返回的 `form` 字段中包含每个控件的 `id` 和 `name`，将 `name` 与 `id` 的对应关系更新到 `WIDGET_MAP` 即可。

#### 3.5 发布应用并添加机器人

1. 在开放平台创建版本并发布应用（至少发布到当前企业）
2. 在飞书群聊中添加机器人，或直接与机器人私聊
3. 群聊中使用时需要 **@机器人** 才会触发消息接收

### 4. 启动服务

```bash
uv run python main.py
```

或使用已激活的虚拟环境：

```bash
# Windows
.venv\Scripts\activate
python main.py

# macOS / Linux
source .venv/bin/activate
python main.py
```

启动成功后终端输出：

```
飞书 Agent 已启动，等待消息...
```

服务通过 WebSocket 长连接监听飞书消息，无需公网 IP。**保持此终端窗口运行，不要关闭。**

### 5. 验证是否配置成功

在飞书中向机器人发送：

```
帮我查询一下当前候选人数据
```

若机器人在 30 秒内回复表格数据分析结果，说明整体链路配置成功。

## 使用示例

在飞书中向机器人发送：

```
# 简历筛选（需准备飞书文档格式的简历，并确保应用有文档读取权限）
帮我筛选一下这份简历：https://xxx.feishu.cn/docx/AbCdEfGh

# 数据查询
帮我查询一下当前候选人数据
评分超过 85 分的候选人有哪些？

# 生成周报
帮我生成本周招聘工作周报
```

**简历文档权限：** 简历必须是飞书文档（docx），不能是上传的 PDF 附件。需将文档分享给应用可读，或在开放平台开通文档权限后由应用直接访问。

## 常见问题

| 现象 | 可能原因 | 解决方法 |
|------|---------|---------|
| WebSocket 配置保存失败 | 本地服务未启动 | 先运行 `python main.py`，再保存长连接配置 |
| 机器人无回复 | 事件未订阅或服务未运行 | 检查 `im.message.receive_v1` 是否订阅，终端是否保持运行 |
| 群聊发消息无反应 | 未 @ 机器人 | 群聊中需要 @机器人 发送消息 |
| 多维表格读写失败 | 应用未授权访问表格 | 将应用添加为多维表格协作者 |
| 写入表格报 FieldNameNotFound | 字段名与代码不一致 | 对照 2.1 检查字段名和类型 |
| 读取简历失败 | 文档权限不足 | 分享文档给应用，或检查 `docx:document:readonly` 权限 |
| 审批发起失败 | 未配置或 widget ID 不匹配 | 检查 `APPROVAL_CODE` 和 `feishu_approval.py` 中的 `WIDGET_MAP` |
| 同一条消息回复两次 | 飞书消息重投 | 代码已做去重，重启服务后应恢复正常 |
| LLM 调用超时 | 模型服务不可达 | 检查 `LLM_BASE_URL` 和 `LLM_API_KEY` 是否正确 |

## 扩展新 Skill

只需在 `skills/` 下新建目录，添加 `skill.md`（含 YAML frontmatter），无需修改任何代码：

```
skills/
└── your_skill/
    ├── skill.md        # 必须，含 name 和 description frontmatter
    ├── refs/           # 可选，参考知识文件
    └── templates/      # 可选，输出模板文件
```

`skill.md` frontmatter 格式：

```yaml
---
name: your_skill
description: >-
  一句话描述该 Skill 的功能和触发条件，Router 据此路由。
---
```

## 技术栈

- **运行时**：Python 3.11+
- **Agent 框架**：LangGraph + LangChain
- **LLM**：兼容 OpenAI 接口的任意模型（DeepSeek、Qwen 等）
- **飞书 SDK**：lark-oapi
