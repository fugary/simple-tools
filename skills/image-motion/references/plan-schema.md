# `motion_plan.json` 配方格式说明

所有坐标与尺寸均使用归一化比例 `[0.0 .. 1.0]`，原点 `(0, 0)` 在画面左上角，`(1, 1)` 在右下角。

```json
{
  "duration": 5.0,
  "fps": 30,
  "static_regions": {
    "polygons": [[[0.63, 0.72], [1.0, 0.70], [1.0, 0.89], [0.63, 0.86]]],
    "rects": [[0.65, 0.89, 0.99, 0.96]]
  },
  "effects": [
    {
      "type": "water_ripple",
      "polygons": [[[0.0, 0.72], [0.22, 0.66], [1.0, 0.66], [1.0, 1.0], [0.0, 1.0]]],
      "edge_snap": true,
      "amplitude": 1.0,
      "shimmer": 0.7,
      "speed": 1
    },
    {
      "type": "sky_drift",
      "polygons": [[[0.0, 0.0], [1.0, 0.0], [1.0, 0.45], [0.0, 0.45]]],
      "edge_snap": true,
      "drift_x": 0.024
    },
    {
      "type": "overlay_fx",
      "kind": "sun_motes",
      "count": 20,
      "opacity": 0.45
    }
  ]
}
```

## 全局刚体锁定（`static_regions`）

- 顶层可选 `"static_regions": {"polygons": [...], "rects": [...]}`（也支持列表格式 `[{"rect": ...}, {"polygon": ...}]`）。
- 凡填入 `static_regions` 的**建筑、桥梁、墙壁、木栈道、停靠船只、山岩、电线杆、站立人物或水印文字**，渲染器会自动合并进所有局部形变动效（`water_ripple`、`waterfall_flow`、`sky_drift`、`foliage_sway`、`flag_cloth_wave`、`rotate_part`）的排除掩膜：
  - 水面/云层/草丛形变在刚体边缘即止；
  - 旋转部件（如风车扇叶）自动从前景静止人物/建筑**背后**转过，不会糊到前景主体上；
  - 若某个静止区域条带带有 `"lock_camera": true`（适合角标、水印、字幕框），不仅在开启 `depth_parallax` 时会将该区域钉死回原像素，还会自动从 `overlay_fx` 氛围层中柔和羽化排除（若希望普通 `static_regions` 也屏蔽某个 `overlay_fx`，可在该 overlay 中设 `"respect_static_regions": true`）；
  - `.verification.json` 会在多相位采样点（约 `0.25 / 0.37 / 0.50 / 0.75`）检验并输出 `mean_motion_peak_diff` 与 `static_region_warp_max_diff`（未开 `depth_parallax` 时检查全部 `static_regions`，开启 `depth_parallax` 时检查 `lock_camera: true` 区域，理想均为 `0.0`），并在 `--preview-masks` 中生成 `static_regions_locked.png`（及 `camera_locked_regions.png`）供核查。

## 动效原语（`effects`）

1. **`water_ripple`**（湖泊 / 河流 / 海面波纹）
   - `polygons` / `rects`：粗略水体区域；`exclude_polygons` / `exclude_rects`：需保持静止的船只、木栈道、桥梁、人物或水印框。
   - `edge_snap`（默认 `true`）：通过边缘停止扩散将粗多边形自动吸附到真实水岸/船体边界，并自动由遮罩上缘推算远近透视岸线。
   - `amplitude`（默认 `1.0`）、`shimmer`（倒影微高光，默认 `0.7`）、`speed`（整数循环倍率，默认 `1`）。若原图水面本身已有清晰细碎波浪纹理，建议降至 `amplitude: 0.45 ~ 0.65`、`shimmer: 0.3 ~ 0.4` 以免原波纹叠加后出现交错网格感。

2. **`sky_drift`**（天空飘云）
   - `polygons` / `rects`：粗略天空区域，`edge_snap` 默认开启以自动贴紧山脊/树梢/建筑轮廓。
   - `drift_x`（默认 `0.024`，单循环占画宽位移比例，正值为向右飘，负值为向左飘）、`drift_y`（默认 `0.0`）。使用双相半周期融合，无接缝单向飘动。

3. **`foliage_sway`**（草丛 / 树冠微风摆动）
   - `polygons` / `rects` + 可选 `exclude_polygons`；`amplitude`（默认 `2.2`）、`speed`（整数倍率，默认 `1`）。

4. **`waterfall_flow`**（瀑布 / 山涧急流 / 喷泉定向流注）
   - `polygons` / `rects`：粗略瀑布或急流区域，`edge_snap` 默认开启自动贴紧两侧岩石峭壁。
   - `angle`：流动方向角度（默认 `90.0` 为竖直向下，斜瀑或溪流可设如 `75.0` 或 `15.0`）。
   - `flow_distance`（单循环流注行程占流向跨度比例，默认 `0.16`）、`turbulence`（湍流波纹强度，默认 `1.0`）、`foam_shimmer`（白水浪花高光闪烁，默认 `0.65`）、`mist`（瀑布底部自动升腾水雾强度，默认 `0.40`，设 `0` 关闭）、`speed`（整数循环倍速，默认 `1`）。

5. **`flag_cloth_wave`**（旗帜 / 横幅 / 窗帘 / 衣角单侧锚定飘动）
   - `polygons` / `rects`：旗面或布料区域，`edge_snap` 默认开启。
   - `anchor_side`: `"left"`（默认，左侧连接旗杆，波浪从左向右传播） | `"right"`（右侧连接旗杆） | `"top"`（顶部固定，如垂挂横幅/窗帘） | `"bottom"`（底部固定）。锚定边位移严格为 `0.0`，向自由端平滑递增。
   - `amplitude`（波幅，默认 `3.2`）、`wavelength`（波长占布面跨度比例，默认 `0.55`）、`shade`（3D 布料凹凸受光明暗褶皱强度，默认 `0.65`）、`speed`（整数循环倍速，默认 `1`）。

6. **`rotate_part`**（风车 / 风扇 / 摩天轮 / 钟表盘）
   - `center`: `[cx, cy]` 旋转中心；`radius`: 半径（相对画幅短边比例，如 `0.08`）。
   - `turns`：单循环旋转圈数（四叶风车可用 `0.25` 实现每 5 秒转 90° 无缝循环，整体圆盘可用 `1.0`）。
   - `mode`: `"blades"`（自动用局部中值滤波分离细长扇叶并保留后方流动天空/背景）或 `"disc"`（整体羽化圆盘旋转）。
   - `blade_tone`: `"bright" | "dark" | "any"`（仅 `"blades"` 模式生效，默认 `"bright"`）；可选 `max_y` 限制扇叶以下支撑立柱不随旋转变形。

5. **`overlay_fx`**（透明氛围层）
   - `kind`:
     - `"steam"`：热气上升，需传 `anchors: [[x, y], ...]` 与可选 `scale`。
     - `"sun_motes"`：暖色阳光光斑/浮尘，`count`（默认 `22`）。
     - `"warm_glow"`：灯火/烛光呼吸光晕，传 `anchors` 与 `radius`。
     - `"sunbeam"`：斜向柔光光束脉冲。
     - `"rain"` / `"snow"`：轻度细雨或飘雪，`count`。
   - `opacity`：透明度（`0.0 ~ 1.0`）。

6. **`depth_parallax`**（3%～5% 温和空间微推进）
   - **Step 1（无需外部模型）**：按 `horizon_y`（天际线高度）、`sky_depth`（默认 `0.05`）、`horizon_depth`（默认 `0.25`）、`bottom_depth`（默认 `0.92`）构建平滑斜坡深度场，并可附带 `foreground_regions: [{"polygons": [...], "depth": 0.92}]`（默认走 `edge_snap` 贴合主体边缘）。
   - **Step 2（已接入 Depth Anything V2 / 外部深度图）**：
     - 命令行可加 `--auto-depth`（支持 `--depth-backend auto|onnx|transformers`、`--onnx-path`、`--depth-model`、`--depth-input-size`、`--depth-out`）自动推算灰度深度图并接入 `depth_parallax`；也可先用 `scripts/estimate_depth.py` 单独生成后再传 `"depth_map": "path/to/depth.png"` 或 `--depth-map`。
     - 可配合 `"invert_depth": true` 适配“黑近白远”的第三方深度图。
   - `strength`（默认 `0.04`，含建筑构图建议 `0.025 ~ 0.035`）、`sway_x`（横向摇摆，`loop` / `push` 模式**默认 `0.0`** 避免建筑物像地震一样左右晃动；仅 `orbit` 模式默认 `0.006`）、`mode`: `"loop"`（纯前后微呼吸无缝循环） | `"push"`（单向缓推） | `"orbit"`（轻度环绕微摇，含硬边建筑时慎用）。
   - **防地震/防果冻提示**：若画面中含需要**绝对零位移**的建筑或桌面静物（如楼宇前的喷泉、餐桌热饮），应直接省略 `depth_parallax`，改用局部动效 + `static_regions`；若使用 `depth_parallax` 配合竖直建筑，务必把建筑轮廓加入 `foreground_regions` 赋统一平面深度，避免楼顶与楼底因深度梯度不同而被纵向拉伸。
