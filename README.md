# simple-tools

个人工具与可复用技能。

## Skills

技能统一存放在 `skills/`，每个技能目录包含 `SKILL.md` 及运行所需资源。

| 技能 | 用途 |
| --- | --- |
| [ai-flight-detector](skills/ai-flight-detector/SKILL.md) | 在 Windows/macOS 上检测 Clash/Mihomo 订阅中的节点出口与 Google、Gemini、Grok、Antigravity 公开站点可达性。支持按地区、名称、数量筛选。 |
| [teaching-slideshow-video](skills/teaching-slideshow-video/SKILL.md) | 将教学稿件制作为静态配图、逐句配音和双语字幕的视频。 |
| [bilingual-study-subtitles](skills/bilingual-study-subtitles/SKILL.md) | 根据录音与中英稿件制作 ASS/SRT 学习字幕，支持重点词高亮、语法提示和字幕烧录。 |

制作教学视频时，将两个教学技能目录并排安装。依赖和字体配置见[环境说明](skills/teaching-slideshow-video/references/portability.md)。

使用节点检测技能时，可将整个技能目录复制到 Codex 的技能目录（如 `~/.codex/skills/`），或在支持技能安装的工具中指定本仓库的 `skills/ai-flight-detector` 路径。运行需要 Python 3.10+ 和系统 curl；入口会自动准备虚拟环境、依赖及官方 Mihomo 内核。

节点检测不等于账号或模型调用验证。Antigravity 目前仅检测公开站点，无法据此确认登录后可用性。
