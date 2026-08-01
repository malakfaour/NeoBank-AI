"use client";

import Image from "next/image";
import Link from "next/link";
import PreferenceControls from "@/components/ui/PreferenceControls";
import { usePreferences } from "@/components/providers/AppPreferences";

export default function WelcomePage() {
  const { locale } = usePreferences();

  return (
    <main className="welcome-screen">
      <section className="welcome-panel">
        <div className="welcome-arc" aria-hidden="true" />
        <header className="welcome-controls">
          <PreferenceControls compact />
        </header>

        <div className="welcome-brand">
          <p>{locale === "ar" ? "أهلاً بك في" : "Welcome to"}</p>
          <Image src="/logo.svg" alt="NeoBank Lebanon" width={190} height={76} priority />
        </div>

        <div className="welcome-actions">
          <p>{locale === "ar" ? "هل لديك حساب في نيو؟" : "Already a Neo user?"}</p>
          <Link href="/login" className="welcome-login">
            {locale === "ar" ? "تسجيل الدخول" : "Login"}
          </Link>

          <div className="welcome-divider">
            <span />
            <p>{locale === "ar" ? "هل أنت عميل جديد؟" : "Are you a new customer?"}</p>
            <span />
          </div>

          <Link href="/register" className="welcome-register">
            {locale === "ar" ? "إنشاء حساب" : "Sign up"}
          </Link>
        </div>
      </section>
    </main>
  );
}
