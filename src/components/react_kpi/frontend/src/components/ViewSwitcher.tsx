import React from 'react';
import { Package, Truck, History, ListFilter } from 'lucide-react';

interface ViewSwitcherProps {
  views: string[];
  selectedView: string;
  viewCounts: Record<string, number>;
  onSelectView: (view: string) => void;
  disabled?: boolean;
}

const VIEW_ICONS: Record<string, React.ReactNode> = {
  "All Orders": <Package className="w-3.5 h-3.5" />,
  "Today Shipped": <Truck className="w-3.5 h-3.5" />,
  "Last Day Shipped": <History className="w-3.5 h-3.5" />,
  "Queue": <ListFilter className="w-3.5 h-3.5" />
};

export const ViewSwitcher: React.FC<ViewSwitcherProps> = ({
  views,
  selectedView,
  viewCounts,
  onSelectView,
  disabled
}) => {
  return (
    <div className="flex flex-wrap items-center gap-2 p-1.5 rounded-xl glass-pill max-w-fit">
      {views.map((view) => {
        const isSelected = view === selectedView;
        const count = viewCounts[view] ?? 0;
        const icon = VIEW_ICONS[view] || <Package className="w-3.5 h-3.5" />;

        return (
          <button
            key={view}
            type="button"
            disabled={disabled}
            onClick={() => onSelectView(view)}
            className={`
              relative flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 select-none
              ${isSelected
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/50 shadow-glow-emerald font-semibold'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent'
              }
              ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
            `}
          >
            <span className={isSelected ? 'text-emerald-400' : 'text-slate-500'}>
              {icon}
            </span>
            <span>{view}</span>
            <span
              className={`
                px-1.5 py-0.5 rounded-full text-[10px] font-bold transition-colors
                ${isSelected
                  ? 'bg-emerald-500/30 text-emerald-200'
                  : 'bg-slate-800 text-slate-400'
                }
              `}
            >
              {count.toLocaleString()}
            </span>
          </button>
        );
      })}
    </div>
  );
};
