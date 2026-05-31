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
          x="-70%"
          y="-70%"
          width="240%"
          height="240%"
          colorInterpolationFilters="sRGB"
        >
          <feTurbulence
            type="fractalNoise"
            baseFrequency="4.6"
            numOctaves="2"
            stitchTiles="stitch"
            seed="17"
            result="fineNoise"
          />
          <feColorMatrix
            in="fineNoise"
            type="matrix"
            values="0.2126 0.7152 0.0722 0 0  0.2126 0.7152 0.0722 0 0  0.2126 0.7152 0.0722 0 0  0 0 0 1 0"
            result="fineMono"
          />
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.72"
            numOctaves="4"
            stitchTiles="stitch"
            seed="29"
            result="wideNoise"
          />
          <feColorMatrix
            in="wideNoise"
            type="matrix"
            values="0.2126 0.7152 0.0722 0 0  0.2126 0.7152 0.0722 0 0  0.2126 0.7152 0.0722 0 0  0 0 0 1 0"
            result="wideMono"
          />
          <feBlend in="fineMono" in2="wideMono" mode="multiply" result="inkTexture" />
          <feColorMatrix
            in="inkTexture"
            type="matrix"
            values="4.6 0 0 0 -1.05  0 4.6 0 0 -1.05  0 0 4.6 0 -1.05  0 0 0 1 0"
            result="inkDots"
          />

          <feMorphology in="SourceAlpha" operator="dilate" radius="0.7" result="inkBody" />
          <feGaussianBlur in="inkBody" stdDeviation="2.8" result="softBloom" />
          <feGaussianBlur in="SourceAlpha" stdDeviation="0.85" result="tightBloom" />
          <feComposite in="inkDots" in2="softBloom" operator="in" result="softDots" />
          <feComposite in="inkDots" in2="tightBloom" operator="in" result="tightDots" />
          <feComposite in="inkDots" in2="SourceAlpha" operator="in" result="coreDots" />
          <feComponentTransfer in="softDots" result="softStipple">
            <feFuncR type="linear" slope="4.8" intercept="-2.05" />
            <feFuncG type="linear" slope="4.8" intercept="-2.05" />
            <feFuncB type="linear" slope="4.8" intercept="-2.05" />
            <feFuncA type="linear" slope="0.62" intercept="-0.12" />
          </feComponentTransfer>
          <feComponentTransfer in="tightDots" result="tightStipple">
            <feFuncR type="linear" slope="8.4" intercept="-2.75" />
            <feFuncG type="linear" slope="8.4" intercept="-2.75" />
            <feFuncB type="linear" slope="8.4" intercept="-2.75" />
            <feFuncA type="linear" slope="2.6" intercept="-0.05" />
          </feComponentTransfer>
          <feComponentTransfer in="coreDots" result="coreStipple">
            <feFuncR type="linear" slope="8.8" intercept="-2.7" />
            <feFuncG type="linear" slope="8.8" intercept="-2.7" />
            <feFuncB type="linear" slope="8.8" intercept="-2.7" />
            <feFuncA type="linear" slope="4.8" intercept="0" />
          </feComponentTransfer>
          <feColorMatrix
            in="softStipple"
            type="matrix"
            values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0.2126 0.7152 0.0722 0 0"
            result="softMask"
          />
          <feColorMatrix
            in="tightStipple"
            type="matrix"
            values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0.2126 0.7152 0.0722 0 0"
            result="tightMask"
          />
          <feColorMatrix
            in="coreStipple"
            type="matrix"
            values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0.2126 0.7152 0.0722 0 0"
            result="coreMask"
          />
          <feFlood floodColor="#000000" floodOpacity="0.16" result="black" />
          <feFlood floodColor="#000000" floodOpacity="0.8" result="denseBlack" />
          <feFlood floodColor="#000000" floodOpacity="1" result="coreBlack" />
          <feComposite in="black" in2="softMask" operator="in" result="softInk" />
          <feComposite in="denseBlack" in2="tightMask" operator="in" result="denseInk" />
          <feComposite in="coreBlack" in2="coreMask" operator="in" result="coreInk" />

          <feMerge>
            <feMergeNode in="softInk" />
            <feMergeNode in="denseInk" />
            <feMergeNode in="coreInk" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
    </svg>
  );
}
