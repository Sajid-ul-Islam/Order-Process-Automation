# Architecture

## Layer Diagram

```
┌─────────────────────────────────────────────────┐
│                    app.py                        │
│          (Auth gate, routing, layout)            │
├─────────────────────────────────────────────────┤
│                  src/pages/                       │
│   live_dashboard  sales_ingestion  pathao_orders │
│   stock_analytics  inventory_distribution        │
│   whatsapp_messaging  delivery_parser  data_pilot│
│   return_analytics  woocommerce_orders  excel_   │
│   merger                                         │
├─────────────────────────────────────────────────┤
│               src/components/                     │
│   dashboard/ (metrics, charts, filters, output)  │
│   layout/ (header, footer)  ui/ (styles, clock,  │
│   widgets, snapshot, status, smart_filters, ...) │
├─────────────────────────────────────────────────┤
│               src/services/                       │
│   woocommerce/ (client, stock)  pathao/ (client, │
│   status)  llm/manager  exports/excel_exporter   │
├─────────────────────────────────────────────────┤
│              src/processing/                      │
│   data_processing  column_detection              │
│   categorization  order_processor                │
│   whatsapp_processor  forecasting                │
│   delivery_parser                                │
├─────────────────────────────────────────────────┤
│   src/utils/       src/state/    src/inventory/  │
│   text  product    persistence   core            │
│   file_io logging  snapshots                     │
├─────────────────────────────────────────────────┤
│               src/config/                         │
│   settings  ui_config  constants                 │
└─────────────────────────────────────────────────┘
```

**Import rule**: Each layer imports only from layers below it or the same level. No circular imports.

## Data Flow

### Live Dashboard Sync

```
WooCommerce REST API
    │
    ▼
load_from_woocommerce()          [services/woocommerce/client.py]
    │
    ▼
scrub_raw_dataframe()            [processing/column_detection.py]
find_columns()                   [processing/column_detection.py]
    │
    ▼
process_data()                   [processing/data_processing.py]
  ├── get_category_for_sales()   [processing/categorization.py]
  ├── get_sub_category_for_sales()
  └── get_size_from_name()       [utils/product.py]
    │
    ▼
prepare_granular_data()          [processing/data_processing.py]
aggregate_data()                 [processing/data_processing.py]
    │
    ▼
render_dashboard_output()        [components/dashboard/dashboard_output.py]
  ├── KPI cards, charts (Plotly)
  ├── Association Rules (Market Basket)
  └── ML Forecasting Tournament  [processing/forecasting.py]
```

### Order Processing (Pathao)

```
Excel/CSV Upload or WooCommerce Fetch
    │
    ▼
process_orders_dataframe()       [processing/order_processor.py]
  ├── clean_dataframe()
  ├── identify_columns()
  ├── normalize_city_name()      [utils/text.py]
  └── peek_zone_from_address()   [utils/text.py]
    │
    ▼
PathaoClient.create_order()      [services/pathao/client.py]
```

### Inventory Distribution

```
Excel Upload or WooCommerce Stock Fetch
    │
    ▼
fetch_woocommerce_stock()        [services/woocommerce/stock.py]
    │
    ▼
inv_core.build_inventory_map()   [inventory/core.py]
inv_core.add_stock_columns()     [inventory/core.py]
  ├── Fuzzy name matching (rapidfuzz)
  ├── SKU matching
  └── Exact name matching
    │
    ▼
render_distribution_tab()        [pages/inventory_distribution.py]
```

## Session State

All `st.session_state` keys are preserved from the original codebase. Key groups:

| Prefix | Purpose | Example |
|--------|---------|---------|
| `live_*` | Live dashboard state | `live_sync_time`, `live_df_raw` |
| `manual_*` | Sales ingestion state | `manual_df_raw`, `manual_date_range` |
| `pathao_*` | Pathao orders state | `pathao_df`, `pathao_token` |
| `wp_*` | WhatsApp state | `wp_df`, `wp_messages` |
| `inv_*` | Inventory state | `inv_matrix_data` |
| `parser_*` | Delivery parser state | `parser_df`, `parser_results` |
| `stock_*` | Stock analytics state | `stock_snapshot_df` |
| `pilot_*` | Data Pilot state | `pilot_messages`, `pilot_context` |

## Caching Strategy

| Function | Decorator | TTL | Reason |
|----------|-----------|-----|--------|
| `load_from_woocommerce()` | `@st.cache_data` | 300s | Avoid hammering WooCommerce API |
| `find_columns()` | `@st.cache_data` | None | Pure function, deterministic |
| `scrub_raw_dataframe()` | `@st.cache_data` | None | Pure function, deterministic |
| `fetch_woocommerce_stock()` | `@st.cache_data` | 600s | Stock data changes slowly |
| `get_category_for_sales()` | `@lru_cache(1024)` | None | Hot path in categorization |
| `inject_base_styles()` | `@st.cache_resource` | None | CSS only needs to load once |

## External APIs

| Service | Module | Auth Method |
|---------|--------|-------------|
| WooCommerce | `services/woocommerce/` | Consumer key/secret (HTTP Basic) |
| Pathao Courier | `services/pathao/` | OAuth2 client credentials |
| OpenRouter | `services/llm/` | API key (Bearer token) |
| Gemini | `services/llm/` | API key |
| Groq | `services/llm/` | API key (Bearer token) |
