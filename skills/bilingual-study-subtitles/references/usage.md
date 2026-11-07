# 时间轴、样式与脚本使用

脚本负责确定性排版、格式导出和普通视频烧录；**不会把未对齐原稿自动变成可靠时间轴**。先按 alignment.md 完成识别、匹配和异常复核。

## 输入时间轴

JSON 顶层为数组，`start` 单位为视频全局秒。原稿里的备注归到相关句子，不把备注本身当成指令。必填字段是 `start`、`en`、`zh`；其他字段可省略。

```json
[
  {
    "start": 1.24,
    "en": "It is an exciting journey.",
    "zh": "这是一段令人兴奋的旅程。",
    "highlight_en": ["exciting"],
    "highlight_zh": ["令人兴奋"],
    "notes": ["exciting：令人兴奋的；刺激的。修饰事物的特征。"]
  },
  {
    "start": 5.68,
    "en": "We are excited.",
    "zh": "我们感到很兴奋。",
    "highlight_en": ["excited"],
    "notes": ["excited：感到兴奋的，通常描述人的感受。"]
  }
]
```

不需要 `end`；脚本统一设成下一条起点，末条到视频末尾。开始时间按 ASS 的 10 ms 精度量化，量化后重复、倒退、超出时长会报错。不得复制上述示例时间到真实视频。

`highlight_en` 和 `highlight_zh` 均为原文中的短语列表，支持短语换行后继续高亮，并分别恢复英文/中文原色。纯英文词使用词边界，避免 `art` 高亮到 `part`。没有颜色的 SRT 只保留双语正文，提示只在 ASS 中。

普通空白会被整理成单空格，按画面宽度自动换行。为避免原稿注入 ASS 样式，ASS 文字中的反斜杠及花括号按全角字形显示。自动换行是初稿，特殊窄屏、长英文单词、长提示仍需渲染检查及语义拆分。

## 配色

| 预设 | 英文 | 中文 | 高亮 | 顶部提示 |
|---|---|---|---|---|
| classic（默认） | #FFFFFF | #FFBC00 | #FF7B25 | #FF7B25 |
| soft | #FFF8E7 | #A8E6CF | #FFB86C | #FFB86C |
| contrast | #FFFFFF | #80E5FF | #FF8EC7 | #FF8EC7 |

classic 的黄色与橙色取自用户提供的参考截图代表色：中文黄色 RGB(255,188,0)，重点/提示橙色 RGB(255,123,37)。这是截图取色，不声称是品牌官方色值。

所有颜色都是 `#RRGGBB`，脚本转换成 ASS 的 BGR 顺序。英文、中文、高亮必须是三个不同的颜色；顶部提示允许与高亮相同。优先级：默认样式 → 预设 → 自定义 JSON → 单独 CLI 参数。自定义 JSON 可只写需要覆盖的字段，不必复制整个模板。

[assets/style.example.json](../assets/style.example.json) 列出完整样式字段。字号/垂直边距是视频高度比例，左右边距是视频宽度比例；这些参数不缩放视频。默认 Arial 和 Noto Sans CJK SC；检查实际字体解析，macOS 可覆盖 `--font-zh 'Heiti SC'`。不要未经检查假定字体存在，禁止接受缺字方框的结果。

## 生成 ASS/SRT

在工作区虚拟环境安装 `pysubs2`。以下 `SKILL_DIR` 和输入路径只是占位名称，运行时替换为实际路径；FFmpeg/ffprobe 不在 PATH 时用参数传入真实可执行文件路径。

```bash
python SKILL_DIR/scripts/subtitle_tool.py build \
  --video INPUT.mp4 --timeline aligned.json --out-prefix OUTPUT/study \
  --preset classic
```

自定义颜色：

```bash
python SKILL_DIR/scripts/subtitle_tool.py build \
  --video INPUT.mp4 --timeline aligned.json --out-prefix OUTPUT/custom \
  --preset classic --en-color '#FFFFFF' --zh-color '#90CAF9' \
  --highlight-color '#FFAB91' --hint-color '#FFD54F' \
  --font-zh 'Heiti SC'
```

批量复用样式可使用 `--style custom-style.json`。输出 `.ass`、`.srt`、`.style.json`（最终有效配置）和 `.validation.json`（结构检查与短字幕提示）。输出前缀存在时拒绝覆盖；更换前缀或仅清理明确属于本次任务的旧产物。

## 原分辨率烧录

```bash
python SKILL_DIR/scripts/subtitle_tool.py burn \
  --video INPUT.mp4 --ass OUTPUT/study.ass --output OUTPUT/study-burned.mp4
```

辅助命令读取源宽高，核对 ASS 画布，在**不使用 scale/crop/pad/-s/-r** 的情况下运行 libass + libx264，保持输入帧时间，不固定成 720p/1080p。默认 `--crf 20`、复制所有音轨并保留通用元数据和章节；如 MP4 不接受源音频编码，可改用 MKV 或明确设置 `--audio-codec aac`，说明是否重编码音频。烧录本身会重编码视频，不宣称视频无损。

命令通过临时工作目录中的固定字幕文件名调用滤镜，支持输入文件路径包含空格或单引号，不需要自行拼接 FFmpeg 滤镜字符串。

脚本保留非方形像素的原 SAR，并核对输出；不以 setsar=1 修改画面比例。脚本拒绝旋转元数据、HDR/BT.2020、多视频轨或明显非零视频起始时间，避免自动破坏这些媒体。对这类输入继续根据任务制作合适的 FFmpeg 管线，参照 SKILL.md 的保真约束，不能去掉检测直接套用普通命令。烧录后的宽高必须与原视频相同；若原视频的显示方向需要特殊处理，必须明确验证编码尺寸和显示尺寸两个概念。

## 验证及交付

- 检查 `.validation.json` 和起点来源；该报告只验证时间结构，不证明识别语义正确。
- 用 libass 渲染长英文、长中文、关键词及顶部提示；确认英文在中文上方、三种颜色可区分、高亮后能恢复正确颜色、无溢出和缺字。
- `burn` 自动检查输出宽高、像素宽高比、时长和音轨数量，并使用 `ffmpeg -xerror` 完整解码；再核对帧率、音画同步、显示方向和色彩。不得仅凭 ASS 能解析就宣称视频全部验收。
- 最终提供 ASS、SRT；烧录被请求时提供带字幕视频。可附有效样式 JSON 便于复用，清楚说明 SRT 没有高亮和顶部提示。
