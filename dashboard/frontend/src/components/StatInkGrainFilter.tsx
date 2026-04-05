/**
 * Solid black glyphs; only the drop shadow uses stippled grain (offset + blurred glyph alpha).
 * Shadow is masked twice to the spray silhouette so it follows each digit’s shape, not a generic blob.
 */
export default function StatInkGrainFilter() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="1"
      height="1"
      className="pointer-events-none fixed left-0 top-0 h-px w-px overflow-hidden"
      aria-hidden={true}
    >
      <defs>
        <filter
          id="statInkGrain"
          x="-140%"
          y="-140%"
          width="380%"
          height="380%"
          colorInterpolationFilters="sRGB"
        >
          <feTurbulence
            type="fractalNoise"
            baseFrequency="3.8"
            numOctaves="2"
            stitchTiles="stitch"
            result="tFine"
          />
          <feColorMatrix
            in="tFine"
            type="matrix"
            values="0.2126 0.7152 0.0722 0 0  0.2126 0.7152 0.0722 0 0  0.2126 0.7152 0.0722 0 0  0 0 0 1 0"
            result="fMono"
          />
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.95"
            numOctaves="3"
            stitchTiles="stitch"
            result="tWide"
          />
          <feColorMatrix
            in="tWide"
            type="matrix"
            values="0.2126 0.7152 0.0722 0 0  0.2126 0.7152 0.0722 0 0  0.2126 0.7152 0.0722 0 0  0 0 0 1 0"
            result="wMono"
          />
          <feBlend in="fMono" in2="wMono" mode="multiply" result="nBlend" />
          <feColorMatrix
            in="nBlend"
            type="matrix"
            values="3.4 0 0 0 -0.45  0 3.4 0 0 -0.45  0 0 3.4 0 -0.45  0 0 0 1 0"
            result="grain"
          />

          {/* Shadow: smaller offset, slightly wider blur so the rim dissolves (fade) instead of cutting off */}
          <feOffset in="SourceAlpha" dx="-4" dy="-3" result="offA" />
          <feGaussianBlur in="offA" stdDeviation="4.8" result="spray" />
          <feComposite in="grain" in2="spray" operator="in" result="sClip" />
          <feComponentTransfer in="sClip" result="sThresh">
            <feFuncR type="linear" slope="7.5" intercept="-2.2" />
            <feFuncG type="linear" slope="7.5" intercept="-2.2" />
            <feFuncB type="linear" slope="7.5" intercept="-2.2" />
          </feComponentTransfer>
          <feComposite in="sThresh" in2="spray" operator="in" result="sShape" />
          <feColorMatrix
            in="sShape"
            type="matrix"
            values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0.2126 0.7152 0.0722 0 0"
            result="sMask"
          />
          <feComponentTransfer in="sMask" result="sDots">
            <feFuncA type="linear" slope="10" intercept="-3.6" />
          </feComponentTransfer>
          <feFlood floodColor="#000000" floodOpacity="0.38" result="black" />
          <feComposite in="black" in2="sDots" operator="in" result="shadowDots" />

          <feMerge>
            <feMergeNode in="shadowDots" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
    </svg>
  );
}
