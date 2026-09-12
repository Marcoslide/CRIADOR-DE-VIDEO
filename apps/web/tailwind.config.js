/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: {
          950: "#0a0b0f",
          900: "#111318",
          850: "#161922",
          800: "#1b1f2a",
          700: "#262b38",
          600: "#3a4157",
        },
      },
    },
  },
  plugins: [],
};
