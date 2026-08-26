import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        // Cifras en monoespaciada tabular: las columnas numéricas de un panel
        // científico tienen que alinearse.
        mono: ['ui-monospace', 'JetBrains Mono', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        ink: {
          950: '#0a0d12',
          900: '#0f141b',
          850: '#141b24',
          800: '#1a222d',
          700: '#243040',
          600: '#334155',
          400: '#7d8da3',
          300: '#a3b1c6',
          100: '#e6ecf5',
        },
        // Semántica de estados, alineada con el mapa _ICON del bot de Telegram
        // para que la GUI y Telegram se lean igual.
        st: {
          running: '#3b82f6',
          converged: '#22c55e',
          failed: '#ef4444',
          stopped: '#9f1239',
          stalled: '#f59e0b',
          oscillating: '#fb923c',
          pending: '#64748b',
          skipped: '#8b5cf6',
          unknown: '#475569',
        },
      },
    },
  },
  plugins: [],
} satisfies Config
