import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'url';
import { defineConfig } from 'vite';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Deterministic UI fingerprint; no environment secrets, credentials or timestamps.
const hash = createHash('sha256');
function fingerprint(relative) {
  const absolute = path.join(__dirname, relative);
  if (fs.statSync(absolute).isDirectory()) {
    for (const name of fs.readdirSync(absolute).sort()) fingerprint(`${relative}/${name}`);
  } else {
    hash.update(relative).update('\0').update(fs.readFileSync(absolute));
  }
}
for (const file of ['src', 'public', 'index.html', 'package.json', 'bun.lock', 'vite.config.js']) fingerprint(file);
const uiVersion = hash.digest('hex').slice(0, 16);

// https://vite.dev/config/
export default defineConfig({
  define: { __SOURCE_UI_VERSION__: JSON.stringify(uiVersion) },
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'native-webapp-routes',
      generateBundle() {
        this.emitFile({ type: 'asset', fileName: 'ui-version.json',
          source: JSON.stringify({ version: uiVersion, entrypoint: '/menu' }) });
        this.emitFile({
          type: 'asset',
          fileName: 'native-routes.json',
          source: fs.readFileSync(path.join(__dirname, 'src/native/routes.json'), 'utf8'),
        });
      },
    },
  ],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            // Order matters: check specific packages before the generic
            // 'react' substring match (e.g. @tanstack/react-query contains
            // 'react' in its path).
            if (id.includes('framer-motion')) return 'motion-vendor';
            if (id.includes('@tanstack/react-query')) return 'query-vendor';
            if (id.includes('lucide-react')) return 'icons-vendor';
            if (id.includes('react')) return 'react-vendor';
          }
        },
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
