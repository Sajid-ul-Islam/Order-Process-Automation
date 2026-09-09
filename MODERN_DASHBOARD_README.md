# Modern KPI Dashboard Component

A human-centric dashboard component that follows five key design principles to avoid common "AI-generated" design clichés.

## Design Principles

### 1. Flat Accents, Not Gradients
- ❌ Avoid: Purple-to-blue decorative gradients on headers, buttons, or chart fills
- ✅ Use: One flat accent color so color conveys actual meaning rather than acting as filler

### 2. Make the Number the Hero
- ❌ Avoid: Icons inside pastel-colored tiles, different colors for every metric
- ✅ Use: Drop colored tiles and make the data/number the visual hero of the card

### 3. Establish Clear Hierarchy
- ❌ Avoid: All metric cards the exact same size and weight
- ✅ Use: One primary metric large, three secondary metrics smaller so user's eye knows where to land

### 4. Refine Shadows and Corners
- ❌ Avoid: 16-pixel rounded corners and drop shadows on every element
- ✅ Use: Hairline borders and tighter border radii (6px) on smaller parts; shadows only on floating elements

### 5. Use Meaningful Data Displays
- ❌ Avoid: Generic placeholder greetings, shapeless numbers
- ✅ Use: Explicit time periods, tabular digits for alignment, sparklines for trends

## Files Created

```
src/components/dashboard/modern_kpi.py    # Main KPI rendering component
assets/styles.css                         # CSS styles (appended ~200 lines)
examples/modern_dashboard_demo.py         # Usage example
```

## Usage

### Basic Integration

```python
from src.components.dashboard.modern_kpi import render_modern_kpi_cards

# In your Streamlit page
drill, summ, top, basket = render_modern_kpi_cards(
    m_df=current_data,
    c_df=comparison_data,
    nav_mode="Today",
    dummy_mapping={},
    wc_raw_mapping={"date": "Order Date", "order_id": "Order ID"},
)
```

### Required Data Columns

The function expects DataFrames with these columns:
- `Order ID` - Unique order identifier
- `Order Date` - Timestamp of order
- `Quantity` - Number of items
- `Item Cost` - Per-item cost
- `Gross Amount` - Order total before discounts
- `Cashback Discount` - Discount/cashback amount
- `Total Amount` - Final amount after discounts
- `Customer Phone` or `Email` - For customer identification

### CSS Classes

The component uses these CSS classes (already in `assets/styles.css`):

```css
/* Container */
.kpi-container

/* Cards */
.kpi-card              /* Base card style */
.kpi-card-primary      /* Larger, prominent (for revenue) */
.kpi-card-secondary    /* Smaller, supporting metrics */

/* Content */
.kpi-label             /* Metric label (small, uppercase) */
.kpi-value             /* Metric value (large number) */
.kpi-value-primary     /* Extra-large for primary metric */
.kpi-prev              /* Previous period badge */

/* Deltas */
.kpi-delta             /* Base delta indicator */
.kpi-delta-up          /* Green positive change */
.kpi-delta-down        /* Red negative change */
.kpi-delta-warning     /* Amber warning state */
```

## Visual Hierarchy

The layout creates clear visual hierarchy:

```
┌─────────────────────────────┬──────────┬──────────┬──────────┬──────────┐
│  NET REVENUE · Today (BDT)  │  Orders  │   Items  │   AOV    │Customers │
│         ৳25,450             │   142    │    387   │  ৳179    │ 89N/53R  │
│  Prev: ৳22,100              │Prev: 128 │ Prev:352 │Prev:৳172 │          │
│  ▲ +৳3,350 (+15.2%)         │▲ +14     │  ▲ +35   │ ▲ +৳7    │          │
│  [sparkline trend...]       │[trend]   │ [trend]  │ [trend]  │          │
└─────────────────────────────┴──────────┴──────────┴──────────┴──────────┘
         ↑ PRIMARY                    ↑ SECONDARY METRICS
    (spans 2 columns, larger)         (smaller, supporting)
```

## Running the Demo

```bash
streamlit run examples/modern_dashboard_demo.py
```

## Key Features

1. **36-hour sparkline trends** - Visual trend indicators for each metric
2. **Previous period comparison** - Shows prior period values and deltas
3. **Responsive design** - Adapts from 5 columns to 1 column on mobile
4. **Dark mode support** - Automatic via `prefers-color-scheme`
5. **Tabular numbers** - Uses `font-variant-numeric: tabular-nums` for alignment
6. **Semantic colors** - Green for positive, red for negative, amber for warnings

## Comparison: Old vs New

| Aspect | Old Design | New Design |
|--------|-----------|------------|
| Corners | 16px everywhere | 6px on cards, 4px on badges |
| Shadows | On all cards | Only on hover/floating |
| Colors | Gradient fills | Flat semantic colors |
| Icons | Decorative emojis | Removed (data is hero) |
| Size | All cards equal | Primary spans 2x width |
| Numbers | Standard fonts | Tabular-nums for alignment |
| Context | No time labels | Explicit period labels |
| Trends | Percentage badges | Sparkline charts |

## Dependencies

- Python 3.10+
- Streamlit
- Pandas
- Polars (for data processing module)
