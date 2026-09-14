"use client";

import { HeroSection } from "@/features/home/components/HeroSection";
import { StepsSection } from "@/features/home/components/StepsSection";
import { FeaturesSection } from "@/features/home/components/FeaturesSection";
import { TrustSection } from "@/features/home/components/TrustSection";
import { CtaSection } from "@/features/home/components/CtaSection";

export default function HomePage() {
  return (
    <div className="min-h-full anim-rise">
      <HeroSection />
      <StepsSection />
      <FeaturesSection />
      <TrustSection />
      <CtaSection />
    </div>
  );
}
