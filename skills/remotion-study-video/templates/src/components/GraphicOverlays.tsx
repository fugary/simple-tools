import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { GraphicOverlayItem } from "../types";

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
const seg = (t: number, t0: number, t1: number) =>
  clamp((t - t0) / Math.max(0.0001, t1 - t0), 0, 1);

const glassPanel: React.CSSProperties = {
  borderRadius: 24,
  backgroundColor: "rgba(15, 23, 42, 0.44)",
  border: "1.5px solid rgba(255, 255, 255, 0.24)",
  boxShadow: "0 18px 42px rgba(0, 0, 0, 0.45)",
  color: "#F8FAFC",
  fontFamily: "'SF Pro Display', 'PingFang SC', system-ui, sans-serif",
};

function computeWindowAlpha(t: number, start: number, end: number, fadeInDur = 0.45, fadeOutDur = 0.4) {
  const inP = interpolate(t, [start, start + fadeInDur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const outP = interpolate(t, [end - fadeOutDur, end], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return Math.min(inP, outP);
}

/**
 * Clamp a data-animation end timestamp so counters/bars/rulers reach 100% briskly
 * and always leave sufficient hold time to inspect the final value before exit.
 */
function computeAnimEnd(
  start: number,
  end: number,
  delay = 0.2,
  maxDur = 2.2,
  minHold = 1.0
): number {
  const span = Math.max(0.6, end - start);
  const avail = Math.max(0.4, span - delay - minHold);
  return start + delay + Math.min(maxDur, avail);
}

const GreatWallSvg: React.FC<{ drawProg: number; fillProg: number }> = ({
  drawProg,
  fillProg,
}) => {
  const dash = (len: number, staggerIdx: number, total = 18) => {
    const stagger = (staggerIdx / total) * 0.35;
    const p = clamp((drawProg - stagger) / 0.65, 0, 1);
    return { strokeDasharray: `${len} ${len}`, strokeDashoffset: len * (1 - p) };
  };

  return (
    <svg
      viewBox="0 0 1920 1080"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
    >
      <defs>
        <linearGradient id="gwGoldLine" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#F59E0B" />
          <stop offset="50%" stopColor="#FDE68A" />
          <stop offset="100%" stopColor="#FB923C" />
        </linearGradient>
        <filter id="gwGlow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <path
        d="M 520 560 Q 760 440 980 510 T 1420 420 T 1920 480"
        fill="none"
        stroke="rgba(253,230,138,0.28)"
        strokeWidth={1.8}
        {...dash(1600, 0)}
      />
      <path
        d="M 600 620 Q 860 510 1120 560 T 1580 460 T 1920 530"
        fill="none"
        stroke="rgba(253,230,138,0.18)"
        strokeWidth={1.4}
        {...dash(1500, 1)}
      />

      <path
        d="M 1920 385 C 1780 390 1650 435 1545 495 C 1435 555 1350 535 1235 615 C 1100 710 990 785 835 835 C 680 885 520 935 340 1080 L 470 1080 C 640 950 780 905 935 850 C 1090 795 1185 715 1310 625 C 1405 555 1485 570 1585 505 C 1675 445 1795 405 1920 398 Z"
        fill="rgba(28, 25, 38, 0.85)"
        opacity={fillProg}
      />

      <path
        d="M 1920 385 C 1780 390 1650 435 1545 495 C 1435 555 1350 535 1235 615 C 1100 710 990 785 835 835 C 680 885 520 935 340 1080"
        fill="none"
        stroke="url(#gwGoldLine)"
        strokeWidth={3.4}
        filter="url(#gwGlow)"
        {...dash(1900, 2)}
      />
      <path
        d="M 1920 398 C 1795 405 1675 445 1585 505 C 1485 570 1405 555 1310 625 C 1185 715 1090 795 935 850 C 780 905 640 950 470 1080"
        fill="none"
        stroke="rgba(251,191,36,0.68)"
        strokeWidth={2.2}
        {...dash(1800, 3)}
      />

      {/* Watchtower #1 */}
      <g>
        <path d="M 1190 650 L 1205 560 L 1365 560 L 1380 650 Z" fill="rgba(18, 22, 36, 0.96)" opacity={fillProg} />
        <path
          d="M 1190 650 L 1205 560 L 1365 560 L 1380 650 Z"
          fill="none"
          stroke="url(#gwGoldLine)"
          strokeWidth={2.6}
          {...dash(560, 5)}
        />
        <path
          d="M 1202 560 L 1202 544 L 1222 544 L 1222 554 L 1242 554 L 1242 544 L 1265 544 L 1265 554 L 1305 554 L 1305 544 L 1328 544 L 1328 554 L 1348 554 L 1348 544 L 1368 544 L 1368 560"
          fill="none"
          stroke="#FDE68A"
          strokeWidth={2}
          {...dash(280, 6)}
        />
        <path
          d="M 1225 612 L 1225 586 A 11 11 0 0 1 1247 586 L 1247 612 Z"
          fill="rgba(251,191,36,0.2)"
          stroke="#FBBF24"
          strokeWidth={1.8}
          {...dash(120, 7)}
        />
        <path
          d="M 1274 612 L 1274 586 A 11 11 0 0 1 1296 586 L 1296 612 Z"
          fill="rgba(251,191,36,0.2)"
          stroke="#FBBF24"
          strokeWidth={1.8}
          {...dash(120, 8)}
        />
        <path
          d="M 1323 612 L 1323 586 A 11 11 0 0 1 1345 586 L 1345 612 Z"
          fill="rgba(251,191,36,0.2)"
          stroke="#FBBF24"
          strokeWidth={1.8}
          {...dash(120, 9)}
        />
        <path
          d="M 1226 544 L 1226 508 L 1344 508 L 1344 544"
          fill="none"
          stroke="#FBBF24"
          strokeWidth={2}
          {...dash(220, 10)}
        />
        <path
          d="M 1194 510 Q 1285 496 1376 510 Q 1335 486 1318 468 L 1252 468 Q 1235 486 1194 510 Z"
          fill="rgba(185, 28, 28, 0.78)"
          opacity={fillProg}
        />
        <path
          d="M 1190 510 Q 1235 488 1252 468 L 1318 468 Q 1335 488 1380 510 Q 1285 496 1190 510 Z"
          fill="none"
          stroke="#FDE047"
          strokeWidth={2.4}
          {...dash(440, 11)}
        />
      </g>

      {/* Watchtower #2 */}
      <g>
        <path d="M 1515 522 L 1525 462 L 1620 462 L 1630 522 Z" fill="rgba(20, 24, 38, 0.9)" opacity={fillProg} />
        <path
          d="M 1515 522 L 1525 462 L 1620 462 L 1630 522 Z"
          fill="none"
          stroke="url(#gwGoldLine)"
          strokeWidth={2.1}
          {...dash(380, 13)}
        />
        <path
          d="M 1514 452 Q 1572 442 1631 452 Q 1602 436 1592 424 L 1552 424 Q 1542 436 1514 452 Z"
          fill="rgba(185, 28, 28, 0.68)"
          opacity={fillProg}
        />
        <path
          d="M 1514 452 Q 1542 436 1552 424 L 1592 424 Q 1602 436 1631 452 Q 1572 442 1514 452 Z"
          fill="none"
          stroke="#FDE047"
          strokeWidth={1.9}
          {...dash(300, 14)}
        />
      </g>

      {/* Watchtower #3 */}
      <g>
        <path
          d="M 1735 426 L 1742 385 L 1805 385 L 1812 426 Z"
          fill="rgba(18,22,36,0.96)"
          stroke="#FBBF24"
          strokeWidth={1.6}
          opacity={fillProg}
        />
        <path
          d="M 1732 382 Q 1773 360 1815 382 Q 1773 374 1732 382 Z"
          fill="rgba(185,28,28,0.68)"
          stroke="#FDE047"
          strokeWidth={1.5}
          opacity={fillProg}
        />
      </g>
    </svg>
  );
};

const CoverHeroOverlay: React.FC<{
  item: Extract<GraphicOverlayItem, { kind: "cover_hero" }>;
}> = ({ item }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (t < item.start || t > item.end) return null;

  const alpha = computeWindowAlpha(t, item.start, item.end, 0.35, 0.45);
  const titleP = interpolate(seg(t, item.start + 0.1, item.start + 0.95), [0, 1], [0, 1], {
    easing: Easing.out(Easing.cubic),
  });
  const subP = interpolate(seg(t, item.start + 0.55, item.start + 1.35), [0, 1], [0, 1], {
    easing: Easing.out(Easing.cubic),
  });
  const lineW = 460 * interpolate(seg(t, item.start + 0.35, item.start + 1.15), [0, 1], [0, 1], {
    easing: Easing.out(Easing.cubic),
  });
  const drawProg = interpolate(seg(t, item.start + 0.05, item.start + 2.2), [0, 1], [0, 1], {
    easing: Easing.inOut(Easing.cubic),
  });
  const fillProg = interpolate(seg(t, item.start + 0.95, item.start + 2.3), [0, 1], [0, 1], {
    easing: Easing.out(Easing.cubic),
  });
  const sealScale = spring({
    frame: Math.max(0, Math.round((t - item.start - 0.35) * fps)),
    fps,
    config: { damping: 14, stiffness: 130 },
  });

  return (
    <AbsoluteFill style={{ opacity: alpha, pointerEvents: "none" }}>
      {/* Ultra-light left vignette so crisp photography stays luminous */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(90deg, rgba(8,12,24,0.42) 0%, rgba(10,16,30,0.14) 44%, rgba(10,16,30,0) 76%)",
        }}
      />

      {item.svgPreset !== "none" ? (
        <GreatWallSvg drawProg={drawProg} fillProg={fillProg} />
      ) : null}

      {/* Upright Traditional Red Seal Stamp top-right (0 deg) */}
      {item.sealText ? (
        <div
          style={{
            position: "absolute",
            right: 120,
            top: 130,
            width: 122,
            height: 122,
            borderRadius: 16,
            backgroundColor: "rgba(217, 56, 41, 0.92)",
            border: "3.5px solid #FCA5A5",
            boxShadow: "0 14px 34px rgba(0,0,0,0.45)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#FFF7ED",
            fontSize: 48,
            fontWeight: 800,
            fontFamily: "'PingFang SC', 'Heiti SC', serif",
            transform: `scale(${sealScale})`,
          }}
        >
          {item.sealText}
        </div>
      ) : null}

      <div
        style={{
          position: "absolute",
          left: 104,
          bottom: 270,
          maxWidth: 960,
        }}
      >
        {item.eyebrow ? (
          <div
            style={{
              display: "inline-block",
              padding: "8px 18px",
              borderRadius: 8,
              backgroundColor: "rgba(217, 56, 41, 0.9)",
              fontSize: 22,
              fontWeight: 700,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "#FFF7ED",
              marginBottom: 20,
              opacity: titleP,
            }}
          >
            {item.eyebrow}
          </div>
        ) : null}

        <div
          style={{
            fontSize: 124,
            fontWeight: 800,
            lineHeight: 1.02,
            letterSpacing: "-0.02em",
            background: "linear-gradient(135deg, #FFFFFF 0%, #FDE68A 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            filter: "drop-shadow(0 8px 28px rgba(0,0,0,0.65))",
            transform: `translateY(${(1 - titleP) * 38}px)`,
            opacity: titleP,
          }}
        >
          {item.title}
        </div>

        <div
          style={{
            height: 5,
            width: lineW,
            margin: "22px 0 24px",
            borderRadius: 99,
            background: "linear-gradient(90deg, #F59E0B, #EF4444)",
            boxShadow: "0 0 16px rgba(245, 158, 11, 0.7)",
          }}
        />

        <div
          style={{
            fontSize: 44,
            fontWeight: 600,
            color: "#F8FAFC",
            textShadow: "0 4px 18px rgba(0,0,0,0.75)",
            marginBottom: 10,
            opacity: subP,
            transform: `translateY(${(1 - subP) * 22}px)`,
          }}
        >
          {item.subtitleEn}
        </div>

        {item.subtitleZh ? (
          <div
            style={{
              fontSize: 38,
              fontWeight: 500,
              color: "#FCD34D",
              textShadow: "0 4px 18px rgba(0,0,0,0.75)",
              opacity: subP,
              transform: `translateY(${(1 - subP) * 22}px)`,
            }}
          >
            {item.subtitleZh}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

const GlobeFactCardOverlay: React.FC<{
  item: Extract<GraphicOverlayItem, { kind: "globe_fact_card" }>;
}> = ({ item }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (t < item.start || t > item.end) return null;
  const alpha = computeWindowAlpha(t, item.start, item.end, 0.5, 0.45);

  const cardStart = item.cardStart ?? item.start + 6.5;
  const cardEnd = item.cardEnd ?? cardStart + 3.4;

  const slideRight = interpolate(seg(t, cardStart - 0.3, cardStart + 0.9), [0, 1], [0, 1], {
    easing: Easing.inOut(Easing.cubic),
  });
  const backCenter = interpolate(seg(t, cardEnd - 0.3, cardEnd + 0.9), [0, 1], [0, 1], {
    easing: Easing.inOut(Easing.cubic),
  });

  const gx = 960 + (400 * slideRight) * (1 - backCenter);
  const gy = 465;
  const radius = 270 - 20 * slideRight + 35 * backCenter;

  const cardIn = spring({
    frame: Math.max(0, Math.round((t - cardStart) * fps)),
    fps,
    config: { damping: 16, stiffness: 120 },
  });
  const cardOut = interpolate(t, [cardEnd - 0.4, cardEnd], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const cardVisible = t >= cardStart - 0.1 && t <= cardEnd + 0.1;

  const badgeStart = item.globeBadgeStart ?? item.start + 3.2;
  const switchTime = item.globeSwitchTime ?? cardEnd;
  const showGlobe = item.showGlobe ?? false;
  const showGlobeBadge = showGlobe
    ? t >= badgeStart && (t < cardStart - 0.2 || t >= switchTime)
    : t >= badgeStart;
  const badgeLabel =
    t >= switchTime
      ? item.globeLabel2 ?? "East Asia · 东亚"
      : item.globeLabel1 ?? "China · 中国";
  const pulse = (t * 0.9) % 1;

  return (
    <AbsoluteFill style={{ opacity: alpha, pointerEvents: "none" }}>
      {showGlobe ? (
        <svg viewBox="0 0 1920 1080" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
          <defs>
            <radialGradient id="globeSphere" cx="35%" cy="35%" r="70%">
              <stop offset="0%" stopColor="#1E3A5F" />
              <stop offset="70%" stopColor="#0F2342" />
              <stop offset="100%" stopColor="#081226" />
            </radialGradient>
            <clipPath id="globeClip">
              <circle cx={gx} cy={gy} r={radius} />
            </clipPath>
          </defs>

          <g transform={`translate(${gx}, ${gy}) rotate(${(t * 3.5) % 360})`}>
            <circle cx={0} cy={0} r={radius + 38} fill="none" stroke="rgba(251, 191, 36, 0.28)" strokeWidth={2} />
            {Array.from({ length: 36 }, (_, a) => {
              const ang = (a * 10 * Math.PI) / 180;
              const r1 = radius + 30;
              const r2 = radius + (a % 3 === 0 ? 48 : 38);
              return (
                <line
                  key={a}
                  x1={Math.cos(ang) * r1}
                  y1={Math.sin(ang) * r1}
                  x2={Math.cos(ang) * r2}
                  y2={Math.sin(ang) * r2}
                  stroke={a % 3 === 0 ? "rgba(251, 191, 36, 0.65)" : "rgba(148, 163, 184, 0.28)"}
                  strokeWidth={a % 3 === 0 ? 2.2 : 1.4}
                />
              );
            })}
          </g>

          <circle
            cx={gx}
            cy={gy}
            r={radius}
            fill="url(#globeSphere)"
            fillOpacity={0.62}
            stroke="rgba(56, 189, 248, 0.6)"
            strokeWidth={3}
          />

          <g clipPath="url(#globeClip)">
            {[-60, -30, 0, 30, 60].map((lat) => {
              const yOff = Math.sin((lat * Math.PI) / 180) * radius;
              const w = Math.cos((lat * Math.PI) / 180) * radius;
              return (
                <line
                  key={lat}
                  x1={gx - w}
                  y1={gy - yOff}
                  x2={gx + w}
                  y2={gy - yOff}
                  stroke={lat === 30 ? "rgba(251, 191, 36, 0.42)" : "rgba(56, 189, 248, 0.22)"}
                  strokeWidth={lat === 0 ? 2 : 1.3}
                />
              );
            })}
            {Array.from({ length: 6 }, (_, m) => {
              const ang = t * 0.35 + (m * Math.PI) / 6;
              const rx = Math.max(3, Math.abs(Math.cos(ang)) * radius);
              return (
                <ellipse
                  key={m}
                  cx={gx}
                  cy={gy}
                  rx={rx}
                  ry={radius}
                  fill="none"
                  stroke="rgba(56, 189, 248, 0.22)"
                  strokeWidth={1.4}
                />
              );
            })}
          </g>

          {showGlobeBadge ? (
            <g>
              <circle
                cx={gx}
                cy={gy}
                r={55 + pulse * 120}
                fill="none"
                stroke={`rgba(251, 191, 36, ${(1 - pulse) * 0.55})`}
                strokeWidth={2.2}
              />
            </g>
          ) : null}
        </svg>
      ) : null}

      {showGlobeBadge ? (
        <div
          style={{
            ...(showGlobe ? {} : glassPanel),
            position: "absolute",
            ...(showGlobe
              ? {
                  left: gx,
                  top: gy,
                  transform: "translate(-50%, -50%)",
                  padding: "12px 30px",
                  borderRadius: 16,
                  backgroundColor: "rgba(12, 18, 32, 0.56)",
                  border: "1.5px solid #FBBF24",
                }
              : {
                  right: 96,
                  top: 210,
                  padding: "14px 28px",
                  borderRadius: 999,
                  border: "1.5px solid rgba(251, 191, 36, 0.6)",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 12,
                }),
            boxShadow: "0 14px 36px rgba(0,0,0,0.34)",
            color: "#FEF08A",
            fontSize: 27,
            fontWeight: 700,
            whiteSpace: "nowrap",
          }}
        >
          {!showGlobe ? (
            <span
              style={{
                width: 11,
                height: 11,
                borderRadius: "50%",
                backgroundColor: "#FBBF24",
                boxShadow: "0 0 12px rgba(251, 191, 36, 0.9)",
                display: "inline-block",
              }}
            />
          ) : null}
          {badgeLabel}
        </div>
      ) : null}

      {cardVisible ? (
        <div
          style={{
            ...glassPanel,
            position: "absolute",
            left: 100,
            top: 175,
            width: 700,
            padding: "36px 40px",
            borderColor: "rgba(251, 191, 36, 0.38)",
            opacity: cardIn * cardOut,
            transform: `translateY(${(1 - cardIn) * 32}px)`,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              paddingBottom: 18,
              marginBottom: 20,
              borderBottom: "1px solid rgba(255,255,255,0.14)",
            }}
          >
            <div>
              <div style={{ fontSize: 30, fontWeight: 700, color: "#FBBF24" }}>
                {item.cardTitleEn}
              </div>
              {item.cardTitleZh ? (
                <div style={{ fontSize: 22, color: "#94A3B8", marginTop: 4 }}>
                  {item.cardTitleZh}
                </div>
              ) : null}
            </div>
            {item.badge ? (
              <div
                style={{
                  padding: "7px 18px",
                  borderRadius: 99,
                  backgroundColor: "rgba(239, 68, 68, 0.22)",
                  border: "1px solid rgba(239, 68, 68, 0.55)",
                  color: "#FCA5A5",
                  fontSize: 20,
                  fontWeight: 700,
                }}
              >
                {item.badge}
              </div>
            ) : null}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {item.rows.map((row, idx) => {
              const rowP = spring({
                frame: Math.max(0, Math.round((t - cardStart - 0.12 * idx) * fps)),
                fps,
                config: { damping: 16, stiffness: 120 },
              });
              return (
                <div
                  key={row.label}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "16px 20px",
                    borderRadius: 14,
                    backgroundColor: "rgba(255,255,255,0.05)",
                    border: "1px solid rgba(255,255,255,0.07)",
                    opacity: rowP,
                    transform: `translateX(${(1 - rowP) * -22}px)`,
                  }}
                >
                  <span style={{ fontSize: 23, color: "#94A3B8", fontWeight: 500 }}>
                    {row.label}
                  </span>
                  <span style={{ fontSize: 29, color: "#FFFFFF", fontWeight: 700 }}>
                    {row.value}
                    {row.zh ? (
                      <span style={{ color: "#FCD34D", marginLeft: 10, fontSize: 24 }}>
                        {row.zh}
                      </span>
                    ) : null}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

const AreaInfographicOverlay: React.FC<{
  item: Extract<GraphicOverlayItem, { kind: "area_infographic" }>;
  hasTopNote: boolean;
}> = ({ item, hasTopNote }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (t < item.start || t > item.end) return null;
  const alpha = computeWindowAlpha(t, item.start, item.end, 0.35, 0.35);
  const localFrame = Math.max(0, Math.round((t - item.start) * fps));
  const enter = spring({ frame: localFrame, fps, config: { damping: 16, stiffness: 120 } });

  const animEnd = computeAnimEnd(item.start, item.end, 0.15, 1.45, 0.9);
  const numProg = interpolate(seg(t, item.start + 0.15, animEnd), [0, 1], [0, 1], {
    easing: Easing.out(Easing.cubic),
  });
  const topY = hasTopNote ? 228 : 196;

  return (
    <AbsoluteFill style={{ opacity: alpha, pointerEvents: "none" }}>
      {/* Left Hero Stat Card */}
      <div
        style={{
          ...glassPanel,
          position: "absolute",
          left: 88,
          top: topY + 25,
          width: 560,
          padding: "34px 38px",
          opacity: enter,
          transform: `translateY(${(1 - enter) * 26}px)`,
        }}
      >
        <div
          style={{
            display: "inline-block",
            padding: "6px 16px",
            borderRadius: 99,
            backgroundColor: "rgba(245, 158, 11, 0.22)",
            color: "#FCD34D",
            fontSize: 19,
            fontWeight: 700,
            letterSpacing: "0.06em",
            marginBottom: 16,
          }}
        >
          {item.statTag}
        </div>
        <div style={{ fontSize: 66, fontWeight: 800, lineHeight: 1.08, marginBottom: 14 }}>
          {item.statNumTarget
            ? `~${(item.statNumTarget * numProg).toFixed(1)}M km²`
            : item.statValue}
        </div>
        <div style={{ fontSize: 26, color: "#E2E8F0", lineHeight: 1.45 }}>
          {item.statDescEn}
          {item.statDescZh ? (
            <div style={{ color: "#94A3B8", fontSize: 23, marginTop: 6 }}>{item.statDescZh}</div>
          ) : null}
        </div>
      </div>

      {/* Right Wide Comparison Bar Chart */}
      <div
        style={{
          ...glassPanel,
          position: "absolute",
          left: 710,
          right: 88,
          top: topY,
          padding: "36px 42px",
          borderColor: "rgba(251, 191, 36, 0.35)",
          opacity: enter,
          transform: `translateY(${(1 - enter) * 26}px)`,
        }}
      >
        <div style={{ fontSize: 24, fontWeight: 700, color: "#FBBF24", marginBottom: 24 }}>
          {item.chartTitle}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          {item.items.map((row, idx) => {
            const bp = interpolate(
              seg(t, item.start + 0.15 + idx * 0.08, item.start + 1.35 + idx * 0.08),
              [0, 1],
              [0, 1],
              { easing: Easing.out(Easing.cubic) }
            );
            const pct = (row.value / row.max) * 100 * bp;
            return (
              <div
                key={row.label}
                style={{
                  display: "grid",
                  gridTemplateColumns: "270px 1fr 110px",
                  alignItems: "center",
                  gap: 20,
                }}
              >
                <div
                  style={{
                    fontSize: row.accent ? 26 : 23,
                    fontWeight: row.accent ? 700 : 500,
                    color: row.accent ? "#FEF08A" : "#CBD5E1",
                  }}
                >
                  {row.label}
                </div>
                <div
                  style={{
                    height: 30,
                    borderRadius: 10,
                    backgroundColor: "rgba(255,255,255,0.08)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${pct}%`,
                      borderRadius: 10,
                      background: row.accent
                        ? "linear-gradient(90deg, #EF4444, #FBBF24)"
                        : "rgba(56, 189, 248, 0.55)",
                    }}
                  />
                </div>
                <div
                  style={{
                    fontSize: row.accent ? 25 : 22,
                    fontWeight: row.accent ? 700 : 500,
                    color: row.accent ? "#FDE047" : "#94A3B8",
                    textAlign: "right",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {(row.value * bp).toFixed(2)}
                  {row.unit ?? "M"}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const TempleOfHeavenSvg: React.FC<{ drawProg: number; fillProg: number }> = ({
  drawProg,
  fillProg,
}) => {
  const dash = (len: number, idx: number, total = 18) => {
    const stagger = (idx / total) * 0.35;
    const p = clamp((drawProg - stagger) / 0.65, 0, 1);
    return { strokeDasharray: `${len} ${len}`, strokeDashoffset: len * (1 - p) };
  };

  return (
    <svg
      viewBox="0 0 600 460"
      style={{
        position: "absolute",
        left: 880,
        top: 120,
        width: 850,
        height: 650,
        pointerEvents: "none",
      }}
    >
      <defs>
        <linearGradient id="thGold" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#F59E0B" />
          <stop offset="50%" stopColor="#FDE68A" />
          <stop offset="100%" stopColor="#FB923C" />
        </linearGradient>
        <linearGradient id="thAzure" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#2563EB" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#1E3A8A" stopOpacity="0.78" />
        </linearGradient>
        <linearGradient id="thCrimson" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#DC2626" stopOpacity="0.58" />
          <stop offset="100%" stopColor="#7F1D1D" stopOpacity="0.7" />
        </linearGradient>
      </defs>

      <circle cx={300} cy={240} r={215} fill="none" stroke="rgba(251,191,36,0.18)" strokeWidth={1.3} strokeDasharray="8 8" />
      <circle cx={300} cy={240} r={180} fill="none" stroke="rgba(56,189,248,0.18)" strokeWidth={1.1} />

      {/* Three marble tiers */}
      {[
        "M 74 398 Q 300 416 526 398 L 534 422 Q 300 442 66 422 Z",
        "M 110 368 Q 300 384 490 368 L 496 392 Q 300 409 104 392 Z",
        "M 146 338 Q 300 352 454 338 L 460 362 Q 300 377 140 362 Z",
      ].map((d, i) => (
        <g key={i}>
          <path d={d} fill="rgba(248, 250, 252, 0.24)" opacity={fillProg} />
          <path d={d} fill="none" stroke="#E2E8F0" strokeWidth={1.8} {...dash(1050, i)} />
        </g>
      ))}

      {/* Main Hall */}
      <path d="M 202 254 L 398 254 L 398 342 Q 300 350 202 342 Z" fill="url(#thCrimson)" opacity={fillProg} />
      <path d="M 202 254 L 398 254 L 398 342 Q 300 350 202 342 Z" fill="none" stroke="#FBBF24" strokeWidth={2} {...dash(620, 4)} />
      <path d="M 218 254 L 218 343 M 242 254 L 242 344 M 268 254 L 268 345 M 332 254 L 332 345 M 358 254 L 358 344 M 382 254 L 382 343" fill="none" stroke="#FDE68A" strokeWidth={1.8} {...dash(560, 5)} />
      <path d="M 282 345 L 282 276 L 318 276 L 318 345 M 300 276 L 300 345" fill="none" stroke="#FEF08A" strokeWidth={1.8} {...dash(260, 6)} />

      {/* Lower Roof */}
      <path d="M 122 246 C 175 244 205 232 225 208 L 375 208 C 395 232 425 244 478 246 Q 300 264 122 246 Z" fill="url(#thAzure)" opacity={fillProg} />
      <path d="M 116 244 C 132 249 162 247 188 238 C 205 230 216 218 226 208 L 374 208 C 384 218 395 230 412 238 C 438 247 468 249 484 244 C 466 254 396 263 300 263 C 204 263 134 254 116 244 Z" fill="none" stroke="url(#thGold)" strokeWidth={2.5} {...dash(840, 8)} />

      {/* Middle Roof */}
      <path d="M 232 192 L 368 192 L 368 208 L 232 208 Z" fill="url(#thCrimson)" opacity={fillProg} />
      <path d="M 156 190 C 198 188 222 174 242 152 L 358 152 C 378 174 402 188 444 190 Q 300 206 156 190 Z" fill="url(#thAzure)" opacity={fillProg} />
      <path d="M 150 188 C 166 193 192 190 214 180 C 228 172 236 162 244 152 L 356 152 C 364 162 372 172 386 180 C 408 190 434 193 450 188 C 430 198 378 205 300 205 C 222 205 170 198 150 188 Z" fill="none" stroke="url(#thGold)" strokeWidth={2.5} {...dash(720, 10)} />

      {/* Top Roof & Spire */}
      <path d="M 188 136 C 234 128 268 102 300 66 C 332 102 366 128 412 136 Q 300 152 188 136 Z" fill="url(#thAzure)" opacity={fillProg} />
      <path d="M 182 134 C 202 138 232 128 258 108 C 276 94 290 78 300 64 C 310 78 324 94 342 108 C 368 128 398 138 418 134 C 398 144 358 150 300 150 C 242 150 202 144 182 134 Z" fill="none" stroke="url(#thGold)" strokeWidth={2.6} {...dash(620, 12)} />
      <path d="M 290 64 L 310 64 L 306 54 L 303 44 C 306 38 303 30 300 24 C 297 30 294 38 297 44 L 294 54 Z" fill="#FBBF24" opacity={fillProg} />
    </svg>
  );
};

const BlueprintCalloutOverlay: React.FC<{
  item: Extract<GraphicOverlayItem, { kind: "blueprint_callout" }>;
}> = ({ item }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (t < item.start || t > item.end) return null;
  const alpha = computeWindowAlpha(t, item.start, item.end, 0.35, 0.4);
  const localFrame = Math.max(0, Math.round((t - item.start) * fps));
  const enter = spring({ frame: localFrame, fps, config: { damping: 16, stiffness: 120 } });
  const drawProg = interpolate(seg(t, item.start + 0.08, item.start + 1.9), [0, 1], [0, 1], {
    easing: Easing.inOut(Easing.cubic),
  });
  const fillProg = interpolate(seg(t, item.start + 0.9, item.start + 2.2), [0, 1], [0, 1], {
    easing: Easing.out(Easing.cubic),
  });

  return (
    <AbsoluteFill style={{ opacity: alpha, pointerEvents: "none" }}>
      <div
        style={{
          ...glassPanel,
          position: "absolute",
          left: 96,
          top: 230,
          width: 600,
          padding: "36px 40px",
          opacity: enter,
          transform: `translateY(${(1 - enter) * 26}px)`,
        }}
      >
        <div
          style={{
            display: "inline-block",
            padding: "6px 16px",
            borderRadius: 99,
            backgroundColor: "rgba(239, 68, 68, 0.22)",
            color: "#FCA5A5",
            fontSize: 19,
            fontWeight: 700,
            letterSpacing: "0.06em",
            marginBottom: 16,
          }}
        >
          {item.tag}
        </div>
        <div style={{ fontSize: 62, fontWeight: 800, lineHeight: 1.1, marginBottom: 14 }}>
          {item.title}
        </div>
        <div style={{ fontSize: 27, color: "#CBD5E1", lineHeight: 1.48 }}>
          {item.descEn}
          {item.descZh ? (
            <div style={{ color: "#94A3B8", fontSize: 24, marginTop: 6 }}>{item.descZh}</div>
          ) : null}
        </div>
      </div>

      {item.svgPreset === "temple_of_heaven" ? (
        <TempleOfHeavenSvg drawProg={drawProg} fillProg={fillProg} />
      ) : null}
    </AbsoluteFill>
  );
};

const CalligraphyBubblesOverlay: React.FC<{
  item: Extract<GraphicOverlayItem, { kind: "calligraphy_bubbles" }>;
}> = ({ item }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (t < item.start || t > item.end) return null;
  const alpha = computeWindowAlpha(t, item.start, item.end, 0.35, 0.4);
  const localFrame = Math.max(0, Math.round((t - item.start) * fps));
  const enter = spring({ frame: localFrame, fps, config: { damping: 16, stiffness: 120 } });
  const medScale = spring({
    frame: Math.max(0, Math.round((t - item.start - 0.1) * fps)),
    fps,
    config: { damping: 14, stiffness: 130 },
  });
  const revealPct = Math.round(
    interpolate(seg(t, item.start + 0.35, item.start + 1.65), [0, 1], [0, 100], {
      easing: Easing.out(Easing.cubic),
    })
  );

  return (
    <AbsoluteFill style={{ opacity: alpha, pointerEvents: "none" }}>
      <div
        style={{
          ...glassPanel,
          position: "absolute",
          left: 96,
          top: 215,
          width: 600,
          padding: "36px 40px",
          opacity: enter,
          transform: `translateY(${(1 - enter) * 26}px)`,
        }}
      >
        <div
          style={{
            display: "inline-block",
            padding: "6px 16px",
            borderRadius: 99,
            backgroundColor: "rgba(56, 189, 248, 0.22)",
            color: "#7DD3FC",
            fontSize: 19,
            fontWeight: 700,
            letterSpacing: "0.06em",
            marginBottom: 16,
          }}
        >
          {item.tag}
        </div>
        <div style={{ fontSize: 62, fontWeight: 800, lineHeight: 1.1, marginBottom: 14 }}>
          {item.title}
        </div>
        <div style={{ fontSize: 27, color: "#CBD5E1", lineHeight: 1.48 }}>
          {item.descEn}
          {item.descZh ? (
            <div style={{ color: "#94A3B8", fontSize: 24, marginTop: 6 }}>{item.descZh}</div>
          ) : null}
        </div>
      </div>

      {/* Right Transparent Gold-Rimmed Calligraphy Medallion */}
      <div
        style={{
          ...glassPanel,
          position: "absolute",
          left: 1290,
          top: 430,
          width: 340,
          height: 340,
          borderRadius: "50%",
          transform: `translate(-50%, -50%) scale(${medScale})`,
          backgroundColor: "rgba(15, 23, 42, 0.44)",
          border: "2px solid rgba(251, 191, 36, 0.7)",
          boxShadow: "0 0 42px rgba(251, 191, 36, 0.24), 0 18px 42px rgba(0, 0, 0, 0.4)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            width: 304,
            height: 304,
            borderRadius: "50%",
            border: "1.5px solid rgba(251, 191, 36, 0.32)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              fontSize: 126,
              fontWeight: 800,
              color: "#FDE68A",
              fontFamily: "'PingFang SC', 'Heiti SC', serif",
              textShadow: "0 4px 18px rgba(0, 0, 0, 0.72)",
              clipPath: `inset(0 ${100 - revealPct}% 0 0)`,
            }}
          >
            {item.centerText}
          </div>
        </div>
      </div>

      {/* Floating Transparent Vocab Bubbles */}
      {item.bubbles.map((b, i) => {
        const bp = spring({
          frame: Math.max(0, Math.round((t - item.start - b.delay) * fps)),
          fps,
          config: { damping: 13, stiffness: 130 },
        });
        const bob = Math.sin(t * 2.2 + i * 1.8) * 8;
        return (
          <div
            key={b.text}
            style={{
              position: "absolute",
              left: b.x,
              top: b.y + bob,
              transform: `translate(-50%, -50%) scale(${bp})`,
              padding: "13px 26px",
              borderRadius: 999,
              backgroundColor: "rgba(15, 23, 42, 0.48)",
              border: `1.5px solid ${b.color}`,
              color: "#F8FAFC",
              fontSize: 25,
              fontWeight: 700,
              boxShadow: "0 12px 28px rgba(0,0,0,0.38)",
              whiteSpace: "nowrap",
            }}
          >
            {b.text}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const WavingFlagShowcaseOverlay: React.FC<{
  item: Extract<GraphicOverlayItem, { kind: "waving_flag_showcase" }>;
}> = ({ item }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (t < item.start || t > item.end) return null;
  const alpha = computeWindowAlpha(t, item.start, item.end, 0.35, 0.4);
  const localFrame = Math.max(0, Math.round((t - item.start) * fps));
  const enter = spring({ frame: localFrame, fps, config: { damping: 16, stiffness: 120 } });

  const fx = 860;
  const fy = 195;
  const fw = 760;
  const fh = 506;
  const cols = 76;
  const colW = fw / cols;

  // Star coordinates on 30x20 grid
  const unit = fw / 30;
  const bigX = 5 * unit;
  const bigY = 5 * unit;
  const smallStars = [
    [10 * unit, 2 * unit],
    [12 * unit, 4 * unit],
    [12 * unit, 7 * unit],
    [10 * unit, 9 * unit],
  ];

  const makeStarPoints = (cx: number, cy: number, r: number, rot: number) => {
    const pts: string[] = [];
    for (let i = 0; i < 10; i++) {
      const rad = i % 2 === 0 ? r : r * 0.382;
      const a = rot + (i * Math.PI) / 5;
      pts.push(`${(cx + Math.cos(a) * rad).toFixed(1)},${(cy + Math.sin(a) * rad).toFixed(1)}`);
    }
    return pts.join(" ");
  };

  return (
    <AbsoluteFill style={{ opacity: alpha, pointerEvents: "none" }}>
      <div
        style={{
          ...glassPanel,
          position: "absolute",
          left: 96,
          top: 215,
          width: 610,
          padding: "36px 40px",
          opacity: enter,
          transform: `translateY(${(1 - enter) * 26}px)`,
        }}
      >
        <div
          style={{
            display: "inline-block",
            padding: "6px 16px",
            borderRadius: 99,
            backgroundColor: "rgba(239, 68, 68, 0.25)",
            color: "#FCA5A5",
            fontSize: 19,
            fontWeight: 700,
            letterSpacing: "0.06em",
            marginBottom: 16,
          }}
        >
          {item.tag}
        </div>
        <div style={{ fontSize: 54, fontWeight: 800, lineHeight: 1.1, marginBottom: 14 }}>
          {item.title}
        </div>
        <div style={{ fontSize: 27, color: "#CBD5E1", lineHeight: 1.48 }}>
          {item.descEn}
          {item.descZh ? (
            <div style={{ color: "#94A3B8", fontSize: 24, marginTop: 6 }}>{item.descZh}</div>
          ) : null}
        </div>
      </div>

      {/* Optional SVG Waving Flag (omit when background photo already features the flag) */}
      {item.showFlagGraphic ? (
        <svg viewBox="0 0 1920 1080" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
          <defs>
            <linearGradient id="poleGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#92400E" />
              <stop offset="50%" stopColor="#FDE68A" />
              <stop offset="100%" stopColor="#B45309" />
            </linearGradient>
            <g id="chinaFlagGraphic">
              <rect x={0} y={0} width={fw} height={fh} fill="#DE2910" />
              <polygon points={makeStarPoints(bigX, bigY, 3 * unit, -Math.PI / 2)} fill="#FFDE00" />
              {smallStars.map(([sx, sy], idx) => (
                <polygon
                  key={idx}
                  points={makeStarPoints(sx, sy, 1 * unit, Math.atan2(bigY - sy, bigX - sx))}
                  fill="#FFDE00"
                />
              ))}
            </g>
            {Array.from({ length: cols }, (_, i) => (
              <clipPath key={i} id={`flagSlice-${i}`}>
                <rect x={i * colW} y={0} width={colW + 1.2} height={fh} />
              </clipPath>
            ))}
          </defs>

          <rect x={fx - 10} y={fy - 40} width={20} height={650} rx={4} fill="url(#poleGrad)" />
          <circle cx={fx} cy={fy - 48} r={18} fill="#FBBF24" />

          {Array.from({ length: cols }, (_, i) => {
            const u = i / cols;
            const wavePhase = u * 7.2 - t * 5.2;
            const yOff = Math.sin(wavePhase) * 24 * Math.pow(u, 0.85);
            const shade = Math.cos(wavePhase) * u;
            return (
              <g
                key={i}
                transform={`translate(${fx + 8}, ${fy + yOff})`}
                clipPath={`url(#flagSlice-${i})`}
              >
                <use href="#chinaFlagGraphic" />
                <rect
                  x={i * colW}
                  y={0}
                  width={colW + 1.2}
                  height={fh}
                  fill={
                    shade > 0
                      ? `rgba(255,255,255,${(shade * 0.16).toFixed(3)})`
                      : `rgba(0,0,0,${(-shade * 0.24).toFixed(3)})`
                  }
                />
              </g>
            );
          })}
        </svg>
      ) : null}
    </AbsoluteFill>
  );
};

const TerrainProfileOverlay: React.FC<{
  item: Extract<GraphicOverlayItem, { kind: "terrain_profile" }>;
}> = ({ item }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (t < item.start || t > item.end) return null;
  const alpha = computeWindowAlpha(t, item.start, item.end, 0.35, 0.4);
  const sweepP = interpolate(seg(t, item.start + 0.15, item.start + 2.4), [0, 1], [0, 1], {
    easing: Easing.inOut(Easing.cubic),
  });

  const baseX = 160;
  const endX = 1760;
  const baseY = 770;
  const profile: Array<[number, number]> = [
    [160, 770],
    [235, 425],
    [310, 305],
    [385, 345],
    [465, 295],
    [560, 410],
    [690, 430],
    [820, 560],
    [940, 540],
    [1080, 585],
    [1210, 550],
    [1330, 695],
    [1465, 718],
    [1600, 735],
    [1760, 770],
  ];

  const ridgePath = profile.map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x} ${y}`).join(" ");
  const fillPath = `${ridgePath} L ${endX} ${baseY} L ${baseX} ${baseY} Z`;
  const revealX = baseX + (endX + 40 - baseX) * sweepP;
  const enter = spring({
    frame: Math.max(0, Math.round((t - item.start) * fps)),
    fps,
    config: { damping: 16, stiffness: 120 },
  });

  return (
    <AbsoluteFill style={{ opacity: alpha, pointerEvents: "none" }}>
      {/* Compact Centered Glass Title Pill (no outer box wrapping the landscape) */}
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: 186,
          width: 820,
          height: 62,
          transform: `translateX(-50%) translateY(${(1 - enter) * 18}px)`,
          opacity: enter,
          borderRadius: 18,
          backgroundColor: "rgba(15, 23, 42, 0.48)",
          border: "1.5px solid rgba(255, 255, 255, 0.22)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 25,
          fontWeight: 700,
          color: "#38BDF8",
          letterSpacing: "0.05em",
          fontFamily: "'SF Pro Display', 'PingFang SC', sans-serif",
        }}
      >
        {item.header}
      </div>

      {/* Full-bleed Open-Canvas Topography Curve */}
      <svg viewBox="0 0 1920 1080" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
        <defs>
          <linearGradient id="terrainGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#F59E0B" stopOpacity="0.38" />
            <stop offset="55%" stopColor="#38BDF8" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#2DD4BF" stopOpacity="0.18" />
          </linearGradient>
          <clipPath id="terrainReveal">
            <rect x={0} y={0} width={revealX} height={1080} />
          </clipPath>
        </defs>

        <line
          x1={baseX}
          y1={baseY}
          x2={endX}
          y2={baseY}
          stroke="rgba(56, 189, 248, 0.45)"
          strokeWidth={2}
          strokeDasharray="8 6"
        />

        <g clipPath="url(#terrainReveal)">
          <path d={fillPath} fill="url(#terrainGrad)" />
          <path d={ridgePath} fill="none" stroke="#FDE047" strokeWidth={4.2} strokeLinejoin="round" />
        </g>
      </svg>

      {/* Floating Compact Translucent Step Badges */}
      {item.steps.map((s) => {
        const sp = spring({
          frame: Math.max(0, Math.round((t - item.start - s.delay) * fps)),
          fps,
          config: { damping: 14, stiffness: 130 },
        });
        return (
          <div
            key={s.tag}
            style={{
              position: "absolute",
              left: s.x,
              top: s.y,
              width: 380,
              padding: "12px 24px",
              transform: `translate(-50%, -50%) scale(${sp})`,
              borderRadius: 16,
              backgroundColor: "rgba(15, 23, 42, 0.52)",
              border: `2px solid ${s.color}`,
              textAlign: "center",
              boxShadow: "0 12px 30px rgba(0,0,0,0.38)",
              whiteSpace: "nowrap",
            }}
          >
            <div style={{ fontSize: 22, fontWeight: 700, color: s.color }}>{s.tag}</div>
            <div style={{ fontSize: 19, color: "#E2E8F0", marginTop: 4 }}>{s.sub}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const ElevationRulerOverlay: React.FC<{
  item: Extract<GraphicOverlayItem, { kind: "elevation_ruler" }>;
}> = ({ item }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (t < item.start || t > item.end) return null;
  const alpha = computeWindowAlpha(t, item.start, item.end, 0.4, 0.4);
  const localFrame = Math.max(0, Math.round((t - item.start) * fps));
  const enter = spring({ frame: localFrame, fps, config: { damping: 16, stiffness: 110 } });

  const animEnd = computeAnimEnd(item.start, item.end, 0.25, 2.2, 1.2);
  const progress = interpolate(
    t,
    [item.start + 0.25, animEnd],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    }
  );
  const currentMeters = Math.round(item.fromValue + (item.toValue - item.fromValue) * progress);

  const ticks = item.ticks ?? [
    { label: "8,849 m", ratio: 1 },
    { label: "6,000 m", ratio: 0.678 },
    { label: "3,000 m", ratio: 0.339 },
    { label: "0 m", ratio: 0 },
  ];

  const bx = (item.beaconX ?? 0.4) * 1920;
  const by = (item.beaconY ?? 0.14) * 1080;
  const pulse = (t * 1.4) % 1;
  const badgeStart = animEnd - 0.35;
  const badgePop = spring({
    frame: Math.max(0, Math.round((t >= badgeStart ? t - badgeStart : 0) * fps)),
    fps,
    config: { damping: 13, stiffness: 130 },
  });

  return (
    <AbsoluteFill style={{ opacity: alpha, pointerEvents: "none" }}>
      {/* Summit Pulse Beacon on Real Everest Photo */}
      <svg viewBox="0 0 1920 1080" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
        <circle
          cx={bx}
          cy={by}
          r={12 + pulse * 64}
          fill="none"
          stroke={`rgba(251, 191, 36, ${(1 - pulse) * 0.85})`}
          strokeWidth={3}
        />
        <circle cx={bx} cy={by} r={8} fill="#FDE047" />
      </svg>

      {/* Right Tall Vertical Elevation Gauge Card */}
      <div
        style={{
          ...glassPanel,
          position: "absolute",
          right: 76,
          top: 210,
          width: 600,
          height: 580,
          padding: "34px 40px",
          borderColor: "rgba(255, 255, 255, 0.24)",
          opacity: enter,
          transform: `translateY(${(1 - enter) * 28}px)`,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ fontSize: 22, fontWeight: 700, color: "#38BDF8", marginBottom: 24 }}>
          {item.eyebrow}
        </div>

        <div style={{ display: "flex", flex: 1, gap: 36, alignItems: "stretch" }}>
          {/* Vertical Thermometer Ruler */}
          <div style={{ position: "relative", width: 128, height: 410 }}>
            <div
              style={{
                position: "absolute",
                left: 10,
                top: 10,
                bottom: 10,
                width: 14,
                borderRadius: 7,
                backgroundColor: "rgba(255,255,255,0.12)",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  right: 0,
                  bottom: 0,
                  height: `${progress * 100}%`,
                  borderRadius: 7,
                  background: "linear-gradient(to top, #0284C7, #F59E0B, #FDE047)",
                }}
              />
            </div>

            {ticks.map((tk) => (
              <div
                key={tk.label}
                style={{
                  position: "absolute",
                  left: 32,
                  bottom: 10 + tk.ratio * 390 - 11,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <div style={{ width: 14, height: 2, backgroundColor: "rgba(255,255,255,0.45)" }} />
                <span style={{ fontSize: 19, color: "#94A3B8", whiteSpace: "nowrap" }}>
                  {tk.label}
                </span>
              </div>
            ))}
          </div>

          {/* Right Readout */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
            <div
              style={{
                fontSize: 78,
                fontWeight: 800,
                color: "#FDE047",
                lineHeight: 1.05,
                fontVariantNumeric: "tabular-nums",
                marginBottom: 18,
              }}
            >
              {currentMeters.toLocaleString("en-US")} {item.unit ?? "m"}
            </div>
            <div style={{ fontSize: 33, fontWeight: 700, color: "#FFFFFF", marginBottom: 8 }}>
              {item.title}
            </div>
            {item.subtitle ? (
              <div style={{ fontSize: 24, color: "#CBD5E1", marginBottom: 34 }}>{item.subtitle}</div>
            ) : null}

            {item.badge && progress > 0.72 ? (
              <div
                style={{
                  alignSelf: "flex-start",
                  padding: "12px 24px",
                  borderRadius: 16,
                  backgroundColor: "rgba(245, 158, 11, 0.22)",
                  border: "2px solid #F59E0B",
                  color: "#FCD34D",
                  fontSize: 24,
                  fontWeight: 700,
                  transform: `scale(${badgePop})`,
                }}
              >
                {item.badge}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const RiverCourseHudOverlay: React.FC<{
  item: Extract<GraphicOverlayItem, { kind: "river_course_hud" }>;
}> = ({ item }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (t < item.start || t > item.end) return null;
  const alpha = computeWindowAlpha(t, item.start, item.end, 0.4, 0.35);
  const localFrame = Math.max(0, Math.round((t - item.start) * fps));
  const enter = spring({ frame: localFrame, fps, config: { damping: 16, stiffness: 120 } });

  const animEnd = computeAnimEnd(item.start, item.end, 0.15, 2.0, 1.0);
  const prog = interpolate(seg(t, item.start + 0.15, animEnd), [0, 1], [0, 1], {
    easing: Easing.inOut(Easing.cubic),
  });
  const km = Math.round(item.metricTarget * prog);

  return (
    <AbsoluteFill style={{ opacity: alpha, pointerEvents: "none" }}>
      {/* Left Metric Card */}
      <div
        style={{
          ...glassPanel,
          position: "absolute",
          left: 96,
          top: 228,
          width: 580,
          padding: "32px 38px",
          opacity: enter,
          transform: `translateY(${(1 - enter) * 26}px)`,
        }}
      >
        <div
          style={{
            display: "inline-block",
            padding: "6px 16px",
            borderRadius: 99,
            backgroundColor: "rgba(45, 212, 191, 0.22)",
            color: "#5EEAD4",
            fontSize: 19,
            fontWeight: 700,
            letterSpacing: "0.06em",
            marginBottom: 14,
          }}
        >
          {item.tag}
        </div>
        <div
          style={{
            fontSize: 64,
            fontWeight: 800,
            lineHeight: 1.08,
            marginBottom: 12,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {km.toLocaleString("en-US")}
          {item.metricSuffix ?? "+ km"}
        </div>
        <div style={{ fontSize: 27, color: "#E2E8F0", fontWeight: 600 }}>{item.title}</div>
        {item.subtitle ? (
          <div style={{ fontSize: 23, color: "#94A3B8", marginTop: 4 }}>{item.subtitle}</div>
        ) : null}
        <div
          style={{
            marginTop: 22,
            height: 14,
            borderRadius: 99,
            backgroundColor: "rgba(255,255,255,0.1)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${prog * 100}%`,
              borderRadius: 99,
              background: "linear-gradient(90deg, #0EA5E9, #2DD4BF)",
            }}
          />
        </div>
      </div>

      {/* Right Wide River Course Milestone Bar */}
      <div
        style={{
          ...glassPanel,
          position: "absolute",
          left: 740,
          right: 96,
          top: 228,
          padding: "30px 42px 42px",
          borderColor: "rgba(255, 255, 255, 0.24)",
          opacity: enter,
          transform: `translateY(${(1 - enter) * 26}px)`,
        }}
      >
        <div style={{ fontSize: 22, fontWeight: 700, color: "#5EEAD4", marginBottom: 34 }}>
          {item.courseTitle}
        </div>

        <div style={{ position: "relative", height: 76 }}>
          <div
            style={{
              position: "absolute",
              left: 36,
              right: 36,
              top: 12,
              height: 6,
              borderRadius: 99,
              backgroundColor: "rgba(255,255,255,0.14)",
            }}
          />
          <div
            style={{
              position: "absolute",
              left: 36,
              top: 12,
              width: `calc((100% - 72px) * ${prog})`,
              height: 6,
              borderRadius: 99,
              backgroundColor: "#2DD4BF",
            }}
          />
          {item.stops.map((s) => {
            const active = prog >= s.frac - 0.02;
            const align = s.frac === 0 ? "flex-start" : s.frac === 1 ? "flex-end" : "center";
            const tx = s.frac === 0 ? "0%" : s.frac === 1 ? "-100%" : "-50%";
            return (
              <div
                key={s.label}
                style={{
                  position: "absolute",
                  left: `calc(36px + (100% - 72px) * ${s.frac})`,
                  top: 2,
                  transform: `translateX(${tx})`,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: align,
                  gap: 14,
                }}
              >
                <div
                  style={{
                    width: active ? 22 : 16,
                    height: active ? 22 : 16,
                    borderRadius: "50%",
                    backgroundColor: active ? "#5EEAD4" : "#475569",
                    boxShadow: active ? "0 0 14px rgba(94, 234, 212, 0.85)" : "none",
                  }}
                />
                <span
                  style={{
                    fontSize: 20,
                    fontWeight: 700,
                    color: active ? "#F8FAFC" : "#64748B",
                    whiteSpace: "nowrap",
                  }}
                >
                  {s.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const QaQuizOverlay: React.FC<{
  item: Extract<GraphicOverlayItem, { kind: "qa_quiz" }>;
}> = ({ item }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  if (t < item.start || t > item.end) return null;

  const activeQuiz = item.items.find((it) => t >= it.qStart && t < it.end);
  if (!activeQuiz) return null;

  const boxAlpha = computeWindowAlpha(t, item.start, item.end, 0.35, 0.35);
  const qIn = spring({
    frame: Math.max(0, Math.round((t - activeQuiz.qStart) * fps)),
    fps,
    config: { damping: 16, stiffness: 140 },
  });
  const answerActive = t >= activeQuiz.aStart;
  const aIn = answerActive
    ? spring({
        frame: Math.max(0, Math.round((t - activeQuiz.aStart) * fps)),
        fps,
        config: { damping: 15, stiffness: 150 },
      })
    : 0;

  const x = item.x ?? 1060;
  const y = item.y ?? 228;
  const w = item.w ?? 780;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          ...glassPanel,
          position: "absolute",
          left: x,
          top: y,
          width: w,
          padding: "26px 34px",
          backgroundColor: "rgba(15, 23, 42, 0.48)",
          border: "1.5px solid rgba(56, 189, 248, 0.45)",
          opacity: boxAlpha * qIn,
          transform: `translateY(${(1 - qIn) * 16}px)`,
        }}
      >
        <div
          style={{
            fontSize: 16,
            fontWeight: 700,
            letterSpacing: "0.08em",
            color: "#38BDF8",
            textTransform: "uppercase",
            marginBottom: 12,
          }}
        >
          {item.tag ?? "INTERACTIVE QUIZ · 互动问答"}
        </div>

        <div
          style={{
            fontSize: activeQuiz.qEn.length > 52 ? 25 : 29,
            fontWeight: 700,
            color: "#FFFFFF",
            lineHeight: 1.32,
          }}
        >
          {activeQuiz.qEn}
        </div>
        <div
          style={{
            fontSize: 22,
            fontWeight: 600,
            color: "#CBD5E1",
            lineHeight: 1.35,
            marginTop: 6,
          }}
        >
          {activeQuiz.qZh}
        </div>

        {!answerActive ? (
          <div
            style={{
              marginTop: 20,
              fontSize: 22,
              fontWeight: 700,
              color: "#F59E0B",
            }}
          >
            {item.thinkingText ?? "🤔 Think about it... 想一想"}
          </div>
        ) : (
          <div
            style={{
              marginTop: 18,
              padding: "14px 20px",
              borderRadius: 14,
              backgroundColor: "rgba(34, 197, 94, 0.25)",
              border: "1.5px solid #22c55e",
              opacity: aIn,
              transform: `translateY(${(1 - aIn) * 8}px)`,
            }}
          >
            <div
              style={{
                fontSize: activeQuiz.aEn.length > 46 ? 21 : 24,
                fontWeight: 800,
                color: "#4ADE80",
                lineHeight: 1.3,
              }}
            >
              ✓ {activeQuiz.aEn}
            </div>
            <div
              style={{
                fontSize: 20,
                fontWeight: 600,
                color: "#BBF7D0",
                lineHeight: 1.32,
                marginTop: 4,
              }}
            >
              {activeQuiz.aZh}
            </div>
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

export const GraphicOverlays: React.FC<{
  overlays: GraphicOverlayItem[];
  hasTopNote: boolean;
}> = ({ overlays, hasTopNote }) => {
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {overlays.map((item) => {
        switch (item.kind) {
          case "cover_hero":
            return <CoverHeroOverlay key={item.id} item={item} />;
          case "globe_fact_card":
            return <GlobeFactCardOverlay key={item.id} item={item} />;
          case "area_infographic":
            return <AreaInfographicOverlay key={item.id} item={item} hasTopNote={hasTopNote} />;
          case "blueprint_callout":
            return <BlueprintCalloutOverlay key={item.id} item={item} />;
          case "calligraphy_bubbles":
            return <CalligraphyBubblesOverlay key={item.id} item={item} />;
          case "waving_flag_showcase":
            return <WavingFlagShowcaseOverlay key={item.id} item={item} />;
          case "terrain_profile":
            return <TerrainProfileOverlay key={item.id} item={item} />;
          case "elevation_ruler":
            return <ElevationRulerOverlay key={item.id} item={item} />;
          case "river_course_hud":
            return <RiverCourseHudOverlay key={item.id} item={item} />;
          case "qa_quiz":
            return <QaQuizOverlay key={item.id} item={item} />;
          default:
            return null;
        }
      })}
    </AbsoluteFill>
  );
};
