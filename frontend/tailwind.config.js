/** Botanical Field Journal tokens (supplied Stitch spec).
 * Single source alongside index.css :root. No hex values elsewhere. */
 /** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#FAF7EF',
        parchment: '#F4EFE2',
        card: '#FFFFFF',
        ink: '#202722',
        muted: '#5B665E',
        moss: '#1F5B46',
        'moss-dark': '#164635',
        fern: '#E3EDE5',
        clay: '#F3E8D3',
        amber: '#B87A28',
        ochre: '#D5A34B',
        danger: '#B3261E',
        line: '#DED8C9',
        divider: '#ECE7DA',
        stub: '#D5A34B',
      },
      borderRadius: {
        card: '8px',
        field: '6px',
      },
      fontFamily: {
        // Preferred faces first; no webfont downloads (DESIGN no-fetch + offline-safe).
        display: ['Newsreader', 'Georgia', "'Times New Roman'", 'serif'],
        sans: ['Inter', 'system-ui', '-apple-system', "'Segoe UI'", 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
