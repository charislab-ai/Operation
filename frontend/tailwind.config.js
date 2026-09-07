/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          purple: "#886AFF",
          blue: "#5771f8",
        },
      },
    },
  },
  plugins: [],
};
