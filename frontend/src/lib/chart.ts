// Recharts takes colours as strings, not Tailwind classes, so the palette from
// tailwind.config.js is mirrored here. Change one, change the other.

export const palette = {
  paper: "#F2EDE3",
  paperRaised: "#FBF8F1",
  paperSunk: "#EAE3D5",
  ink: "#16130F",
  inkSoft: "#4A4238",
  inkFaint: "#8B8171",
  rule: "#DDD5C6",
  ruleStrong: "#C7BCA6",
  oxblood: "#7A2E2E",
  olive: "#5A6337",
  ochre: "#A87C2A",
};

export const axisTick = { fill: palette.inkFaint, fontSize: 12 };

export const tooltipStyle = {
  background: palette.paperRaised,
  border: `1px solid ${palette.rule}`,
  borderRadius: 3,
  fontSize: 13,
  color: palette.ink,
};
