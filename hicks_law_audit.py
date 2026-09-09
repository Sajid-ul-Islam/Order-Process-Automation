"""
Hick's Law UI/UX Audit and Refactoring System

This module provides tools to audit UI codebases against Hick's Law principles
and automatically refactor components to reduce decision friction.

Hick's Law: The more choices you give a user, the longer it takes them to 
make a decision. More decisions lead to increased friction, hurting retention.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Tuple
from pathlib import Path


class ViolationSeverity(Enum):
    """Severity levels for Hick's Law violations."""
    CRITICAL = "critical"  # Directly blocks user action
    HIGH = "high"  # Significantly increases decision time
    MEDIUM = "medium"  # Creates noticeable friction
    LOW = "low"  # Minor optimization opportunity


class ViolationType(Enum):
    """Types of Hick's Law violations."""
    MULTIPLE_PRIMARY_ACTIONS = "multiple_primary_actions"
    EQUAL_BUTTON_HIERARCHY = "equal_button_hierarchy"
    NO_VISUAL_HIERARCHY = "no_visual_hierarchy"
    PREMATURE_ADVANCED_OPTIONS = "premature_advanced_options"
    IRRELEVANT_CONTEXT_OPTIONS = "irrelevant_context_options"
    CLUTTERED_MENU = "cluttered_menu"
    HIDDEN_PRIMARY_ACTION = "hidden_primary_action"
    COMPETING_CALLS_TO_ACTION = "competing_calls_to_action"


@dataclass
class UXViolation:
    """Represents a single Hick's Law violation found during audit."""
    violation_type: ViolationType
    severity: ViolationSeverity
    file_path: str
    line_number: int
    description: str
    suggestion: str
    code_snippet: str = ""
    
    def to_dict(self) -> dict:
        return {
            "type": self.violation_type.value,
            "severity": self.severity.value,
            "file": self.file_path,
            "line": self.line_number,
            "description": self.description,
            "suggestion": self.suggestion,
            "snippet": self.code_snippet
        }


@dataclass
class AuditReport:
    """Complete audit report for a codebase."""
    total_files_scanned: int
    total_violations: int
    violations_by_severity: Dict[ViolationSeverity, int]
    violations_by_type: Dict[ViolationType, int]
    violations: List[UXViolation]
    summary: str
    priority_actions: List[str]
    
    def to_markdown(self) -> str:
        """Generate a Markdown report."""
        lines = [
            "# Hick's Law UX Audit Report\n",
            f"**Files Scanned:** {self.total_files_scanned}\n",
            f"**Total Violations:** {self.total_violations}\n",
            "\n## Summary\n",
            f"{self.summary}\n",
            "\n## Violations by Severity\n",
        ]
        
        for severity in ViolationSeverity:
            count = self.violations_by_severity.get(severity, 0)
            if count > 0:
                lines.append(f"- **{severity.value.upper()}:** {count}\n")
        
        lines.append("\n## Violations by Type\n")
        for vtype, count in sorted(self.violations_by_type.items(), 
                                   key=lambda x: x[1], reverse=True):
            lines.append(f"- **{vtype.value.replace('_', ' ').title()}:** {count}\n")
        
        if self.priority_actions:
            lines.append("\n## Priority Actions\n")
            for i, action in enumerate(self.priority_actions, 1):
                lines.append(f"{i}. {action}\n")
        
        lines.append("\n## Detailed Findings\n")
        for violation in self.violations:
            lines.extend([
                f"\n### {violation.violation_type.value.replace('_', ' ').title()}\n",
                f"**File:** `{violation.file_path}` (line {violation.line_number})\n",
                f"**Severity:** {violation.severity.value.upper()}\n",
                f"\n**Issue:** {violation.description}\n",
                f"\n**Suggestion:** {violation.suggestion}\n",
            ])
            if violation.code_snippet:
                lines.append(f"\n```code\n{violation.code_snippet}\n```\n")
        
        return "".join(lines)


class HicksLawAuditor:
    """
    Audits UI codebases against Hick's Law principles.
    
    Core Philosophy: While the application might be complex below the surface,
    the user's next action should always feel completely obvious.
    """
    
    # Patterns that indicate potential violations
    PRIMARY_BUTTON_PATTERNS = [
        r'<button[^>]*class="[^"]*btn-primary[^"]*"[^>]*>',
        r'<Button[^>]*variant=["\']primary["\'][^>]*>',
        r'<button[^>]*class="[^"]*primary[^"]*"[^>]*>',
        r'role=["\']button["\'][^>]*class=["\'][^"\']*primary',
        r'<ion-button[^>]*color=["\']primary["\'][^>]*>',
        r'<Button[^>]*type=["\']submit["\'][^>]*>',
    ]
    
    SECONDARY_BUTTON_PATTERNS = [
        r'<button[^>]*class="[^"]*btn-secondary[^"]*"[^>]*>',
        r'<Button[^>]*variant=["\'](secondary|outline|ghost)["\'][^>]*>',
        r'<button[^>]*class="[^"]*secondary[^"]*"[^>]*>',
    ]
    
    ADVANCED_OPTION_PATTERNS = [
        r'advanced',
        r'settings',
        r'preferences',
        r'configuration',
        r'custom',
        r'expert',
        r'detailed',
        r'more options',
        r'show more',
    ]
    
    MENU_CLUTTER_INDICATORS = [
        r'<ul[^>]*>(?:\s*<li[^>]*>){10,}',  # 10+ menu items
        r'<nav[^>]*>(?:\s*<a[^>]*>){8,}',   # 8+ nav links
        r'<menu[^>]*>(?:\s*<item[^>]*>){12,}',  # 12+ menu items
    ]
    
    def __init__(self, codebase_path: str):
        self.codebase_path = Path(codebase_path)
        self.violations: List[UXViolation] = []
        self.files_scanned = 0
        
    def audit(self) -> AuditReport:
        """Run complete audit on the codebase."""
        self.violations = []
        self.files_scanned = 0
        
        # Scan relevant UI files
        ui_extensions = ['.html', '.jsx', '.tsx', '.vue', '.svelte', '.py']
        
        for ext in ui_extensions:
            for file_path in self.codebase_path.rglob(f'*{ext}'):
                if self._is_ui_file(file_path):
                    self.files_scanned += 1
                    self._scan_file(file_path)
        
        # Generate report
        return self._generate_report()
    
    def _is_ui_file(self, file_path: Path) -> bool:
        """Check if file is likely a UI component."""
        ui_keywords = ['component', 'view', 'page', 'screen', 'ui', 'widget']
        return any(keyword in file_path.name.lower() for keyword in ui_keywords)
    
    def _scan_file(self, file_path: Path) -> None:
        """Scan a single file for violations."""
        try:
            content = file_path.read_text(encoding='utf-8')
            lines = content.split('\n')
        except Exception:
            return
        
        # Check for each violation type
        self._check_multiple_primary_actions(file_path, content, lines)
        self._check_equal_button_hierarchy(file_path, content, lines)
        self._check_no_visual_hierarchy(file_path, content, lines)
        self._check_premature_advanced_options(file_path, content, lines)
        self._check_irrelevant_context_options(file_path, content, lines)
        self._check_cluttered_menu(file_path, content, lines)
        self._check_hidden_primary_action(file_path, content, lines)
    
    def _check_multiple_primary_actions(self, file_path: Path, 
                                        content: str, lines: List[str]) -> None:
        """Rule 1: Ensure every screen has one obvious primary action."""
        primary_buttons = []
        
        for pattern in self.PRIMARY_BUTTON_PATTERNS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count('\n') + 1
                primary_buttons.append((line_num, match.group()))
        
        if len(primary_buttons) > 1:
            self.violations.append(UXViolation(
                violation_type=ViolationType.MULTIPLE_PRIMARY_ACTIONS,
                severity=ViolationSeverity.HIGH,
                file_path=str(file_path),
                line_number=primary_buttons[0][0],
                description=f"Found {len(primary_buttons)} primary buttons on same screen. "
                           f"Hick's Law states multiple primary actions increase decision time.",
                suggestion="Demote all but one primary action to secondary or tertiary style. "
                          "The most important user goal should have the only primary button.",
                code_snippet="\n".join([pb[1] for pb in primary_buttons[:3]])
            ))
    
    def _check_equal_button_hierarchy(self, file_path: Path,
                                      content: str, lines: List[str]) -> None:
        """Rule 4: Verify adjacent buttons don't look equally important."""
        # Look for button groups with similar styling
        button_group_pattern = r'<div[^>]*class="[^"]*button-group[^"]*"[^>]*>'
        
        for match in re.finditer(button_group_pattern, content, re.IGNORECASE):
            line_num = content[:match.start()].count('\n') + 1
            
            # Extract the button group section
            start = match.end()
            end = content.find('</div>', start)
            if end == -1:
                end = start + 500
            group_content = content[start:end]
            
            # Count buttons with similar classes
            btn_matches = re.findall(r'<button[^>]*class="([^"]*)"[^>]*>', 
                                    group_content, re.IGNORECASE)
            
            if len(btn_matches) >= 2:
                # Check if they have similar visual weight
                primary_count = sum(1 for cls in btn_matches 
                                  if 'primary' in cls.lower())
                if primary_count >= 2 or primary_count == 0:
                    self.violations.append(UXViolation(
                        violation_type=ViolationType.EQUAL_BUTTON_HIERARCHY,
                        severity=ViolationSeverity.MEDIUM,
                        file_path=str(file_path),
                        line_number=line_num,
                        description="Button group contains multiple buttons with equal visual weight. "
                                   "Users struggle to decide when options appear equally important.",
                        suggestion="Make one button visually dominant (primary) and others secondary. "
                                  "Use size, color, or placement to establish clear hierarchy.",
                        code_snippet=group_content[:200]
                    ))
    
    def _check_no_visual_hierarchy(self, file_path: Path,
                                   content: str, lines: List[str]) -> None:
        """Rule 2: Primary button must look significantly more important."""
        # Look for primary buttons without distinctive styling
        primary_btn_pattern = r'<button[^>]*class="[^"]*primary[^"]*"[^>]*>(.*?)</button>'
        
        for match in re.finditer(primary_btn_pattern, content, re.IGNORECASE | re.DOTALL):
            line_num = content[:match.start()].count('\n') + 1
            btn_content = match.group()
            
            # Check if button lacks visual distinction indicators
            has_size_class = re.search(r'(large|big|xl|lg)\b', btn_content, re.IGNORECASE)
            has_color_class = re.search(r'(blue|green|red|brand|accent)', btn_content, re.IGNORECASE)
            has_prominent_style = has_size_class or has_color_class
            
            if not has_prominent_style:
                self.violations.append(UXViolation(
                    violation_type=ViolationType.NO_VISUAL_HIERARCHY,
                    severity=ViolationSeverity.MEDIUM,
                    file_path=str(file_path),
                    line_number=line_num,
                    description="Primary button lacks visual distinction from other elements. "
                               "Users may not immediately identify the main action.",
                    suggestion="Add distinctive sizing (e.g., 'btn-lg'), bold color, or prominent "
                              "placement to make the primary action unmistakable.",
                    code_snippet=btn_content[:150]
                ))
    
    def _check_premature_advanced_options(self, file_path: Path,
                                          content: str, lines: List[str]) -> None:
        """Rule 3: Hide advanced options until needed."""
        for pattern in self.ADVANCED_OPTION_PATTERNS:
            matches = list(re.finditer(pattern, content, re.IGNORECASE))
            
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                
                # Check if advanced options are visible by default
                context_start = max(0, match.start() - 200)
                context = content[context_start:match.end()]
                
                is_visible = not re.search(r'(hidden|collapsed|expand|show|toggle)', 
                                         context, re.IGNORECASE)
                is_on_main_screen = not re.search(r'(modal|dialog|dropdown|accordion)', 
                                                  context, re.IGNORECASE)
                
                if is_visible and is_on_main_screen:
                    self.violations.append(UXViolation(
                        violation_type=ViolationType.PREMATURE_ADVANCED_OPTIONS,
                        severity=ViolationSeverity.MEDIUM,
                        file_path=str(file_path),
                        line_number=line_num,
                        description=f"Advanced option '{pattern}' visible on main screen. "
                                   "Showing advanced options prematurely overwhelms users.",
                        suggestion="Move advanced options behind a 'More' link, accordion, modal, "
                                  "or progressive disclosure pattern. Show only when contextually relevant.",
                        code_snippet=context[-100:]
                    ))
                    break  # One violation per pattern type per file
    
    def _check_irrelevant_context_options(self, file_path: Path,
                                          content: str, lines: List[str]) -> None:
        """Rule 5: Don't show options irrelevant to current context."""
        # This requires semantic analysis - simplified heuristic approach
        context_keywords = {
            'checkout': ['cart', 'payment', 'shipping', 'order'],
            'profile': ['settings', 'avatar', 'bio', 'preferences'],
            'dashboard': ['stats', 'overview', 'metrics', 'charts'],
            'search': ['filters', 'results', 'query', 'sort'],
        }
        
        file_name = file_path.name.lower()
        current_context = None
        
        for context, keywords in context_keywords.items():
            if context in file_name:
                current_context = context
                break
        
        if current_context:
            # Look for options that don't belong in this context
            all_other_contexts = {k: v for k, v in context_keywords.items() 
                                 if k != current_context}
            
            for other_context, keywords in all_other_contexts.items():
                for keyword in keywords:
                    if re.search(rf'\b{keyword}\b', content, re.IGNORECASE):
                        line_num = content.count('\n', 0, content.find(keyword)) + 1
                        self.violations.append(UXViolation(
                            violation_type=ViolationType.IRRELEVANT_CONTEXT_OPTIONS,
                            severity=ViolationSeverity.LOW,
                            file_path=str(file_path),
                            line_number=line_num,
                            description=f"Option '{keyword}' may be irrelevant in {current_context} context. "
                                       "Irrelevant options increase cognitive load.",
                            suggestion="Remove or hide options that aren't relevant to the current user task. "
                                      "Context-aware interfaces reduce decision fatigue.",
                            code_snippet=keyword
                        ))
                        break
    
    def _check_cluttered_menu(self, file_path: Path,
                             content: str, lines: List[str]) -> None:
        """Check for menu clutter (too many options)."""
        for pattern in self.MENU_CLUTTER_INDICATORS:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                line_num = content[:match.start()].count('\n') + 1
                self.violations.append(UXViolation(
                    violation_type=ViolationType.CLUTTERED_MENU,
                    severity=ViolationSeverity.HIGH,
                    file_path=str(file_path),
                    line_number=line_num,
                    description="Menu contains too many items (>8-10). Excessive choices paralyze users.",
                    suggestion="Group related items into collapsible sections, use progressive disclosure, "
                              "or move less-frequent actions to secondary menus. Aim for 5±2 options.",
                    code_snippet=match.group()[:150]
                ))
                break
    
    def _check_hidden_primary_action(self, file_path: Path,
                                    content: str, lines: List[str]) -> None:
        """Check if primary action is hidden or unclear."""
        # Look for screens without clear primary action
        has_any_button = bool(re.search(r'<button', content, re.IGNORECASE))
        has_submit = bool(re.search(r'type=["\']submit["\']', content, re.IGNORECASE))
        has_primary = bool(re.search(r'primary', content, re.IGNORECASE))
        
        # Check if this looks like an interactive screen
        has_form = bool(re.search(r'<form', content, re.IGNORECASE))
        has_cta_section = bool(re.search(r'(cta|call-to-action|action)', content, re.IGNORECASE))
        
        if (has_form or has_cta_section) and not (has_submit or has_primary):
            self.violations.append(UXViolation(
                violation_type=ViolationType.HIDDEN_PRIMARY_ACTION,
                severity=ViolationSeverity.CRITICAL,
                file_path=str(file_path),
                line_number=1,
                description="Interactive screen lacks clear primary action button. "
                           "Users need an obvious next step.",
                suggestion="Add a clearly labeled primary button that represents the main user goal. "
                          "Make it visually prominent and place it in an expected location.",
                code_snippet="No primary action found"
            ))
    
    def _generate_report(self) -> AuditReport:
        """Generate comprehensive audit report."""
        violations_by_severity = {}
        violations_by_type = {}
        
        for violation in self.violations:
            violations_by_severity[violation.severity] = \
                violations_by_severity.get(violation.severity, 0) + 1
            violations_by_type[violation.violation_type] = \
                violations_by_type.get(violation.violation_type, 0) + 1
        
        # Generate summary
        critical_count = violations_by_severity.get(ViolationSeverity.CRITICAL, 0)
        high_count = violations_by_severity.get(ViolationSeverity.HIGH, 0)
        
        if critical_count > 0:
            summary = (f"Critical UX friction detected. {critical_count} critical and {high_count} high-"
                      f"severity violations found. Immediate refactoring recommended to reduce user "
                      f"decision fatigue and improve retention.")
        elif high_count > 0:
            summary = (f"Significant UX friction identified. {high_count} high-severity violations "
                      f"may be causing user hesitation. Prioritize fixing these to streamline user flows.")
        else:
            summary = ("Minor optimization opportunities found. While no critical issues detected, "
                      "addressing medium and low severity violations can further reduce friction.")
        
        # Generate priority actions
        priority_actions = []
        if critical_count > 0:
            priority_actions.append("Fix all CRITICAL violations immediately - these block user progress")
        if high_count > 0:
            priority_actions.append("Address HIGH severity violations within current sprint")
        
        # Add specific recommendations based on violation types
        if violations_by_type.get(ViolationType.MULTIPLE_PRIMARY_ACTIONS, 0) > 0:
            priority_actions.append("Consolidate primary buttons: one screen = one primary action")
        if violations_by_type.get(ViolationType.CLUTTERED_MENU, 0) > 0:
            priority_actions.append("Simplify navigation: group menu items, aim for 5±2 options")
        if violations_by_type.get(ViolationType.PREMATURE_ADVANCED_OPTIONS, 0) > 0:
            priority_actions.append("Implement progressive disclosure: hide advanced features until needed")
        
        return AuditReport(
            total_files_scanned=self.files_scanned,
            total_violations=len(self.violations),
            violations_by_severity=violations_by_severity,
            violations_by_type=violations_by_type,
            violations=self.violations,
            summary=summary,
            priority_actions=priority_actions
        )


class HicksLawRefactorer:
    """
    Automatically refactors UI components to comply with Hick's Law.
    
    Benchmarks: Uber (pick destination), Duolingo (start lesson), 
    TikTok (keep watching) - each screen has one obvious action.
    """
    
    def __init__(self):
        self.changes_made = []
    
    def refactor_file(self, file_path: Path, violations: List[UXViolation]) -> str:
        """Apply refactoring to fix violations in a file."""
        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            return f"Error reading file: {e}"
        
        original_content = content
        
        for violation in violations:
            if violation.violation_type == ViolationType.MULTIPLE_PRIMARY_ACTIONS:
                content = self._demote_extra_primary_buttons(content, violation)
            elif violation.violation_type == ViolationType.EQUAL_BUTTON_HIERARCHY:
                content = self._establish_button_hierarchy(content, violation)
            elif violation.violation_type == ViolationType.PREMATURE_ADVANCED_OPTIONS:
                content = self._hide_advanced_options(content, violation)
            elif violation.violation_type == ViolationType.CLUTTERED_MENU:
                content = self._simplify_menu(content, violation)
        
        if content != original_content:
            self.changes_made.append(str(file_path))
            file_path.write_text(content, encoding='utf-8')
        
        return content
    
    def _demote_extra_primary_buttons(self, content: str, 
                                     violation: UXViolation) -> str:
        """Demote all but the first primary button to secondary."""
        primary_pattern = r'(class="[^"]*)primary([^"]*")'
        
        # Replace all but first occurrence
        count = 0
        def replace_primary(match):
            nonlocal count
            count += 1
            if count == 1:
                return match.group(0)  # Keep first as primary
            return match.group(1) + 'secondary' + match.group(2)
        
        return re.sub(primary_pattern, replace_primary, content, flags=re.IGNORECASE)
    
    def _establish_button_hierarchy(self, content: str, 
                                   violation: UXViolation) -> str:
        """Make first button primary, others secondary."""
        button_pattern = r'(<button[^>]*class=")([^"]*")'
        
        count = 0
        def add_hierarchy(match):
            nonlocal count
            count += 1
            prefix = match.group(1)
            classes = match.group(2)
            
            if count == 1 and 'primary' not in classes:
                return prefix + 'btn-primary ' + classes
            elif count > 1 and 'primary' in classes:
                return prefix + classes.replace('primary', 'secondary')
            return match.group(0)
        
        return re.sub(button_pattern, add_hierarchy, content, flags=re.IGNORECASE)
    
    def _hide_advanced_options(self, content: str, 
                              violation: UXViolation) -> str:
        """Wrap advanced options in collapsible container."""
        advanced_patterns = ['advanced', 'settings', 'preferences', 'configuration']
        
        for pattern in advanced_patterns:
            if pattern in content.lower():
                # Simple heuristic: wrap in details/summary for HTML
                pattern_re = rf'(<div[^>]*>.*?{pattern}.*?</div>)'
                replacement = r'<details><summary>Advanced Options</summary>\1</details>'
                content = re.sub(pattern_re, replacement, content, 
                               flags=re.IGNORECASE | re.DOTALL, count=1)
                break
        
        return content
    
    def _simplify_menu(self, content: str, violation: UXViolation) -> str:
        """Group excessive menu items into categories."""
        # This is a simplified version - real implementation would need
        # semantic understanding of menu items
        ul_pattern = r'(<ul[^>]*>)(.*?)(</ul>)'
        
        def group_menu_items(match):
            open_tag = match.group(1)
            items = match.group(2)
            close_tag = match.group(3)
            
            # Count list items
            li_items = re.findall(r'<li[^>]*>', items)
            if len(li_items) > 7:
                # Split into groups (simplified - just add grouping comments)
                grouped = []
                item_list = re.split(r'(<li[^>]*>.*?</li>)', items, flags=re.DOTALL)
                item_list = [i for i in item_list if i.strip()]
                
                for i, item in enumerate(item_list):
                    if i % 4 == 0 and i > 0:
                        grouped.append(f'<!-- Group {i//4 + 1} -->')
                    grouped.append(item)
                
                return open_tag + '\n'.join(grouped) + close_tag
            
            return match.group(0)
        
        return re.sub(ul_pattern, group_menu_items, content, flags=re.DOTALL)
    
    def get_refactoring_summary(self) -> str:
        """Get summary of changes made."""
        if not self.changes_made:
            return "No refactoring changes were applied."
        
        return f"Refactored {len(self.changes_made)} file(s):\n" + \
               "\n".join(f"- {f}" for f in self.changes_made)


def run_audit_and_refactor(codebase_path: str, auto_refactor: bool = False) -> str:
    """
    Run complete Hick's Law audit and optionally refactor.
    
    Args:
        codebase_path: Path to the codebase to audit
        auto_refactor: If True, automatically apply fixes
        
    Returns:
        Markdown report of findings and actions taken
    """
    # Run audit
    auditor = HicksLawAuditor(codebase_path)
    report = auditor.audit()
    
    output = ["# Hick's Law UX Audit & Refactoring Report\n"]
    output.append(report.to_markdown())
    
    # Optionally refactor
    if auto_refactor and report.violations:
        output.append("\n---\n\n## Refactoring Applied\n")
        refactorer = HicksLawRefactorer()
        
        # Group violations by file
        violations_by_file = {}
        for violation in report.violations:
            if violation.file_path not in violations_by_file:
                violations_by_file[violation.file_path] = []
            violations_by_file[violation.file_path].append(violation)
        
        # Refactor each file
        for file_path, violations in violations_by_file.items():
            path = Path(file_path)
            if path.exists():
                refactorer.refactor_file(path, violations)
        
        output.append(refactorer.get_refactoring_summary())
    else:
        output.append("\n---\n\n*Auto-refactoring was not enabled. Review violations above and apply fixes manually.*\n")
    
    return "".join(output)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python hicks_law_audit.py <codebase_path> [--refactor]")
        sys.exit(1)
    
    codebase_path = sys.argv[1]
    auto_refactor = "--refactor" in sys.argv
    
    report = run_audit_and_refactor(codebase_path, auto_refactor)
    print(report)
