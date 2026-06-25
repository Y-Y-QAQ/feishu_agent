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

### 1. 安装依赖

```bash
pip install uv
uv sync
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入各项配置：

```bash
cp .env.example .env
```

| 变量 | 说明 | 获取方式 |
|------|------|---------|
| `FEISHU_APP_ID` | 飞书应用 App ID | 飞书开放平台 → 应用凭证 |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret | 飞书开放平台 → 应用凭证 |
| `FEISHU_VERIFICATION_TOKEN` | 事件验证 Token | 开放平台 → 事件与回调 |
| `FEISHU_ENCRYPT_KEY` | 消息加密 Key（可为空） | 开放平台 → 事件与回调 |
| `LLM_BASE_URL` | LLM API 地址 | 模型服务商提供 |
| `LLM_API_KEY` | LLM API Key | 模型服务商提供 |
| `LLM_MODEL` | 模型名称 | 如 `deepseek-chat` |
| `BITABLE_APP_TOKEN` | 多维表格 App Token | 多维表格 URL 中提取 |
| `BITABLE_TABLE_ID` | 数据表 ID | 多维表格 API 或 URL 中提取 |
| `APPROVAL_CODE` | 审批定义 Code | 飞书审批后台 → 审批定义详情 |

### 3. 飞书应用配置

在飞书开放平台为应用开通以下权限：

- `im:message`（接收和发送消息）
- `im:message.group_at_msg`（接收群组 @ 消息）
- `bitable:app`（多维表格读写）
- `docx:document`（文档读取）
- `approval:approval`（发起审批）

开启**机器人**能力，并在「事件与回调」中订阅 `im.message.receive_v1` 事件。

### 4. 启动服务

```bash
python main.py
```

服务启动后通过 WebSocket 长连接监听飞书消息，无需公网 IP。

## 使用示例

在飞书中向机器人发送：

```
# 简历筛选
帮我筛选一下这份简历：https://xxx.feishu.cn/docx/AbCdEfGh

# 数据查询
帮我查询一下当前候选人数据
评分超过 85 分的候选人有哪些？

# 生成周报
帮我生成本周招聘工作周报
```

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
