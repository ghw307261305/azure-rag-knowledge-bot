import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts"
  },
  server: {
    // バックエンドのローカル既定 URL と合わせ、開発時の接続先を予測しやすくする。
    port: 5173
  }
});
