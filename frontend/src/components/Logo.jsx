// Original KisaanMitra brand mark: golden sunrise, resilient crop sprout, and live digital decision pulse.
// Role="img" with accessible aria-label; crisp at 16px to 64px.
export default function Logo({ size = 28, className = "" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`logo-mark ${className}`}
      role="img"
      aria-label="KisaanMitra logo"
    >
      {/* Background circle badge */}
      <circle cx="24" cy="24" r="22" fill="#13231B" stroke="#254B35" strokeWidth="2" />
      {/* Golden dawn / sun rays */}
      <circle cx="24" cy="18" r="7" fill="#E67E22" opacity="0.9" />
      <path d="M24 6v3M33 9l-2 2M15 9l2 2" stroke="#F39C12" strokeWidth="2" strokeLinecap="round" />
      {/* Resilient crop leaves */}
      <path
        d="M24 38c0-8-6-14-11-13 1 6 5 12 11 13z"
        fill="#27AE60"
        stroke="#1E8449"
        strokeWidth="1.5"
      />
      <path
        d="M24 38c0-8 6-14 11-13-1 6-5 12-11 13z"
        fill="#2ECC71"
        stroke="#27AE60"
        strokeWidth="1.5"
      />
      {/* Central stem */}
      <path d="M24 38V21" stroke="#A9DFBF" strokeWidth="2.5" strokeLinecap="round" />
      {/* Live decision pulse / heartbeat */}
      <path
        d="M10 27h6l2.5-4 4 8 3.5-6 3 2h9"
        stroke="#FFFFFF"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.85"
      />
    </svg>
  );
}
