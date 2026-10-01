/**
 * Lightweight inline SVG illustrations.
 * Used for empty states, login branding, chat empty state, errors.
 */

export function IllustrationNoApps({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 160" fill="none" xmlns="http://www.w3.org/2000/svg"
      className={className} aria-hidden="true">
      {/* Grid background */}
      <rect width="200" height="160" rx="12" fill="hsl(252 84% 97%)" />
      {/* Server blocks */}
      <rect x="30" y="48" width="60" height="72" rx="6" fill="white" stroke="hsl(252 84% 57% / 0.2)" strokeWidth="1.5"/>
      <rect x="40" y="62" width="40" height="6" rx="3" fill="hsl(252 84% 57% / 0.3)"/>
      <rect x="40" y="74" width="28" height="6" rx="3" fill="hsl(252 84% 57% / 0.15)"/>
      <rect x="40" y="86" width="34" height="6" rx="3" fill="hsl(252 84% 57% / 0.15)"/>
      {/* Connection line */}
      <path d="M90 84 H110" stroke="hsl(252 84% 57% / 0.4)" strokeWidth="1.5" strokeDasharray="3 3"/>
      <circle cx="90" cy="84" r="3" fill="hsl(252 84% 57% / 0.5)"/>
      <circle cx="110" cy="84" r="3" fill="hsl(252 84% 57% / 0.5)"/>
      {/* Bot head */}
      <rect x="110" y="60" width="60" height="48" rx="8" fill="white" stroke="hsl(252 84% 57% / 0.25)" strokeWidth="1.5"/>
      <circle cx="128" cy="78" r="5" fill="hsl(252 84% 57% / 0.4)"/>
      <circle cx="152" cy="78" r="5" fill="hsl(252 84% 57% / 0.4)"/>
      <path d="M126 90 Q140 97 154 90" stroke="hsl(252 84% 57% / 0.5)" strokeWidth="1.5" strokeLinecap="round" fill="none"/>
      {/* Antenna */}
      <path d="M140 60 V52" stroke="hsl(252 84% 57% / 0.4)" strokeWidth="1.5" strokeLinecap="round"/>
      <circle cx="140" cy="50" r="3" fill="hsl(252 84% 57% / 0.5)"/>
      {/* Plus icon hint */}
      <circle cx="140" cy="130" r="14" fill="hsl(252 84% 57%)"/>
      <path d="M140 124 V136 M134 130 H146" stroke="white" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  );
}

export function IllustrationNoLogs({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 140" fill="none" xmlns="http://www.w3.org/2000/svg"
      className={className} aria-hidden="true">
      <rect width="200" height="140" rx="12" fill="hsl(220 18% 97%)"/>
      {/* Lines representing log entries — mostly faded */}
      {[28,44,60,76,92,108].map((y, i) => (
        <rect key={y} x="24" y={y} width={i === 2 ? 152 : i === 0 ? 120 : 90 + i * 8} height="8" rx="4"
          fill={i === 0 ? "hsl(252 84% 57% / 0.25)" : "hsl(220 12% 88%)"}/>
      ))}
      {/* Magnifier */}
      <circle cx="148" cy="94" r="26" fill="white" stroke="hsl(220 16% 88%)" strokeWidth="1.5"/>
      <circle cx="148" cy="94" r="14" fill="none" stroke="hsl(252 84% 57% / 0.35)" strokeWidth="2.5"/>
      <path d="M158 104 L168 114" stroke="hsl(252 84% 57% / 0.5)" strokeWidth="3" strokeLinecap="round"/>
      <path d="M144 91 H152 M148 87 V95" stroke="hsl(252 84% 57% / 0.5)" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}

export function IllustrationNoResults({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 160 120" fill="none" xmlns="http://www.w3.org/2000/svg"
      className={className} aria-hidden="true">
      <circle cx="80" cy="55" r="38" fill="hsl(252 84% 97%)"/>
      <circle cx="80" cy="55" r="22" fill="none" stroke="hsl(252 84% 57% / 0.3)" strokeWidth="2.5"/>
      <path d="M96 71 L110 85" stroke="hsl(252 84% 57% / 0.4)" strokeWidth="3.5" strokeLinecap="round"/>
      <path d="M72 48 H88 M80 40 V56" stroke="hsl(252 84% 57% / 0.4)" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  );
}

export function IllustrationError({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 160 120" fill="none" xmlns="http://www.w3.org/2000/svg"
      className={className} aria-hidden="true">
      <circle cx="80" cy="56" r="38" fill="hsl(0 72% 96%)"/>
      <circle cx="80" cy="56" r="24" fill="none" stroke="hsl(0 72% 50% / 0.35)" strokeWidth="2.5"/>
      <path d="M80 44 V60" stroke="hsl(0 72% 50% / 0.6)" strokeWidth="2.5" strokeLinecap="round"/>
      <circle cx="80" cy="67" r="2" fill="hsl(0 72% 50% / 0.6)"/>
    </svg>
  );
}

export function IllustrationChatEmpty({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 160" fill="none" xmlns="http://www.w3.org/2000/svg"
      className={className} aria-hidden="true">
      {/* Bot body */}
      <rect x="62" y="38" width="76" height="68" rx="14" fill="hsl(252 84% 97%)" stroke="hsl(252 84% 57% / 0.2)" strokeWidth="1.5"/>
      {/* Eyes */}
      <circle cx="88" cy="68" r="7" fill="hsl(252 84% 57% / 0.2)"/>
      <circle cx="112" cy="68" r="7" fill="hsl(252 84% 57% / 0.2)"/>
      <circle cx="88" cy="68" r="3.5" fill="hsl(252 84% 57% / 0.7)"/>
      <circle cx="112" cy="68" r="3.5" fill="hsl(252 84% 57% / 0.7)"/>
      {/* Mouth */}
      <path d="M86 82 Q100 90 114 82" stroke="hsl(252 84% 57% / 0.5)" strokeWidth="2" strokeLinecap="round" fill="none"/>
      {/* Antenna */}
      <path d="M100 38 V28" stroke="hsl(252 84% 57% / 0.4)" strokeWidth="2" strokeLinecap="round"/>
      <circle cx="100" cy="25" r="4" fill="hsl(252 84% 57% / 0.5)"/>
      {/* Arms */}
      <rect x="42" y="56" width="20" height="10" rx="5" fill="hsl(252 84% 57% / 0.2)" stroke="hsl(252 84% 57% / 0.2)" strokeWidth="1"/>
      <rect x="138" y="56" width="20" height="10" rx="5" fill="hsl(252 84% 57% / 0.2)" stroke="hsl(252 84% 57% / 0.2)" strokeWidth="1"/>
      {/* Chat bubbles */}
      <rect x="28" y="118" width="64" height="24" rx="8" fill="hsl(252 84% 57% / 0.12)"/>
      <rect x="108" y="118" width="64" height="24" rx="8" fill="hsl(252 84% 57%)"/>
      <rect x="36" y="125" width="48" height="4" rx="2" fill="hsl(252 84% 57% / 0.3)"/>
      <rect x="116" y="122" width="48" height="4" rx="2" fill="white/60"/>
      <rect x="116" y="130" width="32" height="4" rx="2" fill="white/40"/>
    </svg>
  );
}

/** Right-panel branding for the login page */
export function IllustrationLoginBranding({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 400 400" fill="none" xmlns="http://www.w3.org/2000/svg"
      className={className} aria-hidden="true">
      {/* Concentric rings */}
      <circle cx="200" cy="200" r="160" stroke="hsl(252 84% 57% / 0.08)" strokeWidth="1"/>
      <circle cx="200" cy="200" r="120" stroke="hsl(252 84% 57% / 0.10)" strokeWidth="1"/>
      <circle cx="200" cy="200" r="80"  stroke="hsl(252 84% 57% / 0.12)" strokeWidth="1"/>
      <circle cx="200" cy="200" r="40"  fill="hsl(252 84% 57% / 0.12)"/>

      {/* Center bot */}
      <circle cx="200" cy="200" r="28" fill="hsl(252 84% 57%)"/>
      <circle cx="191" cy="197" r="4" fill="white" opacity="0.9"/>
      <circle cx="209" cy="197" r="4" fill="white" opacity="0.9"/>
      <path d="M192 207 Q200 213 208 207" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" opacity="0.9"/>
      <path d="M200 172 V162" stroke="hsl(252 84% 57% / 0.5)" strokeWidth="2" strokeLinecap="round"/>
      <circle cx="200" cy="160" r="4" fill="hsl(252 84% 57% / 0.6)"/>

      {/* Satellites */}
      {[
        [200, 80],  [320, 200], [200, 320], [80, 200],
        [271, 129], [271, 271], [129, 271], [129, 129],
      ].map(([cx, cy], i) => (
        <g key={i}>
          <line x1="200" y1="200" x2={cx} y2={cy}
            stroke="hsl(252 84% 57% / 0.12)" strokeWidth="1" strokeDasharray="4 4"/>
          <circle cx={cx} cy={cy} r={i < 4 ? 8 : 6}
            fill="white" stroke="hsl(252 84% 57% / 0.3)" strokeWidth="1.5"/>
        </g>
      ))}
    </svg>
  );
}
