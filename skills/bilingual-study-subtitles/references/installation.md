# 安装与调用

本技能随教学视频包提供。将整个 `bilingual-study-subtitles/` 和 `teaching-slideshow-video/` 两个目录并排安装到目标 Agent 的技能目录，不只复制 SKILL.md。将这两个完整目录复制到目标 Agent 的技能目录；教学视频环境准备见[跨 Agent 使用](../../teaching-slideshow-video/references/portability.md)。

`agents/openai.yaml` 是可选展示元数据；其他 Agent 可直接读取 SKILL.md、references 和 scripts。安装不包含 Python、FFmpeg、字体、Whisper 模型或在线服务凭据。

先按 [setup.md](setup.md) 准备依赖，再按 [alignment.md](alignment.md) 对齐及 [usage.md](usage.md) 生成字幕。独立使用时可对 Agent 说“使用 bilingual-study-subtitles 技能，根据录音和稿件生成 ASS/SRT”。
