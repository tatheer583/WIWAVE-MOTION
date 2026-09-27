import { useEffect, useRef } from 'react';

// Rolling heatmap of subcarrier amplitudes: one row per update, newest on top.
export default function CsiWaterfall({ preview }) {
  const canvasRef = useRef(null);
  const rows = useRef([]);

  useEffect(() => {
    if (!Array.isArray(preview) || !preview.length) return;
    rows.current = [...rows.current, preview].slice(-90);
    const canvas = canvasRef.current;
    if (!canvas) return;
    const width = 640, height = 220;
    canvas.width = width; canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#0a0f14';
    ctx.fillRect(0, 0, width, height);
    const all = rows.current.flat();
    const max = Math.max(...all, 1), min = Math.min(...all, 0);
    const span = Math.max(1e-6, max - min);
    const rowCount = rows.current.length, cols = preview.length;
    const rowHeight = height / rowCount, colWidth = width / cols;
    rows.current.forEach((row, r) => {
      const y = height - (r + 1) * rowHeight;
      row.forEach((value, c) => {
        const t = Math.max(0, Math.min(1, (value - min) / span));
        ctx.fillStyle = `hsl(${185 - 185 * t}, 80%, ${16 + 46 * t}%)`;
        ctx.fillRect(c * colWidth, y, colWidth + 1, rowHeight + 1);
      });
    });
  }, [preview]);

  return <div className="waterfall">
    <canvas ref={canvasRef} role="img" aria-label="Subcarrier amplitude waterfall, newest rows on top" />
    <div className="waterfall-caption"><span>90 frames ago</span><span>Subcarrier amplitude · newest on top</span><span>Now</span></div>
  </div>;
}
