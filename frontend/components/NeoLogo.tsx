export default function NeoLogo({ size = 48 }: { size?: number }) {
  return (
    <svg width={size * 3} height={size} viewBox="0 0 180 60" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* n */}
      <path d="M10 45V15H22L38 35V15H50V45H38L22 25V45H10Z" fill="#0A0A0A"/>
      {/* c */}
      <path d="M60 30C60 20 68 13 80 13C89 13 96 17 99 24L89 27C87 24 84 22 80 22C74 22 70 25.5 70 30C70 34.5 74 38 80 38C84 38 87 36 89 33L99 36C96 43 89 47 80 47C68 47 60 40 60 30Z" fill="#0A0A0A"/>
      {/* o — green oval */}
      <ellipse cx="140" cy="30" rx="28" ry="17" fill="#00C853"/>
      <ellipse cx="140" cy="30" rx="18" ry="10" fill="#F5F5F5"/>
    </svg>
  );
}