# Jakob's Law Navigation Blueprint

A Streamlit-based navigation component that implements UX best practices based on **Jakob's Law**.

## What is Jakob's Law?

Jakob's Law states that users spend most of their time in other apps, so they expect your app to work the same way as the apps they already know. This component follows navigation patterns established by successful apps like Instagram, TikTok, and YouTube.

## Key Principles Implemented

### 1. **Maximum 5 Tabs**
Bottom navigation is limited to 5 tabs maximum to avoid overwhelming users.

### 2. **Home on Far Left**
The Home tab is always positioned at the far left of the navigation bar.

### 3. **Profile on Far Right**
The Profile tab is always positioned at the far right of the navigation bar.

### 4. **Create Button in Middle**
If your app allows user creation, the Create action is placed in the center position.

### 5. **Standard Gestures**
- **Back gesture**: Left-edge back button appears when not on Home
- **Pull to refresh**: Refresh button available on all pages

### 6. **Settings Placement**
Settings are placed in the **top-right corner**, NOT in the bottom navigation. This reserves bottom nav for core actions only.

## Usage

```python
from jakobs_law_navigation import JakobsLawNavigation

# Define your page callbacks
def home_page():
    st.header("🏠 Home")
    # Your home page content

def profile_page():
    st.header("👤 Profile")
    # Your profile page content

def search_page():
    st.header("🔍 Search")
    # Your search page content

def create_page():
    st.header("➕ Create")
    # Your create content

def inbox_page():
    st.header("💬 Inbox")
    # Your inbox/messages content

# Initialize and setup navigation
nav = JakobsLawNavigation(app_name="YourApp")
nav.setup_navigation(
    home_callback=home_page,
    profile_callback=profile_page,
    search_callback=search_page,      # Optional
    create_callback=create_page,       # Optional
    notifications_callback=inbox_page  # Optional
)
```

## Required Parameters

- `home_callback`: Function for Home page (always displayed, far left)
- `profile_callback`: Function for Profile page (always displayed, far right)

## Optional Parameters

- `search_callback`: Function for Search/Explore page
- `create_callback`: Function for Create action (placed in middle if provided)
- `notifications_callback`: Function for Inbox/Messages page

## Architecture

### Top Bar
- **Left**: Back button (←) when not on Home page
- **Center**: App name
- **Right**: Settings button (⚙️)

### Bottom Navigation
Ordered from left to right:
1. 🏠 Home (required)
2. 🔍 Search (optional)
3. ➕ Create (optional, centered, highlighted as primary)
4. 💬 Inbox (optional)
5. 👤 Profile (required)

### Content Area
- Pull-to-refresh button
- Dynamic content based on current page
- Settings page (accessed via top-right gear icon)

## Common Pitfalls Avoided

❌ **Don't put Settings in bottom navigation**  
✅ Settings are in the top-right corner

❌ **Don't exceed 5 tabs**  
✅ Navigation is limited to 5 items maximum

❌ **Don't place Home anywhere but far left**  
✅ Home is always first

❌ **Don't place Profile anywhere but far right**  
✅ Profile is always last

❌ **Don't hide Create in a submenu**  
✅ Create is prominently displayed in the middle

## Why This Matters

When Snapchat redesigned their app in 2018 and broke familiar navigation patterns, **1.2 million people signed a petition** demanding they reverse the changes. Following Jakob's Law prevents this kind of user backlash by meeting expectations.

## Running the Demo

```bash
streamlit run jakobs_law_navigation.py
```

## Files

- `jakobs_law_navigation.py` - Main navigation component with demo
- `JAKOBS_LAW_README.md` - This documentation file

## References

[1] Jakob's Law UX principles - Based on research from UX experts with 79+ patents
