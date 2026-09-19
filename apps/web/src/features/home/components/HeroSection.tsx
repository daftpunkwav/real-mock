"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useT } from "@/i18n";
import { getMorseHopPx, HERO_MORSE_BITS, HERO_MORSE_INTERVAL_MS } from "../morse";
import { CardStrip } from "./CardStrip";
import { StageButton } from "./StageButton";

/** Choreography easing — leads the eye hard, then settles. */
const introEase = [0.16, 1, 0.3, 1] as const;

function intro(delay: number, y = 10) {
  return {
    initial: { opacity: 0, y },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.7, delay, ease: introEase },
  };
}

/** Light ramp for the second line: steps the primary → sky pair per glyph. */
function glyphColor(colorIndex: number, colorCount: number): string {
  const t = colorCount > 1 ? colorIndex / (colorCount - 1) : 0;
  return `color-mix(in srgb, var(--primary) ${Math.round((1 - t) * 100)}%, #7aabff)`;
}

interface TitleGlyph {
  char: string;
  space: boolean;
  charIndex: number;
  morseIndex: number;
  colorIndex: number;
}

export function HeroSection() {
  const reduce = useReducedMotion();
  const t = useT("home");
  const [morseTick, setMorseTick] = useState(0);

  // The title spells its word in Morse, one glyph hop per tick; alternate
  // cycles invert high/low so repeats read differently.
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mq.matches) return;
    const id = window.setInterval(() => {
      setMorseTick((tick) => tick + 1);
    }, HERO_MORSE_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, []);

  // Split both title lines into glyphs; spaces pass through without hopping.
  let morseCursor = 0;
  let colorCursor = 0;
  const buildLine = (text: string, colored: boolean): TitleGlyph[] =>
    Array.from(text).map((char, charIndex) => {
      if (char === " ")
        return { char, space: true, charIndex, morseIndex: -1, colorIndex: -1 };
      return {
        char,
        space: false,
        charIndex,
        morseIndex: morseCursor++,
        colorIndex: colored ? colorCursor++ : -1,
      };
    });
  const line1 = buildLine(t("hero.title.line1"), false);
  const line2 = buildLine(t("hero.title.line2"), true);
  const glyphCount = morseCursor;
  const colorCount = colorCursor;

  const activeIndex = morseTick % glyphCount;
  const bit = (HERO_MORSE_BITS[morseTick % HERO_MORSE_BITS.length] ?? 0) as 0 | 1;
  const invert = Math.floor(morseTick / HERO_MORSE_BITS.length) % 2 === 1;

  const renderGlyph = (glyph: TitleGlyph, colored: boolean) => {
    if (glyph.space) return <span key={`s-${glyph.charIndex}`}>{glyph.char}</span>;
    const isActive = glyph.morseIndex === activeIndex;
    const style: React.CSSProperties & Record<string, string | number> = {};
    if (colored) style.color = glyphColor(glyph.colorIndex, colorCount);
    if (isActive) style["--hero-hop"] = `${getMorseHopPx(glyph.morseIndex, bit, invert)}px`;
    return (
      <span
        key={isActive ? `hop-${morseTick}` : `rest-${glyph.morseIndex}`}
        className={`hero-title-glyph${isActive ? " morse-hopping" : ""}`}
        style={style}
      >
        {glyph.char}
      </span>
    );
  };

  return (
    // The hero owns the whole first screen at any zoom level: min-h-svh tracks
    // the visual viewport, so the next section never peeks in from the bottom.
    <section className="relative flex min-h-svh flex-col overflow-hidden">
      {/* Faint bank of light along the foot that dissolves back to transparent
          before the section edge — a hard stop here reads as a divider line. */}
      <div
        className="pointer-events-none absolute inset-0"
        aria-hidden
        style={{
          background:
            "linear-gradient(180deg, transparent 55%, color-mix(in srgb, var(--primary) 5%, transparent) 80%, transparent 100%)",
        }}
      />

      {/* Copy block — centred like a marquee, context first then message. It
          stretches to absorb the space a tall viewport offers, so the wheel
          keeps its grounded height instead of floating. */}
      <div className="relative mx-auto flex w-full max-w-[1200px] flex-1 flex-col items-center justify-center px-5 pb-8 pt-14 text-center sm:px-6 sm:pt-20 lg:px-8">
        <motion.h1
          {...(reduce ? {} : intro(0.14, 14))}
          className="text-[clamp(2.5rem,6vw,4.25rem)] font-bold leading-[1.06] tracking-[0.01em] text-ink"
        >
          {line1.map((glyph) => renderGlyph(glyph, false))}{" "}
          <span className="whitespace-nowrap">{line2.map((glyph) => renderGlyph(glyph, true))}</span>
        </motion.h1>

        <motion.p
          {...(reduce ? {} : intro(0.24, 9))}
          className="mt-5 whitespace-nowrap text-[14px] leading-[1.7] text-ink-muted sm:text-[15px]"
        >
          {t("hero.sub1")}
        </motion.p>

        <motion.div
          {...(reduce ? {} : intro(0.32, 8))}
          className="mt-8 flex flex-wrap items-center justify-center gap-2.5"
        >
          <StageButton href="/interview">{t("hero.cta.interview")}</StageButton>
          <Link
            href="/resume"
            className="btn-secondary !h-[52px] !px-7 !text-[16px]"
          >
            {t("hero.cta.resume")}
          </Link>
        </motion.div>
      </div>

      {/* Scene zone: full main-column width (not the text container), so the
          wheel spans edge to edge instead of floating in dead margins.
          overflow-x clips the band when the scale floor makes it wider than a
          narrow container (vertical stays visible so the rim-card arch is not
          sliced, and no horizontal scrollbar appears). */}
      <div className="relative h-[360px] w-full shrink-0 overflow-x-clip sm:h-[420px]">
        <motion.div
          {...(reduce ? {} : intro(0.4, 16))}
          className="absolute inset-0"
        >
          <CardStrip />
        </motion.div>
        {/* Pool of light under the wheel. Its centre sits INSIDE the box so
            the falloff reaches zero before every edge — a gradient clipped
            by the box edge reads as a divider line. */}
        <div
          className="pointer-events-none absolute inset-x-0 bottom-0 h-40"
          aria-hidden
          style={{
            background:
              "radial-gradient(46% 62% at 50% 42%, color-mix(in srgb, var(--primary) 11%, transparent), transparent 68%)",
          }}
        />
      </div>
    </section>
  );
}
