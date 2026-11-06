// KisaanMitra mark (Step 7.4): a seedling coming up out of a protective shield.
// Pure vector, so it stays sharp from 16px to 120px. Colours: saffron shoot tip, emerald foliage, navy shield outline.
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
      {/* Shield: the protective contour */}
      <path d="M24 3 L42 9 V23 C42 34 34 41 24 45 C14 41 6 34 6 23 V9 Z" fill="#131d27" stroke="#1e293b" strokeWidth="2" strokeLinejoin="round" />
      {/* Stem */}
      <path d="M24 39 V21" stroke="#22c55e" strokeWidth="2.5" strokeLinecap="round" />
      {/* Left leaf */}
      <path d="M24 26 C20 26 15 23 14 17 C19 17 23 20 24 26 Z" fill="#16a34a" />
      {/* Right leaf */}
      <path d="M24 22 C24 16 28 12 34 12 C34 18 30 22 24 22 Z" fill="#22c55e" />
      {/* Saffron shoot tip */}
      <circle cx="24" cy="19" r="2.2" fill="#ff9933" />
    </svg>
  );
}
