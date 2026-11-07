# 清单及脚本

需要 Python 3.9+，合成需要 FFmpeg（libass/libx264）与 ffprobe；`narrate` 额外需要 edge-tts。字幕 build 需要既有字幕 skill 的 Python 依赖。复用工作区虚拟环境，缺失时在任务授权范围内安装。不要自动使用管理员权限。

路径相对于清单文件。新项目用独立目录；脚本拒绝覆盖 prepare/render 输出。修订时用新目录或明确选定本次中间产物。

```json
{
  "voice": "en-US-JennyNeural",
  "rate": "-15%",
  "pause": 2.0,
  "cues": [
    {"en":"Hello, everyone.", "zh":"大家好。", "notes":[], "highlight_en":[], "audio":"audio/hello.wav"},
    {"en":"help sb. do sth.", "zh":"帮助某人做某事", "spoken":"help somebody do something"}
  ],
  "scenes": [
    {"cue":0, "image":"assets/classroom.png", "title":"课堂导入"}
  ]
}
```

- `cues` 为有序中英条目。`spoken` 可调整缩写读法；缺省为 `en`。`audio` 指已有逐句音频，有它时 narrate 不调用服务。每条可覆盖 `voice`、`rate`、`pause`。场景 `cue` 为零起始条目下标，第一场必须为 0，其后严格递增。图片必须是静态本地文件。
- 有录音片段时先准备对应音频路径。对声音参考的克隆需要提供方能力与用户明确用途，脚本不提供克隆。
- 音频时长及波形有极长空白时先单独检查；脚本不激进裁剪首尾，以免删掉轻辅音。

```sh
python SKILL/scripts/lesson_media.py narrate --manifest PROJECT/lesson.json --out PROJECT/narrated.json --cache PROJECT/audio-cache
python SKILL/scripts/lesson_media.py prepare --manifest PROJECT/narrated.json --out-dir PROJECT/build --ffmpeg /path/to/ffmpeg
python SKILL/scripts/build_subtitles.py --build PROJECT/build --font-zh "Installed Chinese Font" --ffprobe /path/to/ffprobe
python SKILL/scripts/lesson_media.py render --build PROJECT/build --ass PROJECT/build/study.ass --output PROJECT/lesson.mp4 --ffmpeg /path/to/ffmpeg --ffprobe /path/to/ffprobe
```

build 时另传 `--font-zh` 指定已安装中文字体（例如 macOS 的 `Heiti SC`）。

`prepare` 输出旁白、清单副本、时间轴、场景时间及低帧率黑色视频参考；成片为 30fps，参考不交付。`render` 使用所提供 ASS，不自动生成字幕；输出验证 JSON。字幕语义、图片教学准确性、ASR 和视觉抽查仍需 Agent 完成。

重复调用 narrate 可复用缓存；失败调用只保留已完成片段。缓存不能靠碰巧同名推定匹配；跨旧项目复用时核对声音、速度和朗读文本，再明确填入 audio。
