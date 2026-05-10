import { defineConfig } from 'vite';

export default defineConfig({
  root: 'Kente Salon',
  server: { open: false },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
  },
});
