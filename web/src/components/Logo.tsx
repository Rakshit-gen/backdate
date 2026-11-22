/**
 * Two rows of stored facts. The lower row was corrected at the red mark, and everything
 * after the mark is redrawn in red: the part backdate recomputes.
 */
export function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <g fill="none" strokeLinecap="round">
        <path d="M6 11H26" stroke="currentColor" strokeWidth="3.5" opacity="0.45" />
        <path d="M6 21H11" stroke="currentColor" strokeWidth="3.5" />
        <path d="M18 21H26" stroke="var(--redpen)" strokeWidth="3.5" />
        <path d="M14.5 5V27" stroke="var(--redpen)" strokeWidth="2.5" />
      </g>
    </svg>
  );
}
