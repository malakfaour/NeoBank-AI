export default function NeoLogo({ size = 48 }: { size?: number }) {
  const scale = size / 60;
  return (
    <svg width={200 * scale} height={60 * scale} viewBox="0 0 200 60" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* n */}
      <path d="M8 48V12H20L44 38V12H56V48H44L20 22V48H8Z" fill="#0A0A0A" />
      {/* e */}
      <path d="M66 30C66 19 74 11 86 11C98 11 106 19 106 31V34H78C79 38 82 41 86 41C90 41 92 39 94 37L103 41C100 46 94 49 86 49C74 49 66 41 66 30ZM78 27H94C93 23 90 20 86 20C82 20 79 23 78 27Z" fill="#0A0A0A" />
      {/* o — green oval */}
      <ellipse cx="152" cy="30" rx="36" ry="22" fill="#00C853" />
      <ellipse cx="152" cy="30" rx="22" ry="13" fill="#F0F0F0" />
    </svg>
  );
}