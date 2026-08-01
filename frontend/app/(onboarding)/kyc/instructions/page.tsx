"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, FileBadge, LockKeyhole, ScanFace, Wifi } from "lucide-react";
import { usePreferences } from "@/components/providers/AppPreferences";
import PreferenceControls from "@/components/ui/PreferenceControls";

const requirements = [
  { key: "id", icon: FileBadge },
  { key: "light", icon: ScanFace },
  { key: "internet", icon: Wifi },
];

export default function KycInstructionsPage() {
  const router = useRouter();
  const { t } = usePreferences();

  return (
    <main className="kyc-intro-page">
      <header className="kyc-intro-header">
        <Image src="/logo.svg" alt="NeoBank Lebanon" width={112} height={44} />
        <PreferenceControls compact />
      </header>
      <section className="kyc-intro-shell">
        <div className="kyc-intro-copy">
          <p className="eyebrow"><span />{t("kyc.eyebrow")}</p>
          <h1>{t("kyc.title")}</h1>
          <p className="kyc-intro-lede">{t("kyc.body")}</p>
          <div className="kyc-requirements">
            {requirements.map(({ key, icon: Icon }) => (
              <article key={key}><span><Icon size={22} /></span><div><h2>{t(`kyc.${key}`)}</h2><p>{t(`kyc.${key}.body`)}</p></div><Check size={18} /></article>
            ))}
          </div>
        </div>
        <aside className="kyc-steps-card">
          <div className="kyc-steps-icon"><LockKeyhole size={25} /></div>
          <h2>{t("kyc.steps")}</h2>
          <ol>
            {[1, 2, 3, 4].map((number) => <li key={number}><span>{number}</span><p>{t(`kyc.step${number}`)}</p></li>)}
          </ol>
          <button type="button" onClick={() => router.push("/kyc")} className="kyc-start-button">{t("kyc.start")} <ArrowRight size={18} /></button>
          <p className="kyc-private"><LockKeyhole size={13} />{t("kyc.private")}</p>
        </aside>
      </section>
    </main>
  );
}
