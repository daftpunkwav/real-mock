// Tailwind 4 moved its PostCSS plugin out of the tailwindcss package into
// @tailwindcss/postcss. autoprefixer is gone: the Tailwind 4 engine already
// prefixes for the browsers it targets.
// Must stay CommonJS - next's PostCSS loader only reads `module.exports`.
module.exports = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
