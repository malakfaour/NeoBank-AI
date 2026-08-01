"use client";

import { ShieldCheck } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { usePreferences } from "@/components/providers/AppPreferences";

interface AdminPageHeaderProps {
  eyebrow?: string;
  title: string;
  description: string;
}

function initials(name?: string | null) {
  if (!name) return "NE";
  return name.split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

export default function AdminPageHeader({
  eyebrow = "Neo operations",
  title,
  description,
}: AdminPageHeaderProps) {
  const user = useAuthStore((state) => state.user);
  const { locale } = usePreferences();
  const role = user?.role === "admin"
    ? locale === "ar" ? "مدير النظام" : "Administrator"
    : locale === "ar" ? "مسؤول امتثال" : "Compliance";

  return (
    <header className="admin-page-hero">
      <div className="admin-page-hero__copy">
        <span className="admin-page-hero__eyebrow"><ShieldCheck size={15} />{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="admin-staff-card">
        <span className="admin-staff-card__avatar">{initials(user?.full_name)}</span>
        <span className="admin-staff-card__identity">
          <strong>{user?.full_name ?? (locale === "ar" ? "فريق نيو" : "Neo staff")}</strong>
          <small>{role}</small>
        </span>
        <i aria-label="Online" />
      </div>
    </header>
  );
}
