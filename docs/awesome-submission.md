# 投稿清单：awesome-deepseek-harness 收录

这个文件是把 portable-memory 提交到 awesome 列表的操作清单。
带 `<...>` 的地方需要你自己填，其余已按仓库现状准备好。

目标仓库：`Dominic789654/awesome-deepseek-harness`（明确收录 MCP servers 类别）。
该列表要求：仓库公开、带 dsh 相关 topic、README 说明与 DSH 的关系、中英文条目同步、纯新增行。

## 0. 前置条件（必须按顺序）

```bash
# 在 F:/2025Code/portable-memory 下
git remote add origin https://github.com/<你的用户名>/portable-memory.git
git push -u origin main
```

推上去之后，在 GitHub 网页做两件事：

1. Settings → About → Description 填一句包含 `DeepSeek Harness` 或 `dsh` 的描述，例如：
   `Cross-project long-term memory MCP server for DeepSeek Harness, with project isolation and a Web UI.`
2. Settings → Topics 添加：`dsh`（再加 `dsh-plugin`、`mcp` 可选）

仓库至少存在 1 天后再提 PR——部分 registry 的 CI 会检查仓库年龄。

## 1. PR 条目填空骨架

Fork 目标仓库后，在 `README.md`（英文）和 `README.zh-CN.md`（中文）各加**一行**，
放在 `MCP servers` 分类下。只加行，不改任何现有行。

英文（README.md）：

```markdown
- [<你的用户名>/portable-memory](https://github.com/<你的用户名>/portable-memory) — Local cross-project long-term memory MCP server with project isolation, sessions, and a Web UI; usable from DeepSeek Harness via MCP.
```

中文（README.zh-CN.md，注意分隔符是 `——` 两个破折号）：

```markdown
- [<你的用户名>/portable-memory](https://github.com/<你的用户名>/portable-memory) —— 本地跨项目长期记忆 MCP 服务，支持项目隔离、会话管理与 Web 面板，可通过 MCP 接入 DeepSeek Harness。
```

检查：`git diff` 里每一行都以 `+` 开头，没有任何被删改的现有行。

## 2. 提交 PR

```bash
git checkout -b add-portable-memory
git add README.md README.zh-CN.md
git commit -m "docs: add portable-memory to MCP servers"
git push origin add-portable-memory
```

在 GitHub 网页点 New pull request，标题：

```
docs: add portable-memory
```

PR 描述可写：

> portable-memory is a standalone Python MCP server providing cross-project
> long-term memory. It is usable from DeepSeek Harness via `setup_editors.py
> --editors dsh`. Added to both README.md and README.zh-CN.md under MCP servers.

保持 "Allow edits by maintainers" 勾选。

## 3. 提交后

- PR 会跑自动检查：链接可达、topic 存在、描述非空、只改两个 README、纯新增行。
- 失败会在 PR 里留言告诉你具体哪条，改完 push 到同一分支即可，不用重开 PR。
- 合并后目录站约 1 天刷新，届时会出现在列表里。

## 4. 可选：换一个更严格的目录

如果想进带 Curated 标记的 `cccakeee/awesome-dsh-plugins`，需要额外证据：
`dsh.bundle` 声明或可复现的 `dsh plugin --profile ... add ...` 安装命令。
这个目录的门槛更高，建议先过第一个列表，再考虑。
