# portable-memory

一个跨编辑器的「外挂记忆」系统：把同一份长期记忆写进各 AI 编辑器的全局记忆入口，让每个新会话都自动带上你的偏好、环境事实和工作习惯，不用每次重新讲一遍。

## 为什么需要

AI 每次开新会话都是失忆的。解决方案不是让模型记住，而是把规矩写进它启动时必读的文件。本项目提供：

1. **一份核心记忆**：精简、脱敏、跨项目通用（沟通偏好 / 代码原则 / 本机环境 / 工作习惯）。
2. **一个安装脚本**：自动识别编辑器、写入对应入口、幂等更新、不覆盖你自己写的内容。
3. **一个 WorkBuddy Skill**：在对话里就能安装、更新、卸载、查询记忆。

项目专属的架构、字段口径、踩坑史不进这里，留在各自项目的记忆目录。

## 支持的编辑器

| Key | 编辑器 | 记忆入口 | 作用域 |
|-----|--------|----------|--------|
| `workbuddy` | WorkBuddy | `~/.workbuddy/user-*/MEMORY.md` | 用户级，自动注入 |
| `claude` | Claude Code | `~/.claude/CLAUDE.md` | 用户级，自动注入 |
| `cursor` | Cursor | `~/.cursorrules` 或 `~/.cursor/rules/*.mdc` | 用户级，自动注入 |
| `codebuddy` | CodeBuddy | `~/.codebuddy/rules/*.mdc` | 用户级，注入行为因版本而异，需自测 |
| `copilot` | GitHub Copilot | `.github/copilot-instructions.md` | 项目级，每个仓库跑一次 |
| `windsurf` | Windsurf | `~/.windsurfrules` | 用户级，自动注入 |

## 安装

### 作为 WorkBuddy Skill

把整个目录放到 `~/.workbuddy/skills/portable-memory/`，或直接让 WorkBuddy 加载本仓库。之后对话里说"安装我的跨项目记忆"即可。

### 作为命令行工具

```bash
# 看看检测到哪些编辑器
python scripts/install.py --list

# 预览将写入什么（不落盘）
python scripts/install.py --all --dry-run

# 装到所有检测到的编辑器
python scripts/install.py --all

# 只装指定的
python scripts/install.py --editors workbuddy,claude
```

需要 Python 3.9+，无第三方依赖。

## 自定义记忆内容

编辑 `references/memory-core.md`，然后重新运行安装脚本。推荐保持精简——各编辑器对用户记忆有字符上限（WorkBuddy 用户级为 4000 字符）。

脚本用标记块管理内容：

```
<!-- portable-memory:START -->
...记忆正文...
<!-- portable-memory:END -->
```

标记块之外的内容不会被覆盖。

## 卸载

```bash
python scripts/install.py --uninstall --all
```

只移除标记块，你自己写的记忆保留。

## 许可

MIT
