import React from "react";
import {
  AbsoluteFill,
  Img,
  Loop,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { SceneItem, SpotlightItem } from "../types";

interface SceneLayerProps {
  scenes: SceneItem[];
  spotlights: SpotlightItem[];
}

const AmbientMotes: React.FC<{ count: number; opacity: number }> = ({
  count,
  opacity,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;

  const motes = React.useMemo(() => {
    return Array.from({ length: count }, (_, i) => {
      const seed1 = Math.sin(i * 12.9898) * 43758.5453;
      const seed2 = Math.sin(i * 78.233 + 1.3) * 43758.5453;
      const rx = seed1 - Math.floor(seed1);
      const ry = seed2 - Math.floor(seed2);
      return {
        x0: rx * width,
        y0: ry * height,
        r: 2.2 + (i % 5) * 1.4,
        speedY: 14 + (i % 4) * 6,
        ampX: 16 + (i % 3) * 10,
        phase: i * 1.17,
      };
    });
  }, [count, width, height]);

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <radialGradient id="moteGrad">
            <stop offset="0%" stopColor="#FFF7D6" stopOpacity="1" />
            <stop offset="55%" stopColor="#FDE68A" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#FDE68A" stopOpacity="0" />
          </radialGradient>
        </defs>
        {motes.map((m, idx) => {
          const y = ((m.y0 - t * m.speedY) % height + height) % height;
          const x = m.x0 + Math.sin(t * 0.8 + m.phase) * m.ampX;
          const twinkle = 0.5 + 0.5 * Math.sin(t * 1.9 + m.phase * 2);
          return (
            <circle
              key={idx}
              cx={x}
              cy={y}
              r={m.r * 3.2}
              fill="url(#moteGrad)"
              opacity={opacity * (0.35 + 0.65 * twinkle)}
            />
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};

const SingleScene: React.FC<{
  scene: SceneItem;
  isFirst: boolean;
  isLast: boolean;
}> = ({ scene, isFirst, isLast }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const transitionFrames = scene.transitionDurationFrames ?? 18;
  const startFrame = Math.round(scene.start * fps);
  const endFrame = Math.round(scene.end * fps);
  const halfOverlap = Math.floor(transitionFrames / 2);

  const seqFrom = isFirst ? 0 : Math.max(0, startFrame - halfOverlap);
  const seqEnd = isLast ? endFrame : endFrame + halfOverlap;
  const duration = Math.max(1, seqEnd - seqFrom);

  const localFrame = frame - seqFrom;
  if (localFrame < 0 || localFrame >= duration) {
    return null;
  }

  const transition = scene.transition ?? "fade";
  let opacity = 1;
  let translateX = 0;
  let clipPath: string | undefined;

  if (!isFirst && transition !== "none" && localFrame < transitionFrames) {
    const p = interpolate(localFrame, [0, transitionFrames], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    if (transition === "fade") {
      opacity = p;
    } else if (transition === "slide") {
      opacity = interpolate(p, [0, 0.25], [0, 1], { extrapolateRight: "clamp" });
      translateX = (1 - p) * 120;
    } else if (transition === "wipe") {
      clipPath = `inset(0 ${(1 - p) * 100}% 0 0)`;
    }
  }

  if (!isLast && transition === "fade" && localFrame > duration - transitionFrames) {
    opacity *= interpolate(
      localFrame,
      [duration - transitionFrames, duration],
      [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );
  }

  const vfx = scene.vfx;

  return (
    <Sequence from={seqFrom} durationInFrames={duration} layout="none">
      <AbsoluteFill
        style={{
          opacity,
          transform: translateX !== 0 ? `translateX(${translateX}px)` : undefined,
          clipPath,
        }}
      >
        <Img
          src={staticFile(scene.imageFile)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />

        {/* Subtle radial edge vignette (keeps center photography crisp and luminous) */}
        <AbsoluteFill
          style={{
            background:
              "radial-gradient(circle at 50% 50%, rgba(0, 0, 0, 0) 56%, rgba(7, 10, 18, 0.22) 100%)",
            pointerEvents: "none",
          }}
        />

        {scene.backdropDim && scene.backdropDim > 0 ? (
          <AbsoluteFill
            style={{
              background: `linear-gradient(180deg, rgba(8, 12, 22, ${Math.min(0.92, scene.backdropDim * 0.9)}) 0%, rgba(8, 12, 22, ${Math.min(0.95, scene.backdropDim)}) 55%, rgba(6, 9, 17, ${Math.min(0.96, scene.backdropDim + 0.08)}) 100%)`,
              pointerEvents: "none",
            }}
          />
        ) : null}

        {vfx?.kind === "motes" ? (
          <AmbientMotes count={vfx.count ?? 18} opacity={vfx.opacity ?? 0.3} />
        ) : null}

        {vfx?.kind === "screen_video" && vfx.videoFile ? (
          <div
            style={{
              position: "absolute",
              left: `${((vfx.region?.x ?? 0.5) - (vfx.region?.w ?? 0.4) / 2) * 100}%`,
              top: `${((vfx.region?.y ?? 0.5) - (vfx.region?.h ?? 0.4) / 2) * 100}%`,
              width: `${(vfx.region?.w ?? 0.4) * 100}%`,
              height: `${(vfx.region?.h ?? 0.4) * 100}%`,
              mixBlendMode: "screen",
              opacity: vfx.opacity ?? 0.55,
              pointerEvents: "none",
              WebkitMaskImage:
                "radial-gradient(ellipse at center, rgba(0,0,0,1) 38%, rgba(0,0,0,0) 78%)",
              maskImage:
                "radial-gradient(ellipse at center, rgba(0,0,0,1) 38%, rgba(0,0,0,0) 78%)",
            }}
          >
            <Loop durationInFrames={120}>
              <OffthreadVideo
                muted
                src={staticFile(vfx.videoFile)}
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            </Loop>
          </div>
        ) : null}
      </AbsoluteFill>
    </Sequence>
  );
};

const SpotlightOverlay: React.FC<{ spotlight: SpotlightItem }> = ({ spotlight }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;

  if (t < spotlight.start || t > spotlight.end) {
    return null;
  }

  const fadeDur = 0.35;
  const alphaIn = interpolate(t, [spotlight.start, spotlight.start + fadeDur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const alphaOut = interpolate(t, [spotlight.end - fadeDur, spotlight.end], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const alpha = Math.min(alphaIn, alphaOut);

  const cx = spotlight.x * width;
  const cy = spotlight.y * height;
  const rx = spotlight.radiusX * width;
  const ry = spotlight.radiusY * height;
  const dim = (spotlight.dimOpacity ?? 0.38) * alpha;

  return (
    <AbsoluteFill style={{ pointerEvents: "none", opacity: alpha }}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <filter id={`spot-blur-${spotlight.id}`}>
            <feGaussianBlur stdDeviation="16" />
          </filter>
          <mask id={`spot-mask-${spotlight.id}`}>
            <rect width={width} height={height} fill="white" />
            <ellipse
              cx={cx}
              cy={cy}
              rx={rx}
              ry={ry}
              fill="black"
              filter={`url(#spot-blur-${spotlight.id})`}
            />
          </mask>
        </defs>
        <rect
          width={width}
          height={height}
          fill={`rgba(6, 10, 20, ${dim})`}
          mask={`url(#spot-mask-${spotlight.id})`}
        />
        <ellipse
          cx={cx}
          cy={cy}
          rx={rx}
          ry={ry}
          fill="none"
          stroke="rgba(251, 191, 36, 0.72)"
          strokeWidth={3}
        />
      </svg>
      {spotlight.label ? (
        <div
          style={{
            position: "absolute",
            left: cx,
            top: Math.max(40, cy - ry - 48),
            transform: "translateX(-50%)",
            padding: "6px 18px",
            borderRadius: 999,
            backgroundColor: "rgba(15, 23, 42, 0.72)",
            border: "1px solid rgba(251, 191, 36, 0.55)",
            color: "#FDE68A",
            fontSize: 22,
            fontWeight: 700,
            fontFamily: "system-ui, -apple-system, 'PingFang SC', sans-serif",
            backdropFilter: "blur(8px)",
          }}
        >
          {spotlight.label}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

export const SceneLayer: React.FC<SceneLayerProps> = ({ scenes, spotlights }) => {
  return (
    <AbsoluteFill>
      {scenes.map((scene, index) => (
        <SingleScene
          key={scene.id}
          scene={scene}
          isFirst={index === 0}
          isLast={index === scenes.length - 1}
        />
      ))}
      {spotlights.map((sp) => (
        <SpotlightOverlay key={sp.id} spotlight={sp} />
      ))}
    </AbsoluteFill>
  );
};
