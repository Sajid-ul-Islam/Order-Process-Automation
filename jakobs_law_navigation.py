"""
Jakob's Law Navigation Component
Implements UX navigation principles based on Jakob's Law
"""

import streamlit as st
from typing import Callable, Optional


class JakobsLawNavigation:
    """
    Navigation component following Jakob's Law principles:
    1. Maximum 5 tabs
    2. Home on far left
    3. Profile on far right
    4. Create button in middle (if applicable)
    5. Standard gestures (back on left swipe, pull to refresh)
    """
    
    def __init__(self, app_name: str = "My App"):
        self.app_name = app_name
        self.current_page = st.session_state.get('current_page', 'Home')
        self.tabs = []
        
    def setup_navigation(self, 
                         home_callback: Callable,
                         profile_callback: Callable,
                         search_callback: Optional[Callable] = None,
                         create_callback: Optional[Callable] = None,
                         notifications_callback: Optional[Callable] = None):
        """
        Setup navigation with Jakob's Law compliance
        
        Args:
            home_callback: Function for Home page (far left)
            profile_callback: Function for Profile page (far right)
            search_callback: Function for Search/Explore page
            create_callback: Function for Create action (middle)
            notifications_callback: Function for Notifications/Messages
        """
        # Initialize session state
        if 'current_page' not in st.session_state:
            st.session_state.current_page = 'Home'
        if 'refresh_triggered' not in st.session_state:
            st.session_state.refresh_triggered = False
            
        # Render top bar with standard gestures
        self._render_top_bar()
        
        # Render main content area
        self._render_content(
            home_callback,
            search_callback,
            create_callback,
            notifications_callback,
            profile_callback
        )
        
        # Render bottom navigation
        self._render_bottom_nav(
            home_callback,
            profile_callback,
            search_callback,
            create_callback,
            notifications_callback
        )
    
    def _render_top_bar(self):
        """Render top navigation bar with back gesture and settings"""
        col1, col2, col3 = st.columns([1, 3, 1])
        
        with col1:
            # Back button (standard left-edge gesture)
            if st.session_state.current_page != 'Home':
                if st.button("←", key="back_btn", use_container_width=True):
                    st.session_state.current_page = 'Home'
                    st.rerun()
            else:
                st.write("")  # Placeholder
        
        with col2:
            # App name or current page title
            st.markdown(f"**{self.app_name}**")
        
        with col3:
            # Settings in top right (not in bottom nav)
            if st.button("⚙️", key="settings_btn", use_container_width=True):
                st.session_state.current_page = 'Settings'
                st.rerun()
    
    def _render_bottom_nav(self,
                          home_callback: Callable,
                          profile_callback: Callable,
                          search_callback: Optional[Callable] = None,
                          create_callback: Optional[Callable] = None,
                          notifications_callback: Optional[Callable] = None):
        """Render bottom navigation following Jakob's Law"""
        
        # Determine which tabs to show (max 5)
        nav_items = []
        
        # 1. Home (far left)
        nav_items.append({
            'name': 'Home',
            'icon': '🏠',
            'callback': home_callback
        })
        
        # 2. Search/Explore (second from left)
        if search_callback:
            nav_items.append({
                'name': 'Search',
                'icon': '🔍',
                'callback': search_callback
            })
        
        # 3. Create (middle) - only if provided
        if create_callback:
            nav_items.append({
                'name': 'Create',
                'icon': '➕',
                'callback': create_callback,
                'is_primary': True
            })
        
        # 4. Notifications (second from right)
        if notifications_callback:
            nav_items.append({
                'name': 'Inbox',
                'icon': '💬',
                'callback': notifications_callback
            })
        
        # 5. Profile (far right)
        nav_items.append({
            'name': 'Profile',
            'icon': '👤',
            'callback': profile_callback
        })
        
        # Ensure max 5 tabs
        nav_items = nav_items[:5]
        
        # Render navigation
        st.markdown("---")
        cols = st.columns(len(nav_items))
        
        for i, item in enumerate(nav_items):
            with cols[i]:
                is_active = st.session_state.current_page == item['name']
                
                # Style active/inactive states
                if item.get('is_primary'):
                    # Primary create button in middle
                    if st.button(f"{item['icon']} {item['name']}", 
                               key=f"nav_{item['name']}",
                               use_container_width=True):
                        st.session_state.current_page = item['name']
                        st.rerun()
                else:
                    # Regular nav items
                    button_style = "**" if is_active else ""
                    label = f"{button_style}{item['icon']} {item['name']}{button_style}"
                    
                    if st.button(label, 
                               key=f"nav_{item['name']}",
                               use_container_width=True):
                        st.session_state.current_page = item['name']
                        st.rerun()
    
    def _render_content(self,
                       home_callback: Callable,
                       profile_callback: Callable,
                       search_callback: Optional[Callable] = None,
                       create_callback: Optional[Callable] = None,
                       notifications_callback: Optional[Callable] = None):
        """Render main content based on current page"""
        
        # Pull-to-refresh simulation
        if st.button("🔄 Refresh", key="refresh_btn"):
            st.session_state.refresh_triggered = True
        
        page = st.session_state.current_page
        
        if page == 'Home':
            home_callback()
        elif page == 'Search' and search_callback:
            search_callback()
        elif page == 'Create' and create_callback:
            create_callback()
        elif page == 'Inbox' and notifications_callback:
            notifications_callback()
        elif page == 'Profile':
            profile_callback()
        elif page == 'Settings':
            self._render_settings()
    
    def _render_settings(self):
        """Render settings page (accessed from top-right, not bottom nav)"""
        st.header("Settings")
        st.write("Account settings, preferences, and more.")
        
        st.subheader("Account")
        st.write("- Change Password")
        st.write("- Privacy Settings")
        st.write("- Notification Preferences")
        
        st.subheader("App")
        st.write("- Theme")
        st.write("- Language")
        st.write("- Help & Support")


# Example usage callbacks
def home_page():
    st.header("🏠 Home")
    st.write("Welcome to your personalized feed!")
    st.write("This is where users spend most of their time.")
    
    # Sample content
    st.markdown("---")
    st.write("📱 **Recent Activity**")
    st.write("- Friend posted a new photo")
    st.write("- You have 3 new notifications")
    st.write("- Trending topics in your area")


def search_page():
    st.header("🔍 Search")
    st.write("Discover new content and people")
    
    search_query = st.text_input("Search...", key="search_input")
    if search_query:
        st.write(f"Searching for: {search_query}")


def create_page():
    st.header("➕ Create")
    st.write("Share something new with your community")
    
    content = st.text_area("What's on your mind?", height=100)
    if st.button("Post"):
        st.success("Posted successfully!")


def inbox_page():
    st.header("💬 Inbox")
    st.write("Your messages and notifications")
    
    st.write("📨 **Messages**")
    st.write("- Alex: Hey, how are you?")
    st.write("- Sarah: Check out this link!")
    
    st.write("🔔 **Notifications**")
    st.write("- John liked your post")
    st.write("- 5 new followers")


def profile_page():
    st.header("👤 Profile")
    st.write("Your personal space")
    
    st.write("**Username**: @johndoe")
    st.write("**Followers**: 1,234")
    st.write("**Following**: 567")
    
    st.markdown("---")
    st.write("📸 **Your Posts**")
    st.write("- Post 1: Vacation photos")
    st.write("- Post 2: Project update")
    st.write("- Post 3: Random thoughts")


# Main app
def main():
    st.set_page_config(page_title="Jakob's Law Demo", layout="centered")
    
    st.title("Jakob's Law Navigation Blueprint")
    st.markdown("""
    This demo implements UX navigation principles based on Jakob's Law:
    - ✅ Home tab on far left
    - ✅ Profile tab on far right  
    - ✅ Create button in middle
    - ✅ Max 5 tabs
    - ✅ Settings in top-right (not bottom nav)
    - ✅ Back gesture on left edge
    """)
    
    st.markdown("---")
    
    # Initialize navigation
    nav = JakobsLawNavigation(app_name="SocialApp")
    
    # Setup navigation with all callbacks
    nav.setup_navigation(
        home_callback=home_page,
        profile_callback=profile_page,
        search_callback=search_page,
        create_callback=create_page,
        notifications_callback=inbox_page
    )


if __name__ == "__main__":
    main()
