# 工具检查、下载与准备

在用户要求使用本技能处理文件，且授权缺少工具自行下载时，Agent 应完成所需环境准备，不把安装步骤直接甩给用户。优先使用已有可执行文件或应用内可复用工具；缺项才下载。优先工作区虚拟环境、本地工具目录和模型目录，不修改无关全局配置。系统或宿主真的拒绝必要操作时，报告具体失败及可选替代方案，按真实权限边界处理。

## 检查实际能力

脚本需要 Python 3.9+ 和 pysubs2。音频识别需要 whisper.cpp 及语言相符的 GGML 模型。烧录还需要 FFmpeg 的 `ass`/`subtitles` 滤镜（libass）及合适的视频编码器。

```bash
python3 --version
ffmpeg -version
ffprobe -version
ffmpeg -filters
ffmpeg -encoders
whisper-cli --help
```

在 `-filters` 输出中确认 `ass` 或 `subtitles`，在 `-encoders` 中确认本技能默认使用的 `libx264`。不能只看到 ffmpeg 文件就认为构建包含字幕功能。工具不在 PATH 但已在磁盘上时，使用绝对路径；脚本接受 `--ffmpeg` 和 `--ffprobe`，不需要移动原应用的文件。

## Python 虚拟环境

macOS/Linux，在任务工作区执行：

```bash
python3 -m venv .subtitle-venv
.subtitle-venv/bin/python -m pip install pysubs2
.subtitle-venv/bin/python /技能绝对路径/scripts/subtitle_tool.py --help
```

Windows PowerShell：

```powershell
py -3 -m venv .subtitle-venv
.subtitle-venv/Scripts/python.exe -m pip install pysubs2
.subtitle-venv/Scripts/python.exe 'C:/技能绝对路径/scripts/subtitle_tool.py' --help
```

只在缺少 Python 时从 [Python 官方下载页](https://www.python.org/downloads/) 或当前系统认可的包管理器准备。RTF 在 macOS 可用系统 `textutil`；Windows/Linux 使用可靠的 RTF 解析库或已有 LibreOffice，DOCX 可用 python-docx。对应解析工具仅在输入格式需要时安装到虚拟环境。

## FFmpeg、构建工具与平台差异

FFmpeg 官方提供源码及各平台构建入口：[下载页](https://ffmpeg.org/download.html)。选择与 CPU 架构匹配且包含 libass 的构建；解压到工作区 `tools/` 也可，不必全局安装。macOS 可以复用已经安装的应用所带 FFmpeg；注意动态库依赖，不要随意把单个文件复制离开其目录。

已有 Homebrew 的 macOS，可按缺项安装：

```bash
brew install ffmpeg cmake git
```

安装后必须检查 libass 滤镜，包名不保证具体构建的可选能力。若缺失，按 FFmpeg 官方下载页选择带 libass 的构建，或使用官方源码及 libass 依赖构建；不能继续生成没有字幕的视频。

Debian/Ubuntu 示例（仅在拥有相应系统安装权限时）：

```bash
sudo apt-get update
sudo apt-get install ffmpeg cmake build-essential git python3-venv
```

Windows 从官方入口选择合适的 FFmpeg 构建，保留同包的 ffmpeg.exe、ffprobe.exe 及所需库。whisper.cpp 优先使用其官方 release 中合适的构建；没有合适构建时安装 CMake 和 C/C++ 工具链再编译。不要使用来源不明的“万能安装脚本”。

## whisper.cpp 与模型

参考当前 [whisper.cpp 官方仓库](https://github.com/ggml-org/whisper.cpp)，在工作区下载源码。先检查 `tools/whisper.cpp` 是否存在，存在则复用并记录版本，不覆盖其改动。

```bash
git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git tools/whisper.cpp
cmake -S tools/whisper.cpp -B tools/whisper.cpp/build -DCMAKE_BUILD_TYPE=Release -DWHISPER_BUILD_TESTS=OFF
cmake --build tools/whisper.cpp/build --config Release -j 4
```

使用实际生成的 whisper-cli 路径；Windows 多配置生成器可能位于 `build/bin/Release/whisper-cli.exe`。macOS 若系统缺少编译工具，使用官方开发工具安装渠道；已有 CMake/编译器时直接复用。

英文教学语音可先选 small.en；中英混合选择多语言模型，不用 `.en` 模型处理中文。官方模型与摘要见仓库 models 文档及 [官方 GGML 模型仓库](https://huggingface.co/ggerganov/whisper.cpp)。Unix 可使用随源码提供的模型下载脚本：

```bash
bash tools/whisper.cpp/models/download-ggml-model.sh small.en
```

如果下载脚本没有适当的超时或断点续传，改用具有有限超时、有限重试的下载器。例如在新建的工作区 `models/` 内下载；开始前检查是否已有完整文件，校验后才把 `.part` 重命名为 `.bin`：

```bash
mkdir -p models
curl --fail --location --connect-timeout 20 --max-time 900 \
  --speed-limit 1024 --speed-time 60 --retry 3 --retry-delay 3 \
  --continue-at - --output models/ggml-small.en.bin.part \
  'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin'
```

Windows 可用系统 `curl.exe` 的相同参数。模型下载失败不能加载残缺文件；校验官方摘要与大小，不把本技能中的模型示例名当成所有语种的唯一选择。记录所用模型和 whisper.cpp 版本，保留可复现日志。

GPU 加速不可用时先检查真实报错。若为宿主权限限制，按宿主许可处理；若为驱动/硬件不支持，可用 `--no-gpu` 的 CPU 路径。词级 DTW 的启用及 `-nfa` 兼容性检查见 [alignment.md](alignment.md)。

## 就绪检查与边界

先用短音频验证模型能加载、输出有有效时间戳，再处理完整视频。先渲染少量字幕确认字体和颜色，再烧录完整视频。下载工具与模型不需要上传用户的视频或字幕。

授权下载必要工具不等于授权安装到所有 Agent、修改全局配置或上传文件。本包只提供安装和使用说明；实际选择项目级或用户级安装位置遵循用户当次请求。
