# simple-tools

个人工具与可复用技能。

## Skills

技能统一存放在 `skills/`，每个技能目录包含 `SKILL.md` 及运行所需资源。

| 技能 | 用途 |
| --- | --- |
| [ai-flight-detector](skills/ai-flight-detector/SKILL.md) | 在 Windows/macOS 上检测 Clash/Mihomo 订阅中的节点出口与 Google、Gemini、Grok、Antigravity 公开站点可达性。支持按地区、名称、数量筛选。 |
| [teaching-slideshow-video](skills/teaching-slideshow-video/SKILL.md) | 将教学稿件制作为静态配图、逐句配音和双语字幕的视频。 |
| [bilingual-article-teaching](skills/bilingual-article-teaching/SKILL.md) | 将英语文章整理为逐句双语学习稿，核对词组高亮、语法提示和易混词，可导出 Word 与字幕标注稿。 |
| [country-study-video](skills/country-study-video/SKILL.md) | 从国家名制作六年级英语双语介绍视频，默认按六年级水平优化教学稿，再制作配音与字幕。 |
| [textbook-unit-video](skills/textbook-unit-video/SKILL.md) | 将英语教材单元学习稿与补充清单经合并查重、两轮防歧义精修、冻结门禁、场景契合配图、Lily 逐句配音与 ASR 体检、双语字幕合成及新加坡 V2 风格 Word/PDF 打印讲义，端到端制作教学视频并统一规范工程目录。 |
| [bilingual-study-subtitles](skills/bilingual-study-subtitles/SKILL.md) | 根据录音与中英稿件制作 ASS/SRT 学习字幕，支持重点词高亮、语法提示和字幕烧录。 |
| [image-motion](skills/image-motion/SKILL.md) | 分析单张静态图片并通过边缘吸附算法生成克制、无缝循环的微动态 MP4/WebP 视频（支持水波、瀑布流、飘云、旗帜横幅、风车旋转、草木风摆、火焰微动、热浪折射、钟摆招牌、星光闪烁、萤火虫、落樱落叶、极光光幔、微光扫掠、透明氛围层、3%～5% 2.5D微推进与刚体锁定，并支持可选 Depth Anything V2 深度推理）。 |

制作国家介绍或课文单元视频时，将 `country-study-video` / `textbook-unit-video` 与 `bilingual-article-teaching`、`teaching-slideshow-video`、`bilingual-study-subtitles` 并排安装。依赖和字体配置见[环境说明](skills/teaching-slideshow-video/references/portability.md)。

使用节点检测技能时，可将整个技能目录复制到 Codex 的技能目录（如 `~/.codex/skills/`），或在支持技能安装的工具中指定本仓库的 `skills/ai-flight-detector` 路径。运行需要 Python 3.10+ 和系统 curl；入口会自动准备虚拟环境、依赖及官方 Mihomo 内核。

默认模式只检测公开页面。`run.py --functional antigravity --input-env SUBSCRIPTION_URL --model <agy-model-id>` 可使用已登录的 Antigravity CLI 做最小实际生成及代理路由观察，输出完整节点名、出口、耗时、原因和通过清单。需要本机已安装的 `agy`；先用 `agy models` 查询模型 ID。CLI 通过不代表 IDE 当前会话或独立 Gemini API Key 可用。
