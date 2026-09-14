/** Root layout: fonts, theme/locale providers with pre-hydration scripts, and the app shell. */

import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import { DM_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/layout/AppShell";
import {
  SIDEBAR_COOKIE_KEY,
  parseSidebarState,
} from "@/components/layout/sidebarStorage";
import { Toaster } from "@/components/Toast";
import { canonicalHostInitScript } from "@/lib/canonicalHost";
import { ThemeProvider, themeInitScript } from "@/components/theme/ThemeProvider";
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  LOCALE_META,
  LocaleProvider,
  isLocaleId,
  localeInitScript,
} from "@/i18n";

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
  weight: ["400", "500"],
});

// Title is not static in metadata: LocaleProvider owns the sole <title> and updates with locale.
export const metadata: Metadata = {
  description: "Agent-based realistic mock interview system with BYOK",
  applicationName: "RealMock",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#161616" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // SSR the user's locale: the cookie mirrors the localStorage choice (kept in
  // sync by localeInitScript and setLocale), so the first paint is already right.
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get(LOCALE_STORAGE_KEY)?.value;
  const initialLocale = isLocaleId(cookieLocale) ? cookieLocale : DEFAULT_LOCALE;
  // SSR the sidebar shell the same way: cookie mirrors the client choice, so
  // the first paint already matches (no expand-then-collapse flash).
  const sidebarInitial = parseSidebarState(cookieStore.get(SIDEBAR_COOKIE_KEY)?.value);

  return (
    <html lang={LOCALE_META[initialLocale].htmlLang} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: canonicalHostInitScript }} />
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <script dangerouslySetInnerHTML={{ __html: localeInitScript }} />
      </head>
      <body
        className={`${dmSans.variable} ${jetbrains.variable} font-sans antialiased text-[var(--foreground)] bg-[var(--background)]`}
      >
        <ThemeProvider>
          <LocaleProvider initialLocale={initialLocale}>
            <AppShell sidebarInitial={sidebarInitial}>{children}</AppShell>
            <Toaster />
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
