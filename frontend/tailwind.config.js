/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    borderRadius: {
      none:    '0px',
      sm:      '2px',
      DEFAULT: '2px',
      md:      '2px',
      lg:      '2px',
      xl:      '2px',
      '2xl':   '2px',
      full:    '9999px',
    },
    extend: {
      colors: {
        bg: {
          base:    '#000000',
          surface: '#090909',
          raised:  '#0e0e0e',
          border:  '#1c1c1c',
          hover:   '#242424',
        },
        text: {
          primary:   '#ffffff',
          secondary: '#a0a0a0',
          muted:     '#505050',
        },
        orange: {
          300: '#fdba74',
          400: '#fb923c',
          500: '#f97316',
          600: '#ea580c',
        },
        emerald: { 400: '#34d399', 500: '#10b981' },
        red:     { 400: '#f87171', 500: '#ef4444' },
        amber:   { 400: '#fbbf24' },
        violet:  { 400: '#a78bfa', 500: '#8b5cf6' },
        cyan:    { 400: '#22d3ee' },
      },
      fontFamily: {
        display: ['Outfit', 'sans-serif'],
        sans:    ['"JetBrains Mono"', 'monospace'],
        mono:    ['"JetBrains Mono"', 'monospace'],
      },
      boxShadow: {
        'orange-glow': '0 0 40px -8px rgba(249,115,22,0.3)',
        'orange-sm':   '0 0 16px -4px rgba(249,115,22,0.25)',
      },
      animation: {
        'blink':       'blink 1s step-end infinite',
        'fade-in':     'fadeIn 0.2s ease-out',
        'slide-down':  'slideDown 0.4s cubic-bezier(0.16,1,0.3,1)',
        'pulse-slow':  'pulse 3s cubic-bezier(0.4,0,0.6,1) infinite',
        'ticker':      'ticker 40s linear infinite',
      },
      keyframes: {
        blink:     { '0%,100%': { opacity: '1' }, '50%': { opacity: '0' } },
        fadeIn:    { from: { opacity: '0' }, to: { opacity: '1' } },
        slideDown: { from: { opacity: '0', transform: 'translateY(-12px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        ticker:    { from: { transform: 'translateX(0)' }, to: { transform: 'translateX(-50%)' } },
      },
    },
  },
  plugins: [],
}
