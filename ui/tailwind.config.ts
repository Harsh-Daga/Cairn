const token = (name: string) => `rgb(var(--${name}-rgb) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Manrope Variable", "Manrope", "system-ui", "sans-serif"],
        ui: ["Manrope Variable", "Manrope", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        chip: "4px",
        sm: "8px",
        card: "12px",
        modal: "16px",
      },
      spacing: {
        "4.5": "18px",
      },
      colors: {
        canvas: token("surface-canvas"),
        surface: token("surface-base"),
        raised: token("surface-raised"),
        overlay: token("surface-overlay"),
        "text-primary": token("text-primary"),
        "text-muted": token("text-muted"),
        "border-default": token("border-default"),
        focus: token("focus"),
        info: token("severity-info"),
        warning: token("severity-warning"),
        high: token("severity-high"),
        critical: token("severity-critical"),
        confidence: token("confidence"),
        estimate: token("estimate"),

        /* Compatibility aliases while components migrate to semantic names. */
        anthracite: token("surface-canvas"),
        slate: token("surface-base"),
        shale: token("surface-raised"),
        granite: token("surface-hover"),
        "quartz-vein": token("border-default"),
        bone: token("text-primary"),
        cinder: token("text-muted"),
        ash: token("text-disabled"),
        copper: token("accent-primary"),
        "copper-dim": token("accent-primary-muted"),
        patina: token("chart-2"),
        malachite: token("status-success"),
        ochre: token("severity-warning"),
        cinnabar: token("severity-critical"),
        lapis: token("severity-info"),
      },
      boxShadow: {
        stone: "var(--shadow-stone)",
      },
    },
  },
  plugins: [],
};
