import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, "../specimpact/webui/static/dist"),
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(__dirname, "src/main.tsx"),
      output: {
        entryFileNames: "app.js",
        chunkFileNames: "chunks/[name]-[hash].js",
        manualChunks: {
          react: ["react", "react-dom"],
          graph: ["cytoscape"],
          icons: ["lucide-react"],
        },
        assetFileNames: (assetInfo) =>
          assetInfo.name?.endsWith(".css") ? "app.css" : "assets/[name]-[hash][extname]",
      },
    },
  },
});
