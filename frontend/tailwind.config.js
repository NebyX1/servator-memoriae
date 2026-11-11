/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        pergamino: {
          50: '#FAF7F0',
          100: '#F4EEE1',
          200: '#E9DEC7',
          300: '#D9C9A6',
        },
        tinta: {
          DEFAULT: '#23201A',
          suave: '#4A4438',
          clara: '#7A7264',
        },
        bosque: {
          50: '#EEF4EE',
          100: '#D9E7D9',
          600: '#1E4D2B',
          700: '#163B21',
          800: '#102B18',
        },
        sello: '#8C2F1B',
        dorado: '#B98A2F',
      },
      fontFamily: {
        serif: ['Georgia', '"Times New Roman"', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [require('daisyui')],
  daisyui: {
    themes: [
      {
        memoria: {
          primary: '#1E4D2B',
          'primary-content': '#FAF7F0',
          secondary: '#B98A2F',
          'secondary-content': '#23201A',
          accent: '#8C2F1B',
          'accent-content': '#FAF7F0',
          neutral: '#23201A',
          'neutral-content': '#FAF7F0',
          'base-100': '#FAF7F0',
          'base-200': '#F4EEE1',
          'base-300': '#E9DEC7',
          'base-content': '#23201A',
          info: '#3B6EA5',
          success: '#1E4D2B',
          warning: '#B98A2F',
          error: '#8C2F1B',
        },
      },
    ],
  },
};
