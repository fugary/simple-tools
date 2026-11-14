import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { HudItem, HudPosition } from "../types";

interface HudLayerProps {
  hudItems: HudItem[];
  hasTopNote: boolean;
}

function getCornerStyle(position: HudPosition | undefined, hasTopNote: boolean): React.CSSProperties {
  const pos = position ?? "top-right";
  const topOffset = hasTopNote ? 136 : 44;
  if (pos === "top-left") {
    return { top: topOffset, left: 48 };
  }
  if (pos === "bottom-right") {
    return { bottom: 250, right: 48 };
  }
  return { top: topOffset, right: 48 };
}

const glassCardStyle: React.CSSProperties = {
  width: 390,
  padding: "20px 24px",
  borderRadius: 18,
  backgroundColor: "rgba(15, 23, 42, 0.56)",
  border: "1px solid rgba(255, 255, 255, 0.16)",
  backdropFilter: "blur(14px)",
  boxShadow: "0 18px 40px rgba(0, 0, 0, 0.38)",
  color: "#F8FAFC",
  fontFamily: "system-ui, -apple-system, 'PingFang SC', sans-serif",
};

const MetricClimbCard: React.FC<{
  item: Extract<HudItem, { kind: "metric_climb" }>;
  hasTopNote: boolean;
}> = ({ item, hasTopNote }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (t < item.start || t > item.end) return null;

  const localFrame = Math.max(0, Math.round((t - item.start) * fps));
  const enter = spring({ frame: localFrame, fps, config: { damping: 16, stiffness: 120 } });
  const exitAlpha = interpolate(t, [item.end - 0.35, item.end], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const span = Math.max(0.6, item.end - item.start);
  const animDur = Math.min(2.0, Math.max(0.4, span - 0.2 - 1.0));
  const animEnd = item.start + 0.2 + animDur;
  const progress = interpolate(
    t,
    [item.start + 0.2, animEnd],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    }
  );

  const val = Math.round(item.fromValue + (item.toValue - item.fromValue) * progress);

  return (
    <div
      style={{
        ...glassCardStyle,
        position: "absolute",
        ...getCornerStyle(item.position, hasTopNote),
        opacity: enter * exitAlpha,
        transform: `translateY(${(1 - enter) * 18}px)`,
      }}
    >
      {item.eyebrow ? (
        <div
          style={{
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: "0.1em",
            color: "#FBBF24",
            marginBottom: 6,
          }}
        >
          {item.eyebrow}
        </div>
      ) : null}
      <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 10 }}>{item.title}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontSize: 48, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
          {val.toLocaleString("en-US")}
        </span>
        {item.unit ? (
          <span style={{ fontSize: 22, color: "#94A3B8", fontWeight: 600 }}>{item.unit}</span>
        ) : null}
      </div>
      <div
        style={{
          marginTop: 12,
          height: 7,
          borderRadius: 999,
          backgroundColor: "rgba(255,255,255,0.14)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${Math.round(progress * 100)}%`,
            height: "100%",
            borderRadius: 999,
            background: "linear-gradient(90deg, #38BDF8, #F59E0B)",
          }}
        />
      </div>
      {item.badge && progress > 0.85 ? (
        <div
          style={{
            marginTop: 12,
            display: "inline-block",
            padding: "4px 12px",
            borderRadius: 999,
            backgroundColor: "rgba(245, 158, 11, 0.2)",
            border: "1px solid rgba(251, 191, 36, 0.55)",
            color: "#FDE68A",
            fontSize: 14,
            fontWeight: 700,
          }}
        >
          {item.badge}
        </div>
      ) : null}
    </div>
  );
};

const ComparisonBarsCard: React.FC<{
  item: Extract<HudItem, { kind: "comparison_bars" }>;
  hasTopNote: boolean;
}> = ({ item, hasTopNote }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (t < item.start || t > item.end) return null;
  const localFrame = Math.max(0, Math.round((t - item.start) * fps));
  const enter = spring({ frame: localFrame, fps, config: { damping: 16, stiffness: 120 } });
  const exitAlpha = interpolate(t, [item.end - 0.35, item.end], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const maxVal = Math.max(...item.items.map((x) => x.value), 1);

  return (
    <div
      style={{
        ...glassCardStyle,
        position: "absolute",
        ...getCornerStyle(item.position, hasTopNote),
        opacity: enter * exitAlpha,
        transform: `translateY(${(1 - enter) * 18}px)`,
      }}
    >
      <div style={{ fontSize: 19, fontWeight: 700, marginBottom: 14 }}>{item.title}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {item.items.map((row, idx) => {
          const barProg = spring({
            frame: Math.max(0, localFrame - idx * 4),
            fps,
            config: { damping: 18, stiffness: 100 },
          });
          const pct = (row.value / maxVal) * 100 * barProg;
          return (
            <div key={row.label}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: 15,
                  marginBottom: 4,
                  color: row.accent ? "#FDE68A" : "#E2E8F0",
                  fontWeight: row.accent ? 700 : 500,
                }}
              >
                <span>{row.label}</span>
                <span>{row.value}</span>
              </div>
              <div
                style={{
                  height: 8,
                  borderRadius: 999,
                  backgroundColor: "rgba(255,255,255,0.12)",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${pct}%`,
                    height: "100%",
                    borderRadius: 999,
                    backgroundColor: row.accent ? "#F59E0B" : "#38BDF8",
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const RouteFlowCard: React.FC<{
  item: Extract<HudItem, { kind: "route_flow" }>;
  hasTopNote: boolean;
}> = ({ item, hasTopNote }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (t < item.start || t > item.end) return null;
  const localFrame = Math.max(0, Math.round((t - item.start) * fps));
  const enter = spring({ frame: localFrame, fps, config: { damping: 16, stiffness: 120 } });
  const exitAlpha = interpolate(t, [item.end - 0.35, item.end], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        ...glassCardStyle,
        position: "absolute",
        ...getCornerStyle(item.position, hasTopNote),
        opacity: enter * exitAlpha,
        transform: `translateY(${(1 - enter) * 18}px)`,
      }}
    >
      <div style={{ fontSize: 19, fontWeight: 700, marginBottom: 14 }}>{item.title}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {item.steps.map((step, idx) => {
          const stepOpacity = spring({
            frame: Math.max(0, localFrame - idx * 8),
            fps,
            config: { damping: 16, stiffness: 110 },
          });
          return (
            <div
              key={step}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                opacity: stepOpacity,
              }}
            >
              <div
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  backgroundColor: "#38BDF8",
                  boxShadow: "0 0 10px rgba(56, 189, 248, 0.8)",
                }}
              />
              <span style={{ fontSize: 16, fontWeight: 600 }}>{step}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const HudLayer: React.FC<HudLayerProps> = ({
  hudItems,
  hasTopNote,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {hudItems.map((item) => {
        if (item.kind === "metric_climb") {
          return <MetricClimbCard key={item.id} item={item} hasTopNote={hasTopNote} />;
        }
        if (item.kind === "comparison_bars") {
          return <ComparisonBarsCard key={item.id} item={item} hasTopNote={hasTopNote} />;
        }
        if (item.kind === "route_flow") {
          return <RouteFlowCard key={item.id} item={item} hasTopNote={hasTopNote} />;
        }
        if (item.kind === "flag_badge") {
          if (t < item.start || t > item.end) return null;
          const localFrame = Math.max(0, Math.round((t - item.start) * fps));
          const pop = spring({ frame: localFrame, fps, config: { damping: 14, stiffness: 140 } });
          return (
            <div
              key={item.id}
              style={{
                position: "absolute",
                top: hasTopNote ? 136 : 44,
                right: 48,
                width: 260,
                borderRadius: 14,
                overflow: "hidden",
                boxShadow: "0 14px 36px rgba(0, 0, 0, 0.45)",
                border: "2px solid rgba(255, 255, 255, 0.25)",
                transform: `scale(${pop})`,
                opacity: pop,
              }}
            >
              <Img
                src={staticFile(item.imageFile)}
                style={{ width: "100%", display: "block" }}
              />
            </div>
          );
        }
        return null;
      })}
    </AbsoluteFill>
  );
};
