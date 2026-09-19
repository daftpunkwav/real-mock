/**
 * Morse bit stream played by the hopping hero title glyphs: encodes the word
 * into a looping dot/dash sequence (dot = low hop, dash = high hop, one low
 * hop inserted between letters).
 */

const MORSE: Record<string, string> = {
  a: '.-',
  b: '-...',
  c: '-.-.',
  d: '-..',
  e: '.',
  f: '..-.',
  g: '--.',
  h: '....',
  i: '..',
  j: '.---',
  k: '-.-',
  l: '.-..',
  m: '--',
  n: '-.',
  o: '---',
  p: '.--.',
  q: '--.-',
  r: '.-.',
  s: '...',
  t: '-',
  u: '..-',
  v: '...-',
  w: '.--',
  x: '-..-',
  y: '-.--',
  z: '--..',
};

/** Dot = 0 (low hop), dash = 1 (high hop); one low hop separates letters. */
function encodeWord(word: string): (0 | 1)[] {
  const bits: (0 | 1)[] = [];
  for (const ch of word) {
    const pattern = MORSE[ch];
    if (!pattern) continue;
    if (bits.length > 0) bits.push(0);
    for (const symbol of pattern) {
      bits.push(symbol === '-' ? 1 : 0);
    }
  }
  return bits;
}

/** The word spelled out by the hopping title, one bit per hop. */
export const HERO_MORSE_WORD = 'daftpunkwav';

export const HERO_MORSE_BITS = encodeWord(HERO_MORSE_WORD);

/** Low/high hop amplitudes (px) per glyph position, for visual variety. */
const LOW_HOP_BY_GLYPH = [6, 8, 5, 7, 6, 9, 5, 7, 6];
const HIGH_HOP_BY_GLYPH = [17, 20, 15, 22, 18, 21, 16, 23, 19];

/** invert flips high/low on alternate cycles so repeats look different. */
export function getMorseHopPx(glyphIndex: number, bit: 0 | 1, invert: boolean): number {
  const isHigh = invert ? bit === 0 : bit === 1;
  const table = isHigh ? HIGH_HOP_BY_GLYPH : LOW_HOP_BY_GLYPH;
  return table[glyphIndex % table.length] ?? (isHigh ? 18 : 7);
}

export const HERO_MORSE_INTERVAL_MS = 1000;
