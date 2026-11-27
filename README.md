# portable-memory

跨编辑器、跨会话的**本地外挂记忆系统**。一个 Python 服务负责捕获、去重、检索和召回，通过 MCP / REST 暴露给所有 AI 编辑器；DeepSeek Harness 通过上层插件适配。带**本地 Web 面板**，可可视化管理项目、会话和记忆。

零第三方依赖（Python 3.9+ 标准库即可运行），数据全部留在你本机。

## Web 面板

启动服务后打开 `http://127.0.0.1:8765/ui`：

- **项目切换**：顶部列出所有项目，点击即可查看该项目的记忆，互不干扰；
- **会话管理**：左侧记录每次协作，可新建、结束、删除会话；
- **记忆增删查改**：搜索、添加、编辑、删除记忆，按类型/标签过滤；
- **统计**：记忆总数、项目数、累计访问次数。

如果设置了 `PMEM_TOKEN`，在页面右上角输入令牌即可。

## 和静态记忆文件的区别

| | 静态 CLAUDE.md / MEMORY.md | portable-memory |
|---|---|---|
| 记录 | 手动写 | hook / MCP 自动捕获 |
| 检索 | 全量塞进上下文 | BM25 按需召回相关项 |
| 去重 | 无 | SHA-256 内容指纹 |
| 隐私 | 无 | 写入前自动脱敏密钥 |
| 时效 | 永久有效、会过时 | 时间衰减 + 重要性排序 |
| 纠错 | 手工改文件 | `memory_delete` / `forget` |
| 跨编辑器 | 每个工具一份 | 一个服务，MCP 通用 |

## 架构（两层）

```
上层：DSH 插件 / WorkBuddy Skill  ── 适配各编辑器的事件与注入时机
                    │ MCP
下层：Python 记忆服务（本仓库）  ── 捕获 → 处理 → 召回 → SQLite 存储
```

底层编辑器无关，换框架不用重写；上层只是一层薄适配器。

## 快速开始

```bash
git clone <this-repo>
cd portable-memory

# 直接跑 CLI（无需安装依赖）
export PYTHONPATH=$PWD/src
python -m portable_memory remember "分页默认 10 条，不开特例" --type rule
python -m portable_memory recall "分页 默认多少条"
python -m portable_memory stats
```

Windows 用 `set PYTHONPATH=%CD%\src` 或在安装脚本里自动配。

### 项目隔离与自动识别

在每个项目根目录跑一次 `init`，生成 `.pmem.json` 标记文件：

```bash
cd /path/to/my-project
python -m portable_memory init my-project --name "我的项目"
```

之后在这个目录（含子目录）里，CLI 和 MCP 会自动识别项目，记忆自动归到对应 namespace——**换项目不用手动切**。面板顶部也能随时手动切换查看。

```bash
python -m portable_memory project list          # 列出所有项目
python -m portable_memory project add --namespace x --name "X"   # 手动注册
```

### 会话管理

```bash
python -m portable_memory session start --title "支付模块联调"
python -m portable_memory remember "支付回调要用幂等键" --session 1 --type decision
python -m portable_memory session close --id 1 --summary "确定幂等方案"
python -m portable_memory session list
```

MCP 客户端可用 `session_start` / `session_end` 工具。会话记录标题、起止时间、摘要和关联记忆数，可在面板回溯。

### 安装为命令

```bash
pip install -e .
pmem serve      # 启动 HTTP 服务
pmem mcp        # 以 MCP stdio 方式运行（供编辑器调用）
```

## 接入编辑器

```bash
python scripts/setup_editors.py --list
python scripts/setup_editors.py --all --dry-run
python scripts/setup_editors.py --all --repo-root /path/to/project
```

支持：Claude Code、Cursor、Windsurf、WorkBuddy、DeepSeek Harness、GitHub Copilot。
脚本把 MCP 服务注册到各自的配置文件，指向 `python -m portable_memory mcp`。

## REST API

服务默认监听 `127.0.0.1:8765`，设置 `PMEM_TOKEN` 后需 `Authorization: Bearer <token>`。

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/remember` | 写入 `{content, type, namespace, tags, importance}` |
| GET | `/recall?query=&namespace=&limit=` | 检索（BM25 + 衰减） |
| GET | `/list?namespace=` | 列出记忆 |
| GET | `/stats` | 统计 |
| DELETE | `/memory/{id}` | 软删除 |
| PUT | `/memory/{id}` | 编辑记忆内容 |
| POST | `/export` | 导出 Markdown 镜像 |
| POST | `/seed` | 从 Markdown 模板批量导入 |
| GET | `/projects` | 列出项目 |
| POST | `/projects/register` | 注册项目 |
| GET | `/sessions?namespace=` | 列出会话 |
| POST | `/sessions` | 新建会话 |
| POST | `/sessions/close` | 结束会话 |
| DELETE | `/sessions/{id}` | 删除会话 |

## MCP 工具

编辑器可直接调用：`memory_add`、`memory_recall`、`memory_list`、`memory_delete`、`session_start`、`session_end`、`project_list`。

建议使用时机：会话开始时 `memory_recall` 当前任务；用户明确表达偏好时 `memory_add`；协作开始时 `session_start`，结束时 `session_end` 并写摘要。

namespace 缺省时自动从当前目录的 `.pmem.json` 推断，所以同一套 MCP 配置跨项目复用，记忆天然隔离。

## 配置项

全部通过环境变量，无需配置文件：

| 变量 | 默认 | 说明 |
|------|------|------|
| `PMEM_DATA_DIR` | `~/.portable-memory` | 数据目录 |
| `PMEM_HOST` / `PMEM_PORT` | `127.0.0.1` / `8765` | HTTP 监听 |
| `PMEM_TOKEN` | 空 | Bearer token |
| `PMEM_HALF_LIFE_DAYS` | `30` | 时间衰减半衰期 |
| `PMEM_DEFAULT_LIMIT` / `PMEM_MAX_LIMIT` | `8` / `50` | 召回条数 |

## 检索原理

无向量库、无 LLM 调用：

1. 中文按 bigram、英文按词切分；
2. BM25 计算词法相关性；
3. 叠加时间衰减（半衰期可配）、访问频次、重要性；
4. 返回带分数明细的结果，可解释为什么召回。

## 测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## 目录

```
src/portable_memory/
  config.py     配置
  db.py         SQLite 存储、去重、脱敏、导入导出
  workspace.py  项目注册、会话管理、.pmem.json 自动识别
  pipeline.py   捕获/处理/召回、BM25、衰减
  server.py     REST 服务 + Web 面板托管
  mcp.py        MCP stdio 桥接
  cli.py        命令行入口
src/webui/
  index.html    零依赖可视化面板
scripts/
  setup_editors.py   编辑器 MCP 自动配置
dsh-plugin/     DeepSeek Harness 适配层（骨架）
tests/          单元测试
```

## License

MIT
