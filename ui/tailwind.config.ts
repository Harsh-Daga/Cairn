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
        anthracite: "#090B10",
        slate: "#0F1219",
        shale: "#151923",
        granite: "#1C2230",
        "quartz-vein": "#2A3242",
        bone: "#F7F8FA",
        cinder: "#98A2B3",
        ash: "#596273",
        copper: "#8B7CFF",
        "copper-dim": "#5B4FC7",
        patina: "#4DE2C5",
        malachite: "#7BE495",
        ochre: "#F2C94C",
        cinnabar: "#FF6B7A",
        lapis: "#60A5FA",
      },
      boxShadow: {
        stone: "0 2px 8px rgba(0,0,0,0.35)",
      },
    },
  },
  plugins: [],
};
