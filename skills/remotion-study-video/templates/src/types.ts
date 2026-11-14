export type TransitionKind = "fade" | "slide" | "wipe" | "none";

export type SceneVfxConfig =
  | { kind: "none" }
  | { kind: "motes"; count?: number; opacity?: number }
  | {
      kind: "screen_video";
      videoFile: string;
      opacity?: number;
      region?: { x: number; y: number; w: number; h: number };
    };

export interface SceneItem {
  id: string;
  title: string;
  imageFile: string;
  start: number;
  end: number;
  transition?: TransitionKind;
  transitionDurationFrames?: number;
  /** Optional photo dimness (0..0.85) so vector overlays pop cleanly over photography */
  backdropDim?: number;
  vfx?: SceneVfxConfig;
}

export interface RichTextSegment {
  text: string;
  highlight?: boolean;
}

export interface CueItem {
  index: number;
  en: string;
  zh: string;
  start: number;
  speechEnd: number;
  end: number;
  chapter?: string;
  notes?: string[];
  highlightEn?: string[];
  highlightZh?: string[];
  richEn?: RichTextSegment[];
  richZh?: RichTextSegment[];
  richNotes?: RichTextSegment[][];
  reviewTopic?: string | null;
}

export interface SpotlightItem {
  id: string;
  start: number;
  end: number;
  x: number;
  y: number;
  radiusX: number;
  radiusY: number;
  dimOpacity?: number;
  label?: string;
}

export type HudPosition = "top-right" | "top-left" | "bottom-right";

export type HudItem =
  | {
      id: string;
      kind: "metric_climb";
      start: number;
      end: number;
      position?: HudPosition;
      eyebrow?: string;
      title: string;
      fromValue: number;
      toValue: number;
      unit?: string;
      badge?: string;
    }
  | {
      id: string;
      kind: "comparison_bars";
      start: number;
      end: number;
      position?: HudPosition;
      title: string;
      items: Array<{ label: string; value: number; accent?: boolean }>;
    }
  | {
      id: string;
      kind: "route_flow";
      start: number;
      end: number;
      position?: HudPosition;
      title: string;
      steps: string[];
    }
  | {
      id: string;
      kind: "flag_badge";
      start: number;
      end: number;
      imageFile: string;
    };

export type GraphicOverlayItem =
  | {
      id: string;
      kind: "cover_hero";
      start: number;
      end: number;
      eyebrow?: string;
      title: string;
      subtitleEn: string;
      subtitleZh?: string;
      sealText?: string;
      svgPreset?: "great_wall" | "none";
    }
  | {
      id: string;
      kind: "globe_fact_card";
      start: number;
      end: number;
      cardStart?: number;
      cardEnd?: number;
      badge?: string;
      cardTitleEn: string;
      cardTitleZh?: string;
      rows: Array<{ label: string; value: string; zh?: string }>;
      globeBadgeStart?: number;
      globeLabel1?: string;
      globeLabel2?: string;
      globeSwitchTime?: number;
      showGlobe?: boolean;
    }
  | {
      id: string;
      kind: "area_infographic";
      start: number;
      end: number;
      statTag: string;
      statValue: string;
      statNumTarget?: number;
      statDescEn: string;
      statDescZh?: string;
      chartTitle: string;
      items: Array<{ label: string; value: number; max: number; unit?: string; accent?: boolean }>;
    }
  | {
      id: string;
      kind: "blueprint_callout";
      start: number;
      end: number;
      tag: string;
      title: string;
      descEn: string;
      descZh?: string;
      svgPreset?: "temple_of_heaven" | "none";
    }
  | {
      id: string;
      kind: "calligraphy_bubbles";
      start: number;
      end: number;
      tag: string;
      title: string;
      descEn: string;
      descZh?: string;
      centerText: string;
      bubbles: Array<{ text: string; color: string; x: number; y: number; delay: number }>;
    }
  | {
      id: string;
      kind: "waving_flag_showcase";
      start: number;
      end: number;
      tag: string;
      title: string;
      descEn: string;
      descZh?: string;
      showFlagGraphic?: boolean;
    }
  | {
      id: string;
      kind: "terrain_profile";
      start: number;
      end: number;
      header: string;
      steps: Array<{ x: number; y: number; tag: string; sub: string; color: string; delay: number }>;
    }
  | {
      id: string;
      kind: "elevation_ruler";
      start: number;
      end: number;
      eyebrow: string;
      title: string;
      subtitle?: string;
      fromValue: number;
      toValue: number;
      unit?: string;
      badge?: string;
      beaconX?: number;
      beaconY?: number;
      ticks?: Array<{ label: string; ratio: number }>;
    }
  | {
      id: string;
      kind: "river_course_hud";
      start: number;
      end: number;
      tag: string;
      metricTarget: number;
      metricSuffix?: string;
      title: string;
      subtitle?: string;
      courseTitle: string;
      stops: Array<{ frac: number; label: string }>;
    }
  | {
      id: string;
      kind: "qa_quiz";
      start: number;
      end: number;
      x?: number;
      y?: number;
      w?: number;
      tag?: string;
      thinkingText?: string;
      items: Array<{
        qStart: number;
        aStart: number;
        end: number;
        qEn: string;
        qZh: string;
        aEn: string;
        aZh: string;
      }>;
    };

export interface StudyProjectData {
  meta: {
    title: string;
    subtitle?: string;
    fps: number;
    width: number;
    height: number;
    durationInSeconds: number;
    durationInFrames: number;
    audioFile: string;
  };
  scenes: SceneItem[];
  cues: CueItem[];
  spotlights?: SpotlightItem[];
  hud?: HudItem[];
  overlays?: GraphicOverlayItem[];
}
