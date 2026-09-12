export interface KPIMetric {
  label: string;
  value: string | number;
  prefix?: string;
  suffix?: string;
  delta?: {
    value: string | number;
    pct?: number;
    positive?: boolean;
    text?: string;
  };
  sparkline?: number[];
  subtext?: string;
}

export interface CustomerMixData {
  newCount: number;
  returningCount: number;
  returningRatio: number; // 0 to 100
}

export interface ComponentArgs {
  views: string[];
  selectedView: string;
  viewCounts: Record<string, number>;
  metrics: {
    revenue: KPIMetric;
    orders: KPIMetric;
    units: KPIMetric;
    aov: KPIMetric;
  };
  customerMix: CustomerMixData;
  syncTime?: string;
}

export interface StreamlitRenderMessage {
  type: "streamlit:render";
  args: ComponentArgs;
  disabled: boolean;
  theme?: {
    base: string;
    primaryColor: string;
    backgroundColor: string;
    secondaryBackgroundColor: string;
    textColor: string;
    font: string;
  };
}
