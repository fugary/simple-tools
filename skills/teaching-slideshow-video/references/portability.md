# 跨 Agent 使用

技能使用普通 Markdown、JSON 和 Python，不依赖 Codex 专有 API。`agents/openai.yaml` 仅为可选展示信息。安装时将两个技能目录并排放置；也可在任意解压目录让具备本地工具能力的 Agent 直接读取 SKILL.md。

## 首次使用

1. 使用当前虚拟环境的 Python 运行 `scripts/check_environment.py`。可传 `--ffmpeg`、`--ffprobe`、`--whisper` 指定程序；不依赖固定应用目录。
2. 缺包时用当前虚拟环境安装本技能目录的 `requirements.txt`。脚本不自动下载安装或修改系统设置。
3. 检查 FFmpeg 的 `ass` 滤镜、`libx264`/`aac` 编码器，选择可用中文字体。macOS 常见 Heiti SC，Windows 常见 Microsoft YaHei，Linux 常见 Noto Sans CJK SC；名称仅是候选，必须实际检查渲染。字体检测不足不表示已安装。
4. 默认英文配音 Lily 随技能携带样音与参数。生成需要本机已安装 mlx-audio、兼容的 Apple Silicon 运行环境和本地模型；可通过 LILY_MODEL_PATH 指定权重目录。配置其他音色时，Edge 服务需要网络；依赖安装和服务连通是不同检查。无网络时可继续用已有录音；不能把缺失声音伪装成完成。其他 TTS 提供方生成逐句音频后写入清单的 `audio`，脚本可继续处理。
5. 图片生成由当前 Agent 的可用工具完成。先发现工具、读取其使用要求；没有图片生成能力时明确说明，可继续整理分镜与复用图片，不擅自用代码示意图冒充 AI 生成图。不假定有 Codex imagegen、Gemini API 或某个密钥；用户无需在聊天中贴密钥。
6. RTF 的 `textutil` 只在 macOS 可用。其他平台使用可用的 RTF 解析器或 LibreOffice 导出，核对中英顺序及编码，不调用不存在的 macOS 命令。

## 运行

先按 [manifest.md](manifest.md) 创建清单，再 narrate、prepare。字幕步骤可简化为：

```sh
python SKILL/scripts/build_subtitles.py --build PROJECT/build --font-zh "实际安装的中文字体" --ffprobe /path/to/ffprobe
```

脚本默认使用同级 `bilingual-study-subtitles`；可用 `--subtitle-skill` 指定另一个有效目录。输出为 `PROJECT/build/study.ass`、`.srt` 和验证/样式 JSON。字号按正文技能给出的手机横屏配置，长句均衡换行。

按 manifest.md 运行 format_subtitles.py，使用 styled.ass 渲染成片。换机器时复制完整技能目录（含 assets 下的 Lily 样音和配置）；本地 Qwen3-TTS 模型权重及运行环境须另行准备。图片清单中的路径相对清单文件解析；使用 Python 参数数组，不拼接 shell，支持空格和单引号。渲染固定为横屏默认；竖屏任务应调整整个布局与输出参数，不能假称现有脚本已支持任意分辨率。

ASR 复核仍需本地 Whisper 或等效工具，模型另行准备。环境检测仅报告可执行程序是否存在，不保证模型、字体或在线服务可用。没有实体手机或没有获准使用 UI 时，只做缩小预览并说明实际验证范围。
