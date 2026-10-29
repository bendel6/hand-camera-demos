// Single-file build for hosting as a claude.ai artifact preview: JS/CSS/fonts inlined into one HTML page;
// models, textures and data stay as sibling files fetched with relative URLs.
import { defineConfig } from 'vite';
import { viteSingleFile } from 'vite-plugin-singlefile';

export default defineConfig({
  base: './',
  plugins: [viteSingleFile()],
  publicDir: false,
  build: { outDir: 'dist-artifact', target: 'es2022', assetsInlineLimit: 100_000_000, chunkSizeWarningLimit: 100000 },
});
