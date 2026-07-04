/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Fraunces", "Georgia", "serif"],
        ui: ["Space Grotesk", "system-ui", "sans-serif"],
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
        anthracite: "#14161A",
        slate: "#1B1E23",
        shale: "#23272E",
        granite: "#2D323A",
        "quartz-vein": "#3A4049",
        bone: "#E8E4DC",
        cinder: "#8A8F98",
        ash: "#5B6068",
        copper: "#D08C4F",
        "copper-dim": "#8A5A30",
        patina: "#6FA8B8",
        malachite: "#7BAE6B",
        ochre: "#C98A3A",
        cinnabar: "#C75B5B",
        lapis: "#8B8FD4",
      },
      boxShadow: {
        stone: "0 2px 8px rgba(0,0,0,0.35)",
      },
    },
  },
  plugins: [],
};
