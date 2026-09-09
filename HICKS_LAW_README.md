# Hick's Law UX Audit & Refactoring System

## Overview

This system audits UI codebases against **Hick's Law** principles and automatically refactors components to reduce decision friction. 

**Hick's Law**: *The more choices you give a user, the longer it takes them to make a decision. More decisions lead to increased friction, which ultimately hurts user retention.*

### Core Philosophy

> One of the biggest mistakes in app design is attempting to show the user everything the product can do at once, which makes the app feel overly complicated. While the application might be incredibly complex below the surface, the user's next action should always feel completely obvious.

**Benchmarks for highly optimized apps:**
- **Uber**: Focuses solely on picking a destination
- **Duolingo**: Wants you to start the next lesson  
- **TikTok**: Just wants you to keep watching

---

## The 5 Rules of Hick's Law

1. **Single Primary Action**: Every screen must have one obvious primary action
2. **Visual Hierarchy**: The primary button must look significantly more important than everything else
3. **Progressive Disclosure**: Hide advanced options until the user actually needs them
4. **Button Grouping**: Multiple buttons placed together must not look equally important
5. **Contextual Relevance**: If a setting/option isn't relevant to current context, don't show it

---

## Installation

No external dependencies required. Uses Python 3.7+ standard library only.

```bash
# Clone or copy hicks_law_audit.py to your project
python hicks_law_audit.py /path/to/your/codebase
```

---

## Usage

### Command Line

```bash
# Run audit only
python hicks_law_audit.py ./src/components

# Run audit with auto-refactoring
python hicks_law_audit.py ./src/components --refactor
```

### Programmatic API

```python
from hicks_law_audit import HicksLawAuditor, HicksLawRefactorer, run_audit_and_refactor

# Option 1: Quick audit and report
report = run_audit_and_refactor('./src/components', auto_refactor=False)
print(report)

# Option 2: Detailed control
auditor = HicksLawAuditor('./src/components')
audit_report = auditor.audit()

# Generate Markdown report
markdown_report = audit_report.to_markdown()

# Option 3: Auto-refactor specific files
refactorer = HicksLawRefactorer()
for violation in audit_report.violations:
    refactorer.refactor_file(Path(violation.file_path), [violation])

print(refactorer.get_refactoring_summary())
```

---

## Features

### Audit Capabilities

The system scans for these violation types:

| Violation Type | Severity | Description |
|---------------|----------|-------------|
| `MULTIPLE_PRIMARY_ACTIONS` | HIGH | Multiple primary buttons on same screen |
| `EQUAL_BUTTON_HIERARCHY` | MEDIUM | Adjacent buttons with equal visual weight |
| `NO_VISUAL_HIERARCHY` | MEDIUM | Primary button lacks distinctive styling |
| `PREMATURE_ADVANCED_OPTIONS` | MEDIUM | Advanced settings visible by default |
| `IRRELEVANT_CONTEXT_OPTIONS` | LOW | Options unrelated to current task |
| `CLUTTERED_MENU` | HIGH | Menu with >8-10 items |
| `HIDDEN_PRIMARY_ACTION` | CRITICAL | Interactive screen without clear CTA |

### Severity Levels

- **CRITICAL**: Directly blocks user action
- **HIGH**: Significantly increases decision time
- **MEDIUM**: Creates noticeable friction
- **LOW**: Minor optimization opportunity

### Auto-Refactoring

The system can automatically fix common violations:

1. **Demote Extra Primary Buttons**: Keeps first primary button, converts others to secondary
2. **Establish Button Hierarchy**: Makes first button primary, others secondary
3. **Hide Advanced Options**: Wraps in `<details>/<summary>` for progressive disclosure
4. **Simplify Menus**: Groups excessive menu items with visual separators

---

## Example Output

### Sample Audit Report

```markdown
# Hick's Law UX Audit Report

**Files Scanned:** 23
**Total Violations:** 8

## Summary

Significant UX friction identified. 3 high-severity violations may be causing user hesitation. Prioritize fixing these to streamline user flows.

## Violations by Severity

- **CRITICAL:** 1
- **HIGH:** 3
- **MEDIUM:** 3
- **LOW:** 1

## Priority Actions

1. Fix all CRITICAL violations immediately - these block user progress
2. Address HIGH severity violations within current sprint
3. Consolidate primary buttons: one screen = one primary action
4. Simplify navigation: group menu items, aim for 5±2 options

## Detailed Findings

### Multiple Primary Actions

**File:** `src/components/CheckoutPage.jsx` (line 45)
**Severity:** HIGH

**Issue:** Found 3 primary buttons on same screen. Hick's Law states multiple primary actions increase decision time.

**Suggestion:** Demote all but one primary action to secondary or tertiary style. The most important user goal should have the only primary button.
```

---

## Architecture

### Classes

#### `HicksLawAuditor`
Main audit engine that scans codebases for violations.

**Key Methods:**
- `audit()` → `AuditReport`: Run complete audit
- `_scan_file(file_path)`: Scan individual file
- `_check_*()` methods: Specific violation checks

#### `AuditReport`
Container for audit results with reporting capabilities.

**Key Methods:**
- `to_markdown()` → `str`: Generate Markdown report
- `to_dict()` → `dict`: Export as dictionary

#### `HicksLawRefactorer`
Applies automatic fixes to violated components.

**Key Methods:**
- `refactor_file(file_path, violations)` → `str`: Fix violations in file
- `get_refactoring_summary()` → `str`: Summary of changes

#### `UXViolation`
Data class representing a single violation.

**Properties:**
- `violation_type`: Type of violation
- `severity`: How serious it is
- `file_path`, `line_number`: Location
- `description`, `suggestion`: Human-readable guidance
- `code_snippet`: Relevant code excerpt

---

## Common Pitfalls (Lessons Learned)

### ❌ What NOT to Do

1. **Show Everything at Once**
   ```html
   <!-- Bad: Overwhelming checkout page -->
   <button class="btn-primary">Complete Order</button>
   <button class="btn-primary">Save for Later</button>
   <button class="btn-primary">Continue Shopping</button>
   <div class="advanced-settings">
     <input name="gift-wrap" />
     <input name="insurance" />
     <input name="custom-message" />
   </div>
   ```

2. **Equal Button Hierarchy**
   ```html
   <!-- Bad: All buttons look the same -->
   <div class="button-group">
     <button class="btn">Cancel</button>
     <button class="btn">Save Draft</button>
     <button class="btn">Submit</button>
   </div>
   ```

3. **Cluttered Navigation**
   ```html
   <!-- Bad: 15 menu items -->
   <nav>
     <a href="/home">Home</a>
     <a href="/profile">Profile</a>
     <a href="/settings">Settings</a>
     <a href="/notifications">Notifications</a>
     <a href="/messages">Messages</a>
     <a href="/friends">Friends</a>
     <a href="/photos">Photos</a>
     <a href="/videos">Videos</a>
     <a href="/music">Music</a>
     <a href="/events">Events</a>
     <a href="/groups">Groups</a>
     <a href="/pages">Pages</a>
     <a href="/marketplace">Marketplace</a>
     <a href="/gaming">Gaming</a>
     <a href="/jobs">Jobs</a>
   </nav>
   ```

### ✅ What TO Do

1. **Single Primary Action**
   ```html
   <!-- Good: Clear primary action -->
   <button class="btn-primary btn-lg">Complete Order</button>
   <button class="btn-secondary">Save for Later</button>
   <a href="#" class="btn-link">Continue Shopping</a>
   ```

2. **Clear Visual Hierarchy**
   ```html
   <!-- Good: Obvious hierarchy -->
   <div class="button-group">
     <button class="btn btn-secondary">Cancel</button>
     <button class="btn btn-outline">Save Draft</button>
     <button class="btn btn-primary btn-lg">Submit Application</button>
   </div>
   ```

3. **Progressive Disclosure**
   ```html
   <!-- Good: Advanced options hidden -->
   <button class="btn btn-link">More Options ▼</button>
   <details>
     <summary>Advanced Settings</summary>
     <div class="advanced-settings">
       <!-- Hidden by default -->
     </div>
   </details>
   ```

4. **Contextual Menus (5±2 Rule)**
   ```html
   <!-- Good: Grouped navigation -->
   <nav>
     <a href="/home">Home</a>
     <a href="/explore">Explore</a>
     <button class="create-btn">+</button>
     <a href="/notifications">Alerts</a>
     <a href="/profile">Profile</a>
   </nav>
   ```

---

## Integration Examples

### React Component Audit

```python
auditor = HicksLawAuditor('./src/components')
report = auditor.audit()

# Filter for React-specific issues
react_violations = [v for v in report.violations 
                   if v.file_path.endswith('.jsx') or v.file_path.endswith('.tsx')]

print(f"Found {len(react_violations)} React component issues")
```

### CI/CD Integration

```yaml
# .github/workflows/ux-audit.yml
name: UX Audit

on: [pull_request]

jobs:
  hicks-law-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Run Hick's Law Audit
        run: python hicks_law_audit.py ./src --refactor
      
      - name: Fail on Critical Violations
        run: |
          python -c "
          from hicks_law_audit import HicksLawAuditor
          auditor = HicksLawAuditor('./src')
          report = auditor.audit()
          critical = report.violations_by_severity.get('critical', 0)
          exit(1) if critical > 0 else exit(0)
          "
```

### Streamlit Dashboard

```python
import streamlit as st
from hicks_law_audit import HicksLawAuditor

st.title("🔍 Hick's Law UX Auditor")

codebase_path = st.text_input("Codebase Path", "./src")

if st.button("Run Audit"):
    auditor = HicksLawAuditor(codebase_path)
    report = auditor.audit()
    
    st.metric("Files Scanned", report.total_files_scanned)
    st.metric("Total Violations", report.total_violations)
    
    st.subheader("By Severity")
    st.bar_chart(report.violations_by_severity)
    
    st.markdown(report.to_markdown())
```

---

## Best Practices

### When to Run Audits

1. **Before Launch**: Audit all user-facing screens
2. **After Major Features**: Check new components
3. **Quarterly**: Regular UX health check
4. **When Metrics Drop**: If conversion/retention drops, audit for friction

### Interpretation Guidelines

- **0-5 violations**: Excellent UX, minor optimizations possible
- **6-15 violations**: Moderate friction, prioritize HIGH/CRITICAL
- **16+ violations**: Significant redesign needed, focus on primary flows first

### Refactoring Strategy

1. **Fix CRITICAL first**: These block user progress
2. **Address HIGH severity**: These cause hesitation
3. **Batch MEDIUM fixes**: Group by component/screen
4. **Iterate on LOW**: Continuous improvement

---

## Case Studies

### Snapchat Redesign Failure (2018)

**What happened**: Snapchat redesigned familiar navigation, moving friends' stories and creator content to separate sections.

**Result**: 1.2 million people signed a petition to reverse the redesign. Stock dropped 22%.

**Hick's Law violation**: Forced users to relearn basic navigation, adding decision friction to core features.

**Lesson**: Don't reinvent established patterns. Users expect apps to work like other apps they use daily.

### Duolingo Success Story

**Approach**: Every screen has ONE obvious action (start lesson, answer question, continue).

**Result**: Industry-leading retention rates, 50M+ DAU.

**Hick's Law applied**: Progressive disclosure, clear visual hierarchy, contextual actions only.

---

## Limitations

1. **Static Analysis Only**: Cannot detect runtime/dynamic UI issues
2. **Heuristic-Based**: May produce false positives/negatives
3. **HTML-Focused**: Best results with HTML/JSX, limited support for native mobile
4. **No Semantic Understanding**: Cannot judge if button labels are clear

## Future Enhancements

- [ ] Machine learning model for better violation detection
- [ ] Support for React Native, Flutter, SwiftUI
- [ ] Integration with Figma/Sketch for design-phase audits
- [ ] A/B testing recommendations based on violations
- [ ] Automated accessibility compliance checks

---

## Contributing

Contributions welcome! Areas needing help:

1. Additional violation pattern detection
2. More refactoring strategies
3. Support for additional frameworks
4. Better semantic analysis

---

## License

MIT License - See LICENSE file for details.

---

## References

[1] Hick, W. E. (1952). "On the rate of gain of information". Quarterly Journal of Experimental Psychology.

[2] Nielsen Norman Group. "Hick's Law and Simple Web Design."

[3] Hyman, R. (1953). "Stimulus information as a determinant of reaction time". Journal of Experimental Psychology.

---

**Remember**: The goal isn't to eliminate all choices—it's to present the RIGHT choice at the RIGHT time in the RIGHT way. Make the user's next action obvious, and they'll keep coming back.
