"use client";

// Drawing overlay (Phase 6.5). A canvas over the chart pane that maps data-space
// anchors ({time, price}) to pixels via the chart's coordinate converters and
// redraws on pan/zoom/resize. Also renders the Volume Profile. Interaction is
// active only while a tool is selected, so the chart stays pannable otherwise.
import type { IChartApi, ISeriesApi, SeriesType, Time } from "lightweight-charts";
import { type RefObject, useEffect, useRef } from "react";
import { chartColors, withAlpha } from "@/lib/chart";
import {
  TWO_POINT_TOOLS,
  distToSegment,
  fibPrices,
  measureStats,
  volumeProfile,
} from "@/lib/chartDrawings.mjs";

export type DrawTool =
  | "select"
  | "trendline"
  | "horizontal"
  | "vertical"
  | "ray"
  | "rectangle"
  | "fib"
  | "measure"
  | "text";

type Pt = { time: number; price: number };
export type Drawing = { id: string; type: string; points: Pt[]; text?: string };

type Bar = { date: string; high: number; low: number; close: number; volume: number };

type Props = {
  chartRef: RefObject<IChartApi | null>;
  getMain: () => ISeriesApi<SeriesType> | null;
  tool: DrawTool | null;
  drawings: Drawing[];
  selectedId: string | null;
  setSelectedId: (id: string | null) => void;
  onChange: (drawings: Drawing[], commit: boolean) => void;
  onToolDone: () => void;
  bars: Bar[];
  showVolumeProfile: boolean;
  levels?: { price: number; label: string; color: "gain" | "loss" | "accent" }[];
};

const uid = () => Math.random().toString(36).slice(2, 10);

export function DrawingCanvas({
  chartRef,
  getMain,
  tool,
  drawings,
  selectedId,
  setSelectedId,
  onChange,
  onToolDone,
  bars,
  showVolumeProfile,
  levels = [],
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const draft = useRef<Drawing | null>(null);
  const drag = useRef<{ id: string; last: Pt } | null>(null);
  // keep latest props for the imperative redraw loop
  const state = useRef({ drawings, selectedId, showVolumeProfile, bars, tool, levels });
  state.current = { drawings, selectedId, showVolumeProfile, bars, tool, levels };

  const toPx = (p: Pt) => {
    const chart = chartRef.current;
    const main = getMain();
    if (!chart || !main) return null;
    const x = chart.timeScale().timeToCoordinate(p.time as Time);
    const y = main.priceToCoordinate(p.price);
    if (x == null || y == null) return null;
    return { x: x as number, y: y as number };
  };
  const toData = (x: number, y: number): Pt | null => {
    const chart = chartRef.current;
    const main = getMain();
    if (!chart || !main) return null;
    let t = chart.timeScale().coordinateToTime(x);
    if (t == null) t = chart.timeScale().getVisibleRange()?.to ?? null;
    const price = main.coordinateToPrice(y);
    if (t == null || price == null) return null;
    return { time: t as unknown as number, price };
  };

  const redraw = () => {
    const canvas = canvasRef.current;
    const chart = chartRef.current;
    const main = getMain();
    if (!canvas || !chart || !main) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(rect.width * dpr) || canvas.height !== Math.round(rect.height * dpr)) {
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, rect.width, rect.height);
    const c = chartColors();
    const s = state.current;

    // Volume Profile (behind drawings, right-anchored)
    if (s.showVolumeProfile) {
      const buckets = volumeProfile(s.bars, 26);
      const maxW = Math.min(rect.width * 0.22, 140);
      ctx.fillStyle = withAlpha(c.accent, 38);
      for (const b of buckets) {
        const yTop = main.priceToCoordinate(b.hi);
        const yBot = main.priceToCoordinate(b.lo);
        if (yTop == null || yBot == null) continue;
        const h = Math.max(1, Math.abs((yBot as number) - (yTop as number)) - 1);
        const w = b.frac * maxW;
        ctx.fillRect(rect.width - w, (yTop as number), w, h);
      }
    }

    // Auto levels (support/resistance, AI targets) — dashed, right-labelled.
    ctx.font = "10px var(--font-sans, sans-serif)";
    for (const lv of s.levels) {
      const y = main.priceToCoordinate(lv.price);
      if (y == null) continue;
      const col = lv.color === "gain" ? c.gain : lv.color === "loss" ? c.loss : c.accent;
      ctx.strokeStyle = withAlpha(col, 150);
      ctx.fillStyle = col;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(0, y as number);
      ctx.lineTo(rect.width, y as number);
      ctx.stroke();
      ctx.setLineDash([]);
      const label = `${lv.label} ${lv.price.toFixed(2)}`;
      const w = ctx.measureText(label).width;
      ctx.fillText(label, rect.width - w - 4, (y as number) - 3);
    }

    const all = draft.current ? [...s.drawings, draft.current] : s.drawings;
    for (const d of all) drawShape(ctx, d, d.id === s.selectedId, rect, c);
  };

  const drawShape = (
    ctx: CanvasRenderingContext2D,
    d: Drawing,
    selected: boolean,
    rect: DOMRect,
    c: ReturnType<typeof chartColors>,
  ) => {
    const main = getMain();
    const col = selected ? c.accent : d.type === "measure" ? c.ink3 : c.accent;
    ctx.strokeStyle = col;
    ctx.fillStyle = col;
    ctx.lineWidth = selected ? 2 : 1.5;
    ctx.font = "11px var(--font-sans, sans-serif)";
    const p0 = d.points[0] ? toPx(d.points[0]) : null;
    const p1 = d.points[1] ? toPx(d.points[1]) : null;

    if (d.type === "horizontal" && p0 && main) {
      ctx.beginPath();
      ctx.moveTo(0, p0.y);
      ctx.lineTo(rect.width, p0.y);
      ctx.stroke();
      ctx.fillText(d.points[0].price.toFixed(2), 4, p0.y - 3);
    } else if (d.type === "vertical" && p0) {
      ctx.beginPath();
      ctx.moveTo(p0.x, 0);
      ctx.lineTo(p0.x, rect.height);
      ctx.stroke();
    } else if (d.type === "text" && p0) {
      ctx.font = "13px var(--font-sans, sans-serif)";
      ctx.fillText(d.text || "text", p0.x + 4, p0.y);
    } else if ((d.type === "trendline" || d.type === "ray" || d.type === "measure") && p0 && p1) {
      let ex = p1.x;
      let ey = p1.y;
      if (d.type === "ray") {
        const dx = p1.x - p0.x;
        const dy = p1.y - p0.y;
        const t = dx !== 0 ? (rect.width - p0.x) / dx : 1e6;
        ex = p0.x + dx * Math.max(t, 1);
        ey = p0.y + dy * Math.max(t, 1);
      }
      if (d.type === "measure") ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(p0.x, p0.y);
      ctx.lineTo(ex, ey);
      ctx.stroke();
      ctx.setLineDash([]);
      if (d.type === "measure") {
        const m = measureStats(d.points[0].price, d.points[1].price, 0, 0);
        const label = `${m.dPrice >= 0 ? "+" : ""}${m.dPrice.toFixed(2)} (${m.dPct.toFixed(2)}%)`;
        ctx.fillStyle = m.dPrice >= 0 ? c.gain : c.loss;
        ctx.fillText(label, (p0.x + p1.x) / 2 + 4, (p0.y + p1.y) / 2 - 4);
      }
    } else if (d.type === "rectangle" && p0 && p1) {
      const x = Math.min(p0.x, p1.x);
      const y = Math.min(p0.y, p1.y);
      const w = Math.abs(p1.x - p0.x);
      const h = Math.abs(p1.y - p0.y);
      ctx.fillStyle = withAlpha(c.accent, 22);
      ctx.fillRect(x, y, w, h);
      ctx.strokeRect(x, y, w, h);
    } else if (d.type === "fib" && p0 && p1 && main) {
      for (const lv of fibPrices(d.points[0].price, d.points[1].price)) {
        const y = main.priceToCoordinate(lv.price);
        if (y == null) continue;
        ctx.strokeStyle = withAlpha(c.accent, 150);
        ctx.beginPath();
        ctx.moveTo(Math.min(p0.x, p1.x), y as number);
        ctx.lineTo(Math.max(p0.x, p1.x), y as number);
        ctx.stroke();
        ctx.fillStyle = c.ink3;
        ctx.fillText(`${lv.level} ${lv.price.toFixed(2)}`, Math.min(p0.x, p1.x) + 2, (y as number) - 2);
      }
    }
  };

  // --- pointer interaction --------------------------------------------------
  const hitTest = (x: number, y: number): string | null => {
    for (let i = state.current.drawings.length - 1; i >= 0; i--) {
      const d = state.current.drawings[i];
      const a = d.points[0] ? toPx(d.points[0]) : null;
      const b = d.points[1] ? toPx(d.points[1]) : null;
      if (!a) continue;
      const canvas = canvasRef.current;
      const w = canvas ? canvas.getBoundingClientRect().width : 0;
      if (d.type === "horizontal" && Math.abs(y - a.y) < 6) return d.id;
      if (d.type === "vertical" && Math.abs(x - a.x) < 6) return d.id;
      if (d.type === "text" && Math.hypot(x - a.x, y - a.y) < 14) return d.id;
      if (b) {
        if (d.type === "rectangle") {
          const inX = x >= Math.min(a.x, b.x) - 4 && x <= Math.max(a.x, b.x) + 4;
          const inY = y >= Math.min(a.y, b.y) - 4 && y <= Math.max(a.y, b.y) + 4;
          const nearEdge =
            Math.abs(y - a.y) < 6 || Math.abs(y - b.y) < 6 || Math.abs(x - a.x) < 6 || Math.abs(x - b.x) < 6;
          if (inX && inY && nearEdge) return d.id;
        } else if (distToSegment(x, y, a.x, a.y, d.type === "ray" ? w : b.x, b.y) < 6) {
          return d.id;
        }
      }
    }
    return null;
  };

  const localXY = (e: PointerEvent) => {
    const r = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };

  const onDown = (e: PointerEvent) => {
    const t = state.current.tool;
    if (!t) return;
    const { x, y } = localXY(e);
    const pt = toData(x, y);
    if (!pt) return;
    canvasRef.current?.setPointerCapture(e.pointerId);
    if (t === "select") {
      const id = hitTest(x, y);
      setSelectedId(id);
      if (id) drag.current = { id, last: pt };
      return;
    }
    if (t === "text") {
      const text = window.prompt("Text label:")?.trim();
      if (text) onChange([...state.current.drawings, { id: uid(), type: "text", points: [pt], text }], true);
      onToolDone();
      return;
    }
    if (t === "horizontal" || t === "vertical") {
      onChange([...state.current.drawings, { id: uid(), type: t, points: [pt] }], true);
      onToolDone();
      return;
    }
    // two-point tools: start a draft
    draft.current = { id: uid(), type: t, points: [pt, pt] };
    redraw();
  };

  const onMove = (e: PointerEvent) => {
    const { x, y } = localXY(e);
    const pt = toData(x, y);
    if (!pt) return;
    if (draft.current) {
      draft.current.points[1] = pt;
      redraw();
    } else if (drag.current) {
      const dt = pt.time - drag.current.last.time;
      const dp = pt.price - drag.current.last.price;
      drag.current.last = pt;
      const next = state.current.drawings.map((d) =>
        d.id === drag.current!.id
          ? { ...d, points: d.points.map((q) => ({ time: q.time + dt, price: q.price + dp })) }
          : d,
      );
      onChange(next, false);
    }
  };

  const onUp = (e: PointerEvent) => {
    canvasRef.current?.releasePointerCapture(e.pointerId);
    if (draft.current) {
      const d = draft.current;
      draft.current = null;
      if (TWO_POINT_TOOLS.includes(d.type)) {
        onChange([...state.current.drawings, d], true);
      }
      onToolDone();
    } else if (drag.current) {
      drag.current = null;
      onChange(state.current.drawings, true); // commit the moved position to history
    }
  };

  // wire pointer + redraw
  useEffect(() => {
    const canvas = canvasRef.current;
    const chart = chartRef.current;
    if (!canvas || !chart) return;
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    let raf = 0;
    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(redraw);
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(schedule);
    const ro = new ResizeObserver(schedule);
    ro.observe(canvas);
    schedule();
    return () => {
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      chart.timeScale().unsubscribeVisibleTimeRangeChange(schedule);
      ro.disconnect();
      cancelAnimationFrame(raf);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartRef.current]);

  // redraw when data/selection/tool change
  useEffect(() => {
    redraw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawings, selectedId, showVolumeProfile, bars, tool, levels]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 h-full w-full"
      style={{ pointerEvents: tool ? "auto" : "none", cursor: tool && tool !== "select" ? "crosshair" : "default" }}
    />
  );
}
