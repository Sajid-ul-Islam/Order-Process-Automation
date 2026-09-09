"""Jakob's Law Navigation Component - UX-compliant navigation following established patterns.

Jakob's Law states that users spend most of their time in other apps, so they expect
your app to work the same way. This component enforces:
1. Maximum 5 tabs for core actions
2. Home on far left
3. Profile on far right  
4. Create action in middle (if applicable)
5. Settings in profile or top-right (NOT in bottom nav)
"""

from __future__ import annotations

import streamlit as st


def render_jakobs_law_nav(
    home_callback,
    orders_callback,
    create_callback=None,
    analytics_callback=None,
    profile_callback=None,
) -> None:
    """Render Jakob's Law compliant navigation with 5 tabs maximum.
    
    Args:
        home_callback: Callback for Home/Dashboard tab (far left)
        orders_callback: Callback for Orders/Tracking tab
        create_callback: Optional callback for primary creation action (center)
        analytics_callback: Callback for Analytics/Reports tab
        profile_callback: Callback for Profile/Settings tab (far right)
    """
    # Build tab list dynamically based on provided callbacks
    tabs_config = []
    
    # Tab 1: Home (ALWAYS far left)
    tabs_config.append((":material/dashboard: Home", home_callback))
    
    # Tab 2: Orders/Core Function
    if orders_callback:
        tabs_config.append((":material/shopping_cart: Orders", orders_callback))
    
    # Tab 3: Create (Center position - optional)
    if create_callback:
        tabs_config.append((":material/add_circle: Create", create_callback))
    
    # Tab 4: Analytics
    if analytics_callback:
        tabs_config.append((":material/analytics: Analytics", analytics_callback))
    
    # Tab 5: Profile (ALWAYS far right)
    if profile_callback:
        tabs_config.append((":material/person: Profile", profile_callback))
    
    # Enforce 5-tab maximum
    if len(tabs_config) > 5:
        # Keep first 4 + Profile (always keep Profile on right)
        tabs_config = tabs_config[:4] + [tabs_config[-1]]
    
    # Render tabs
    tab_labels = [label for label, _ in tabs_config]
    tab_callbacks = [cb for _, cb in tabs_config]
    
    rendered_tabs = st.tabs(tab_labels)
    
    for tab, callback in zip(rendered_tabs, tab_callbacks):
        with tab:
            callback()


def get_consolidated_nav_structure() -> dict:
    """Return recommended navigation structure based on DEEN OPS functionality.
    
    This consolidates the current 11 tabs into Jakob's Law compliant 5-tab structure.
    """
    return {
        "Home": {
            "icon": ":material/dashboard:",
            "includes": [
                "Live Dashboard",
                "Real-time metrics",
                "Quick status overview"
            ],
            "priority": 1  # Far left
        },
        "Orders": {
            "icon": ":material/shopping_cart:",
            "includes": [
                "Order Tracking",
                "Product Listing", 
                "Pathao Processor",
                "Delivery Data Parser"
            ],
            "priority": 2
        },
        "Create": {
            "icon": ":material/add_circle:",
            "includes": [
                "Sales Data Ingestion",
                "Manual order entry",
                "Bulk operations"
            ],
            "priority": 3,  # Center
            "optional": True
        },
        "Analytics": {
            "icon": ":material/analytics:",
            "includes": [
                "Current Stock Analytics",
                "Inventory Distribution",
                "Return Analytics"
            ],
            "priority": 4
        },
        "Profile": {
            "icon": ":material/person:",
            "includes": [
                "Settings",
                "User preferences",
                "System logs",
                "WhatsApp Messaging config"
            ],
            "priority": 5  # Far right
        }
    }


def migrate_settings_to_profile() -> None:
    """Helper to move Settings from main navigation to Profile section.
    
    According to Jakob's Law, Settings should NEVER be in bottom/main navigation.
    It should be accessible from:
    - Top-right corner of header
    - Profile dropdown/menu
    """
    # Mark settings as migrated
    st.session_state["_settings_migrated"] = True


def is_jakobs_compliant(nav_items: list[str]) -> tuple[bool, list[str]]:
    """Check if navigation structure complies with Jakob's Law.
    
    Returns:
        Tuple of (is_compliant, list_of_violations)
    """
    violations = []
    
    # Rule 1: Maximum 5 tabs
    if len(nav_items) > 5:
        violations.append(f"Too many tabs: {len(nav_items)} (max 5)")
    
    # Rule 2: Home on far left
    if nav_items and "Home" not in nav_items[0] and "Dashboard" not in nav_items[0]:
        violations.append("Home/Dashboard should be first (far left)")
    
    # Rule 3: Profile on far right
    if nav_items and "Profile" not in nav_items[-1] and "Settings" not in nav_items[-1]:
        violations.append("Profile/Settings should be last (far right)")
    
    # Rule 4: No Settings in main nav (should be in Profile)
    settings_in_nav = [item for item in nav_items if "Settings" in item]
    if settings_in_nav and len(nav_items) > 1:
        violations.append("Settings should be inside Profile, not separate tab")
    
    return len(violations) == 0, violations
