/**
 * @file diagramTheme.ts
 * @description The mermaid configuration the app renders diagrams with: theme
 * choice plus the palette that maps mermaid's theme variables onto RealMock's
 * design tokens, for both the light and the dark palette. Pure data so the
 * render pipeline and the component stay free of colour knowledge.
 *
 * Constraints:
 * - This module must not import mermaid or touch the DOM; it only describes
 *   the configuration. Applying it belongs to diagramRender.ts.
 */

/**
 * The interface font stack, mirrored from tailwind.config.js. mermaid writes
 * this into the diagram's own stylesheet, so CJK node labels render in the app
 * face instead of the theme's Latin-only fallback.
 */
export const DIAGRAM_FONT_FAMILY =
  'var(--font-dm-sans), system-ui, -apple-system, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif';

/** Light palette, from the :root tokens in globals.css. */
const LIGHT_THEME_VARIABLES = {
  fontFamily: DIAGRAM_FONT_FAMILY,
  background: "#ffffff",
  primaryColor: "#e8f0fe",
  primaryTextColor: "#003e8f",
  primaryBorderColor: "#4285f4",
  lineColor: "#5f6368",
  secondaryColor: "#f9f9fa",
  tertiaryColor: "#ffffff",
  textColor: "#0e1115",
  mainBkg: "#e8f0fe",
  nodeBorder: "#4285f4",
  clusterBkg: "#f9f9fa",
  clusterBorder: "#d2d6dc",
  // Without this mermaid paints a solid grey plate behind every edge label.
  edgeLabelBackground: "#ffffff",
  noteBkgColor: "#fef7e0",
  noteBorderColor: "#fbbc05",
  noteTextColor: "#b06000",
  actorBkg: "#e8f0fe",
  actorBorder: "#4285f4",
  actorTextColor: "#003e8f",
  signalColor: "#333942",
  signalTextColor: "#0e1115",
  labelBoxBkgColor: "#e8f0fe",
} as const;

/** Dark palette, from the .dark tokens in globals.css. */
const DARK_THEME_VARIABLES = {
  fontFamily: DIAGRAM_FONT_FAMILY,
  background: "#1d1d1c",
  primaryColor: "#1c2b3a",
  primaryTextColor: "#a8c7fa",
  primaryBorderColor: "#4285f4",
  lineColor: "#949494",
  secondaryColor: "#252525",
  tertiaryColor: "#161616",
  textColor: "#eff1f4",
  mainBkg: "#1c2b3a",
  nodeBorder: "#4285f4",
  clusterBkg: "#252525",
  clusterBorder: "#404040",
  edgeLabelBackground: "#1d1d1c",
  noteBkgColor: "#383024",
  noteBorderColor: "#f2c94c",
  noteTextColor: "#f2c94c",
  actorBkg: "#1c2b3a",
  actorBorder: "#4285f4",
  actorTextColor: "#a8c7fa",
  signalColor: "#c5c7cd",
  signalTextColor: "#eff1f4",
  labelBoxBkgColor: "#1c2b3a",
} as const;

export interface DiagramThemeConfig {
  theme: "default" | "dark";
  fontFamily: string;
  htmlLabels: boolean;
  themeVariables: Record<string, string>;
}

/**
 * Build the mermaid config for one palette.
 *
 * `htmlLabels: false` is a correctness requirement, not a style choice: mermaid
 * renders node and edge labels as HTML inside <foreignObject>, and the
 * XSS filter in diagramSvg.ts strips every foreignObject. With HTML labels on,
 * every label disappears and only bare shapes remain. Plain SVG <text> keeps
 * the filter intact as pure defence in depth.
 */
export function buildDiagramTheme(dark: boolean): DiagramThemeConfig {
  return {
    theme: dark ? "dark" : "default",
    fontFamily: DIAGRAM_FONT_FAMILY,
    htmlLabels: false,
    themeVariables: { ...(dark ? DARK_THEME_VARIABLES : LIGHT_THEME_VARIABLES) },
  };
}
