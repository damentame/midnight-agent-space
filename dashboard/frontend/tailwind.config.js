/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        accent: {
          DEFAULT: "#ea580c",
          bright: "#f97316",
          muted: "#c2410c",
        },
        /** Warm canvas — never pure #fff */
        paper: {
          DEFAULT: "#e8e3d8",
          bright: "#ebe7df",
          lift: "#ece9e0",
          field: "#e6e1d6",
        },
      },
      animation: {
        float: "float 5s ease-in-out infinite",
        "pulse-slow": "pulse 2.5s ease-in-out infinite",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0) translateX(0)" },
          "33%": { transform: "translateY(-10px) translateX(3px)" },
          "66%": { transform: "translateY(5px) translateX(-5px)" },
        },
      },
    },
  },
  plugins: [],
};
