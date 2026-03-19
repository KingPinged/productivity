/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        body: ['"DM Sans"', 'system-ui', 'sans-serif'],
      },
      colors: {
        cream: '#FAF9F6',
        sand: '#F5F3EF',
        primary: '#1C1917',
        secondary: '#78716C',
        muted: '#A8A29E',
        border: '#E7E5E4',
        accent: '#6366F1',
        'accent-hover': '#4F46E5',
        'accent-light': '#EEF2FF',
        study: '#818CF8',
        meeting: '#34D399',
        rest: '#FBBF24',
        personal: '#F472B6',
        urgent: '#EF4444',
        success: '#22C55E',
      },
      boxShadow: {
        'soft': '0 1px 3px rgba(28,25,23,0.06)',
        'card': '0 2px 8px rgba(28,25,23,0.08)',
        'elevated': '0 4px 16px rgba(28,25,23,0.1)',
      },
      borderRadius: {
        'xl': '12px',
        '2xl': '16px',
      },
    },
  },
  plugins: [],
}
