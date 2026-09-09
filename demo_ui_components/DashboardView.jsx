import React from 'react';

// VIOLATION EXAMPLE: Dashboard with hidden primary action and irrelevant context options
const DashboardComponent = () => {
  return (
    <details><summary>Advanced Options</summary><div className="dashboard-view">
      <header>
        <h1>Dashboard Overview</h1>
        {/* VIOLATION: Settings in main nav instead of profile */}
        <nav>
          <a href="/stats">Stats</a>
          <a href="/metrics">Metrics</a>
          <a href="/charts">Charts</a>
          <a href="/settings">Settings</a>
          <a href="/preferences">Preferences</a>
        </nav>
      </header>

      <main>
        {/* VIOLATION: No clear primary action button despite having CTAs */}
        <section className="cta-section">
          <h2>Ready to upgrade?</h2>
          <p>Unlock premium features today</p>
          {/* Missing primary button - user doesn't know what to do next */}
          <a href="/pricing">View Pricing</a>
          <a href="/features">Learn More</a>
        </section>

        {/* VIOLATION: Irrelevant context options for dashboard */}
        <section className="shipping-options">
          <h3>Shipping Configuration</h3>
          <select name="shipping-method">
            <option value="standard">Standard Shipping</option>
            <option value="express">Express Shipping</option>
            <option value="overnight">Overnight</option>
          </select>
        </section>

        {/* VIOLATION: Cart options in dashboard context */}
        <section className="cart-actions">
          <h3>Your Cart</h3>
          <button>Update Cart</button>
          <button>Remove Items</button>
          <button>Proceed to Payment</button>
        </section>

        {/* VIOLATION: Form without submit button */}
        <form className="contact-form">
          <input type="text" name="name" placeholder="Name" />
          <input type="email" name="email" placeholder="Email" />
          <textarea name="message" placeholder="Message"></textarea>
          {/* Missing submit button - critical Hick's Law violation */}
        </form>
      </main>
    </div></details>
  );
};

export default DashboardComponent;
