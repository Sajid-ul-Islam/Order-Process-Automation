import React from 'react';
import { UserCheck } from 'lucide-react';
import { CustomerMixData } from '../types';

interface CustomerMixProps {
  data: CustomerMixData;
}

export const CustomerMix: React.FC<CustomerMixProps> = ({ data }) => {
  const { newCount, returningCount, returningRatio } = data;
  const safeRatio = Math.max(0, Math.min(100, returningRatio || 0));

  return (
    <div className="glass-card rounded-xl p-4 flex flex-col justify-between transition-all duration-300 hover:border-cyan-500/40 hover:bg-slate-50 dark:hover:bg-slate-900/80 group">
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">
          Customer Mix
        </span>
        <div className="flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-cyan-50 text-cyan-700 border border-cyan-200 dark:bg-cyan-500/15 dark:text-cyan-400 dark:border-cyan-500/20">
          <UserCheck className="w-3 h-3" />
          <span>{safeRatio.toFixed(1)}% Returning</span>
        </div>
      </div>

      {/* Numerical breakdown */}
      <div className="my-2.5 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-1 text-[11px] text-slate-600 dark:text-slate-400 font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            New
          </div>
          <div className="text-xl font-bold text-slate-900 dark:text-white mt-0.5 tabular-nums">
            {newCount.toLocaleString()}
          </div>
        </div>

        <div className="text-right">
          <div className="flex items-center justify-end gap-1 text-[11px] text-slate-600 dark:text-slate-400 font-medium">
            <span className="w-2 h-2 rounded-full bg-cyan-500"></span>
            Returning
          </div>
          <div className="text-xl font-bold text-slate-900 dark:text-white mt-0.5 tabular-nums">
            {returningCount.toLocaleString()}
          </div>
        </div>
      </div>

      {/* Segmented ratio bar */}
      <div className="mt-2">
        <div className="w-full h-2 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden flex">
          <div
            style={{ width: `${100 - safeRatio}%` }}
            className="bg-emerald-500 transition-all duration-500"
            title={`New: ${100 - safeRatio}%`}
          />
          <div
            style={{ width: `${safeRatio}%` }}
            className="bg-cyan-400 transition-all duration-500"
            title={`Returning: ${safeRatio}%`}
          />
        </div>
        <div className="flex justify-between text-[10px] text-slate-500 dark:text-slate-400 mt-1 font-medium">
          <span>{((100 - safeRatio) || 0).toFixed(0)}% New</span>
          <span>{(safeRatio || 0).toFixed(0)}% Repeat</span>
        </div>
      </div>
    </div>
  );
};
