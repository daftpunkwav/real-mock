import { PageBackdrop } from "@/features/home/components/PageBackdrop";
import { HeroSection } from "@/features/home/components/HeroSection";
import { PainSection } from "@/features/home/components/PainSection";
import { StepsSection } from "@/features/home/components/StepsSection";
import { FeaturesSection } from "@/features/home/components/FeaturesSection";
import { TrustSection } from "@/features/home/components/TrustSection";
import { CtaSection } from "@/features/home/components/CtaSection";

export default function HomePage() {
  return (
    <div className="relative min-h-full">
      {/* One continuous stage: the starfield stays fixed while sections scroll
          over it, so the hero and everything below share the same atmosphere. */}
      <PageBackdrop />
      <div className="relative">
        <HeroSection />
        <PainSection />
        <StepsSection />
        <FeaturesSection />
        <TrustSection />
        <CtaSection />
      </div>
    </div>
  );
}
