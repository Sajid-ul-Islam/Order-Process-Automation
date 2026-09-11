import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { KPIMetric } from '../types';

interface KPICardProps {
  metric: KPIMetric;
  accent?: 'emerald' | 'cyan' | 'amber' | 'blue';
}

function renderSparklineSvg(points?: number[], color: string = '#10b981') {
  if (!points || points.length < 2) return null;

  const width = 100;
  const height = 32;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;

  const coords = points.map((p, i) => {
    const x = (i / (points.length - 1)) * width;
    const y = height - 4 - ((p - min) / range) * (height - 8);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const pathD = `M ${coords.join(' L ')}`;
  const areaD = `${pathD} L ${width},${height} L 0,${height} Z`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-8 overflow-visible">
      <defs>
        <linearGradient id={`grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.0" />
        </linearGradient>
      </defs>
      <path d={areaD} fill={`url(#grad-${color.replace('#', '')})`} />
      <path d={pathD} fill="none" stroke={color} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export const KPICard: React.FC<KPICardProps> = ({ metric, accent = 'emerald' }) => {
  const accentColors = {
    emerald: '#10b981',
    cyan: '#06b6d4',
    amber: '#f59e0b',
    blue: '#3b82f6'
  };

  const color = accentColors[accent];
  const delta = metric.delta;
  const isPositive = delta ? (delta.positive ?? (typeof delta.value === 'number' ? delta.value >= 0 : !String(delta.value).startsWith('-'))) : null;

  return (
    <div className="glass-card rounded-xl p-4 flex flex-col justify-between transition-all duration-300 hover:border-emerald-500/30 hover:bg-slate-900/80 group relative overflow-hidden">
      {/* Top row: Label & Delta */}
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
          {metric.label}
        </span>
        {delta && (
          <div
            className={`
              flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full
              ${isPositive
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                : 'bg-rose-500/15 text-rose-400 border border-rose-500/20'
              }
            `}
          >
            {isPositive ? (
              <TrendingUp className="w-3 h-3" />
            ) : isPositive === false ? (
              <TrendingDown className="w-3 h-3" />
            ) : (
              <Minus className="w-3 h-3" />
            )}
            <span>{delta.text || String(delta.value)}</span>
          </div>
        )}
      </div>

      {/* Main Value */}
      <div className="my-2.5 flex items-baseline gap-1">
        {metric.prefix && (
          <span className="text-base font-semibold text-slate-400">{metric.prefix}</span>
        )}
        <span className="text-2xl sm:text-3xl font-bold tracking-tight text-white group-hover:text-emerald-300 transition-colors">
          {typeof metric.value === 'number' ? metric.value.toLocaleString() : metric.value}
        </span>
        {metric.suffix && (
          <span className="text-xs text-slate-400 ml-1">{metric.suffix}</span>
        )}
      </div>

      {/* Bottom Sparkline or Subtext */}
      <div className="mt-1">
        {metric.sparkline && metric.sparkline.length > 1 ? (
          renderSparklineSvg(metric.sparkline, color)
        ) : metric.subtext ? (
          <span className="text-[11px] text-slate-400">{metric.subtext}</span>
        ) : (
          <div className="h-4" />
        )}
      </div>
    </div>
  );
};
