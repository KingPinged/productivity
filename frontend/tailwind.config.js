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
        cream: '#EEECE8',
        surface: '#F0EDE8',
        sand: '#E5E2DC',
        primary: '#1A1714',
        secondary: '#4A4540',
        muted: '#8A847D',
        border: '#D5D0CA',
        accent: '#5B5DF0',
        'accent-hover': '#4845DB',
        'accent-light': '#E8E8FD',
        study: '#7577E8',
        meeting: '#2EBF8B',
        rest: '#E5A820',
        personal: '#E066A0',
        urgent: '#DC3B3B',
        success: '#1FAD52',
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
