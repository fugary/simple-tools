---
name: image-motion
description: 将单张静态图片自动分析并生成自然、无抽卡的微动态循环视频（MP4 / WebP）。由当前 Agent 看图规划动效配方与粗略位置坐标，通过边缘吸附算法自动贴合真实色彩边界，支持湖海波纹、瀑布溪流、天空飘云、草木摇曳、旗帜布料迎风飘动、风车/风扇局部旋转、热气与阳光光斑、以及 3%~5% 温和空间微推进，并支持 Depth Anything V2 深度图推理。暂独立运行，不修改其他视频技能。
---

# 图片微动效（Image Motion）

把单张静态图片转化为自然、克制、可控的无缝循环微动态视频（默认 5 秒、30fps、H.264 MP4）。不依赖生成式视频抽卡，也不需要重型 GPU 模型即可在 Windows 与 macOS 运行；后续可随时通过 `--depth-map` 无缝接入 Depth Anything 等外部深度图。

## 环境检查

首次运行前检查 Python 依赖与 FFmpeg：

```sh
python scripts/check_environment.py
```

需要 Python 3.9+、`Pillow`、`numpy`、`imageio-ffmpeg`（或系统 `PATH` 中的 `ffmpeg`）。若缺包，在当前虚拟环境执行 `pip install -r requirements.txt`；不强行使用系统全局修改或管理员权限。`check_environment.py` 还会同步探测 `depth_anything_step2`（`onnxruntime` / `huggingface_hub` / `torch` / `transformers` 与 CUDA/MPS/CoreML 可用性）。

## 物理合理性与“防地震”刚体锁定规范

除非内容本身明确是地震、爆炸晃动等题材，否则所有配方都必须遵守基本物理常识，禁止“万物乱晃”：

1. **建筑、墙体、桥梁、雕塑、固定牌匾绝对不形变**：
   - 将所有固定建筑与硬边结构体填入配方顶层 `"static_regions": {"polygons": [...], "rects": [...]}`（或对象列表），渲染器会自动把它们锁定并排除出 `water_ripple`、`sky_drift`、`foliage_sway`、`rotate_part` 与 `overlay_fx` 的作用域；若角标水印需要在全局 `depth_parallax` 下也保持完全静止，可给对应条目加 `"lock_camera": true`。
   - 若构图重点是建筑+局部动态（如楼前飘云、大楼前的喷泉水池、室内桌面的咖啡热气），**不要加 `depth_parallax`**，只运行局部动效即可保持建筑像素 `0.0` 绝对静止（`.verification.json` 会多相位检查并输出 `static_region_warp_max_diff` 供确认）。
2. **微推镜头不左右横摇**：
   - `depth_parallax` 在 `"loop"` 和 `"push"` 模式下默认 `sway_x = 0.0`（纯前后温和呼吸/推进），**含建筑、街道、室内的场景严禁随意把 `sway_x` 调大或用 `"orbit"`**，否则竖直墙面会出现“地震式”左右晃动；同时建筑本身需列入 `foreground_regions` 给统一平面深度，避免楼顶与楼底拉伸比率不同导致“楼体变软/弯曲”。
3. **只让真正在风中或物理规律下会动的物体动**：
   - 风车/风扇只允许旋转扇叶（配合 `max_y` 截断固定塔柱与底座），不得带动房屋主体旋转；
   - `sky_drift` 保持单一稳定风向；`foliage_sway` 只框草丛/树梢并排除建筑墙面；`steam` 仅锚定在热食/热饮上方。

## 标准执行流程

1. **生成归一化参考网格并看图分析。**
   先运行网格工具生成带 `[0.0 .. 1.0]` 坐标线的参考图，并用读图能力直接查看：
   ```sh
   python scripts/inspect_grid.py --image INPUT.jpg --out WORK/grid.png
   ```
   判断图片属于哪类场景，同时先列出所有**物理上绝不能动的刚体/静态对象**（建筑、桥梁、城墙、电线杆、风车塔身、地面建筑小品、家具、停靠船只、文字水印等），写入顶层 `static_regions`。

2. **规划 `motion_plan.json`（先按图选配方，不盲套特效）。**
   按 [配方格式](references/plan-schema.md) 组合适合本图的动效原语：
   - **湖海/河流/瀑布/倒影图**：静水用 `water_ripple`（用 `polygons` 框出大概水体；若照片水面本身已有密集天然波纹，用 `amplitude: 0.45~0.65`、`shimmer: 0.3~0.4` 避免网格叠加）；瀑布或急流用 `waterfall_flow`（配 `angle: 90` 与底部水雾 `mist`）+ `static_regions`（锁定船只、栈道、岩石、文字水印）+ 可选 `sky_drift`、`sun_motes`。
   - **多人物/建筑/古迹/户外抓拍图**：极克制的 `depth_parallax`（`strength: 0.025~0.035`，`sway_x: 0.0`，给出 `horizon_y` 与建筑/人物 `foreground_regions`）— 或直接省略 `depth_parallax` 仅做局部动效；若有旗帜/横幅/披风则配 `flag_cloth_wave`（设 `anchor_side` 固定旗杆边），若有风车/风扇则配 `rotate_part`（设 `max_y` 保护塔柱）+ `sky_drift` / `foliage_sway` / `sun_motes`，并把建筑主体与前景人物填入 `static_regions`。
   - **美食/热饮/餐桌/室内灯光图**：以局部动效为主（`overlay_fx` 的 `"steam"` 放在热食锚点，或 `"warm_glow"` 放在灯源），桌椅杯盘放进 `static_regions`；若需镜头微推，只用 `strength: 0.02~0.03`、`sway_x: 0.0`。
   - **纯图文/结构示意图**：**禁止局部水波/风吹扭曲文字与结构**，仅可用极轻 `depth_parallax`（`strength: 0.02`, `sway_x: 0.0`）或局部小光点 `sun_motes`。

3. **开启边缘吸附并校验遮罩。**
   所有粗略多边形默认开启 `"edge_snap": true`，脚本会利用颜色梯度阻止扩散的算法将粗轮廓自动吸附到真实岸线、山脊或物体边缘。首次调试新构图时，建议加 `--preview-masks WORK/masks` 并查看生成的遮罩叠加图（包括 `static_regions_locked.png`），确认山体、建筑、人物、船只未被误纳入水波、飘云或摇摆区域。

4. **渲染并核查成品。**
   ```sh
   python scripts/render_motion.py --image INPUT.jpg --plan WORK/motion_plan.json --output WORK/motion.mp4 --preview-masks WORK/masks
   ```
   - 默认最小输出宽度 `1160`（小图用 Lanczos 放大后渲染以保证亚像素顺滑，上限默认 `1920`，宽高自动对齐偶数），输出自带 `.verification.json`（含 `mean_motion_peak_diff`、`mean_motion_mid_diff`、`loop_seam_diff` 及多相位刚体检验）。
   - **视觉核查**：查看渲染出的 MP4 首/中/尾帧或 `--webp` 预览图，确认：
     1. 动效区域自然连贯，无“果冻感”拉扯或山峰/船体融化；
     2. 建筑、地面固定物等无“地震感”晃动或扭曲；
     3. 循环模式（`loop`）下首尾接缝平滑，水印或关键主体清晰无变形。

## Step 2：Depth Anything V2 深度图推理

代码已内建可选的 `scripts/estimate_depth.py` 与 `render_motion.py --auto-depth`，支持两条后端路径：

- **ONNX Runtime**（轻量推荐，macOS Apple Silicon 可自动走 `CoreMLExecutionProvider`）：安装 `onnxruntime`，配合 `--onnx-path local_model.onnx`（或环境变量 `DEPTH_ANYTHING_ONNX`）运行；若安装 `huggingface-hub` 也可自动拉取 ONNX 权重。
- **Transformers + PyTorch**（支持 `cuda` / Apple Silicon `mps` / `cpu`）：安装 `torch` 和 `transformers`，默认模型 `depth-anything/Depth-Anything-V2-Small-hf`。

```sh
# 方式 1：单独生成灰度深度图
python scripts/estimate_depth.py --image INPUT.jpg --output WORK/depth.png --onnx-path path/to/depth_anything_v2_vits.onnx

# 方式 2：渲染时一步自动计算并接入 depth_parallax
python scripts/render_motion.py --image INPUT.jpg --plan WORK/motion_plan.json --auto-depth --onnx-path path/to/depth_anything_v2_vits.onnx --output WORK/motion.mp4
```

若本机尚未安装任何 Step 2 后端，直接省略 `--auto-depth` 即可无缝退回 Step 1 合成深度与局部边缘吸附动效。
