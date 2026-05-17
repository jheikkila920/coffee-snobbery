// Tailwind v4 standalone CLI configuration — Phase 0 (Plan 00-04).
//
// Compiled into the image at Dockerfile stage 1 (tailwind-builder); the
// resulting content-hashed CSS is COPYed into the runtime image. The runtime
// image carries zero Tailwind tooling (CONTEXT D-04 / D-15).
//
// Palette values are defensible baselines, not the final hex tuning:
// - cream-50 = #FAF7F2 is the dual `theme-color` light value (PITFALL PWA-5).
// - espresso-950 = #1A1110 is the dual `theme-color` dark value (PITFALL PWA-5).
// Both ramps are monotonic warm tones; the first `/gsd-ui-phase` pass refines
// the intermediate shades (CONTEXT D-14).
//
// `darkMode: 'media'` follows the system preference — no manual toggle in v1
// (PROJECT.md row 6, CONTEXT D-14).
//
// Content scan paths intentionally include `app/static/js/**/*.js` even though
// Phase 0 ships no JS there yet; this saves a config edit when Phase 1 adds
// HTMX + Alpine inline directives in templates and any vanilla JS modules
// (RESEARCH Open Question #6).

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  darkMode: 'media',
  theme: {
    extend: {
      colors: {
        cream: {
          50: '#FAF7F2',
          100: '#F4EFE6',
          200: '#E8DFCE',
          300: '#DACBAE',
          400: '#C8B68C',
          500: '#B6A06E',
          600: '#9A8455',
          700: '#7A6843',
          800: '#5C4E33',
          900: '#3E3522',
          950: '#241E13',
        },
        espresso: {
          50: '#F2EBE6',
          100: '#E3D5C9',
          200: '#C6AB94',
          300: '#A98260',
          400: '#7E5C40',
          500: '#5E422C',
          600: '#4B3422',
          700: '#3D2817',
          800: '#2B1B10',
          900: '#21150C',
          950: '#1A1110',
        },
      },
    },
  },
  plugins: [],
};
