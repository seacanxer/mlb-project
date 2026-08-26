/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          50: '#f0f4ff',
          100: '#dbe4ff',
          500: '#1e3a5f',
          700: '#162d4a',
          800: '#0f2033',
          900: '#0a1628',
          950: '#060d1a',
        },
        brand: {
          blue: '#2563eb',
          amber: '#d97706',
          red: '#dc2626',
          green: '#16a34a',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
};
