import type { CSSProperties, ReactNode } from 'react';

export const CANVAS_ASSET_NODE_WIDTH = 240;
export const CANVAS_ASSET_NODE_HEIGHT = 132;

export const CANVAS_ASSET_NODE_STYLE = {
  width: CANVAS_ASSET_NODE_WIDTH,
  height: CANVAS_ASSET_NODE_HEIGHT,
} satisfies CSSProperties;

export const CANVAS_SUBTITLE_CLAMP_STYLE = {
  display: '-webkit-box',
  WebkitBoxOrient: 'vertical',
  WebkitLineClamp: 2,
  overflow: 'hidden',
} satisfies CSSProperties;

export type CanvasTriangleHandleColor = 'red' | 'orange' | 'green';
export type CanvasTriangleHandleDirection = 'input-right' | 'input-up' | 'output-right' | 'output-up';

export function getCanvasTriangleHandleClass(color: CanvasTriangleHandleColor, direction: CanvasTriangleHandleDirection) {
  return `crew-triangle-handle crew-triangle-handle--${color} crew-triangle-handle--${direction}`;
}

type CanvasAssetNodeStyle = CSSProperties & {
  '--crew-node-fill'?: string;
};

export type CanvasAssetNodeCardProps = {
  children: ReactNode;
  className: string;
  fillColor?: string;
  style?: CSSProperties;
};

export function CanvasAssetNodeCard({ children, className, fillColor, style }: CanvasAssetNodeCardProps) {
  const nodeStyle: CanvasAssetNodeStyle = {
    ...CANVAS_ASSET_NODE_STYLE,
    ...(fillColor ? { '--crew-node-fill': fillColor } : {}),
    ...style,
  };

  return (
    <div className={className} style={nodeStyle}>
      {children}
    </div>
  );
}

export type CanvasNodeLabelProps = {
  children: ReactNode;
  className?: string;
};

export function CanvasNodeLabel({ children, className = '' }: CanvasNodeLabelProps) {
  return <p className={`text-[10px] font-semibold uppercase tracking-[0.18em] ${className}`.trim()}>{children}</p>;
}

export type CanvasNodeTitleProps = {
  children: ReactNode;
};

export function CanvasNodeTitle({ children }: CanvasNodeTitleProps) {
  return <p className="mt-1 truncate text-sm font-black text-[#22170f]">{children}</p>;
}

export type CanvasToolChipsProps = {
  names?: readonly string[];
};

export function CanvasToolChips({ names }: CanvasToolChipsProps) {
  if (!names?.length) {
    return <p className="mt-2 text-xs text-stone-500">No tools attached.</p>;
  }

  return (
    <div className="mt-2 flex max-h-7 flex-wrap gap-1 overflow-hidden">
      {names.map((name) => (
        <span key={name} className="max-w-full truncate rounded border border-[#7a5739]/40 bg-[#fffaf0] px-2 py-1 text-[11px] font-semibold text-stone-700">
          {name}
        </span>
      ))}
    </div>
  );
}
