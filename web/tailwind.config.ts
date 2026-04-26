import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        tg: {
          primary: "#0088cc",
          incoming: "#ffffff",
          outgoing: "#dcf8c6",
          unknown: "#fff8e1",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
