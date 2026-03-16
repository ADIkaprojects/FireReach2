/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx}',
    './hooks/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-inter)', 'Inter', 'sans-serif'],
        mono: ['var(--font-mono)', 'JetBrains Mono', 'monospace'],
      },
      colors: {
        'bg-primary': '#0F172A',
        'bg-card': '#1E293B',
        accent: '#F97316',
        success: '#22C55E',
        error: '#EF4444',
        warning: '#EAB308',
        'text-primary': '#F8FAFC',
        'text-secondary': '#94A3B8',
        border: '#334155',
      },
    },
  },
  plugins: [],
};
