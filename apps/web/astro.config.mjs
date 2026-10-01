import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import sitemap from '@astrojs/sitemap';
import robotsTxt from '@astrojs/robots-txt';

export default defineConfig({
  site: 'https://hercule.ai',
  integrations: [
    tailwind(),
    sitemap(),
    robotsTxt(),
  ],
  output: 'static',
  compressHTML: true,
  build: {
    inlineStylesheets: 'auto',
  },
  prefetch: true,
});