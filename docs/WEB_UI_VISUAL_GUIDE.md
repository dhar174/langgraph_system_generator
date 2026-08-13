# Web UI Visual Guide

## Overview

This document provides a visual guide to the enhanced LangGraph System Generator web interface.

## Interface Layout

### Header Section

```
┌──────────────────────────────────────────────────────────────────────┐
│  🚀 LangGraph System Generator                                       │
│  Generate complete multi-agent systems from natural language prompts │
│                                                                       │
│  [🟢 Server Online]  [📜]  [🌙]                                     │
└──────────────────────────────────────────────────────────────────────┘
```

**Elements:**
- Title with gradient effect
- Subtitle explaining the tool
- Server status indicator (green dot + text)
- History toggle button (📜)
- Theme toggle button (🌙/☀️)

---

### Main Form - Basic Options

```
┌─ Generate Your System ────────────────────────────────────────────────┐
│                                                                         │
│  Describe your multi-agent system:                                     │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ Example: Create a router-based chatbot that can handle...      │  │
│  │                                                                  │  │
│  │                                                                  │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                   0 / 5000 characters   │
│                                                                         │
│  Generation Mode:                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ Stub Mode (Fast, No API Key Required)             ▼            │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│  Stub mode generates a basic scaffold without external API calls.      │
│                                                                         │
│  Output Directory:                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ ./output/web_generated                                          │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Features:**
- Large textarea for prompt input
- Character counter with visual warning at limit
- Mode selector dropdown
- Help text for clarity
- Output directory input

---

### Advanced Options Panel (Collapsed)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ▶ Advanced Options                                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### Advanced Options Panel (Expanded)

```
┌─ ▼ Advanced Options ─────────────────────────────────────────────────────┐
│  ┌─────────────────────────┬─────────────────────────┬─────────────────┐ │
│  │ Model ⓘ                 │ Temperature: 0.7 ⓘ      │ Max Tokens ⓘ   │ │
│  │ ┌─────────────────────┐ │ ◄──────●──────────────► │ ┌─────────────┐ │ │
│  │ │ Default (gpt-5-nano)│ │  0              2       │ │ 4000        │ │ │
│  │ └─────────────────────┘ │                         │ └─────────────┘ │ │
│  └─────────────────────────┴─────────────────────────┴─────────────────┘ │
│                                                                            │
│  ┌─────────────────────────┬─────────────────────────────────────────────┐ │
│  │ Agent Type ⓘ            │ Memory Configuration ⓘ                      │ │
│  │ ┌─────────────────────┐ │ ┌─────────────────────────────────────────┐ │ │
│  │ │ Auto-detect         │ │ │ None                                    │ │ │
│  │ └─────────────────────┘ │ └─────────────────────────────────────────┘ │ │
│  └─────────────────────────┴─────────────────────────────────────────────┘ │
│                                                                            │
│  Output Formats ⓘ                                                         │
│  ☑ Jupyter Notebook (.ipynb)  ☑ HTML (.html)  ☑ Word Document (.docx)    │
│  ☐ PDF (.pdf)                  ☑ ZIP Bundle (.zip)                        │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

**Features:**
- Model selection dropdown with popular models
- Temperature slider with real-time value display
- Max tokens input
- Agent type selector
- Memory configuration selector
- Output format checkboxes
- Tooltips (ⓘ) for all options

---

### Submit Button

```
┌────────────────────────────────────────────────────────────┐
│                   [Generate System]                         │
└────────────────────────────────────────────────────────────┘
```

**States:**
- Normal: Blue button with white text
- Hover: Darker blue, slightly lifted
- Loading: "Generating..." with spinner animation
- Disabled: Grayed out

---

### Progress Card (During Generation)

```
┌─ Generation Progress ─────────────────────────────────────────────────┐
│                                                                        │
│  ████████████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░  50%      │
│  Invoking LLM...                                                      │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  ✅  Validating input                                          │  │
│  │  ✅  Preparing generation context                              │  │
│  │  ⏳  Invoking LLM                                              │  │
│  │  ⏳  Generating artifacts                                       │  │
│  │  ⏳  Finalizing outputs                                         │  │
│  │  ⏳  Complete                                                   │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ▶ Show Logs                                                          │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

**Features:**
- Progress bar with percentage
- Current step text
- Step-by-step indicators
- Checkmarks for completed steps
- Pulsing animation on active step
- Collapsible logs panel

---

### Results Card

```
┌─ Generation Results ──────────────────────────────────────────────────┐
│                                                                        │
│  ✅ Generation Successful!                                            │
│  Your system was generated in stub mode.                              │
│                                                                        │
│  Architecture: router                                                  │
│  Plan Title: LangGraph Workflow: Create a customer support...        │
│  Notebook Cells: 15                                                   │
│  Output Directory: ./output/web_generated                             │
│                                                                        │
│  Notebook Plan: ./output/web_generated/notebook_plan.json            │
│  Generated Cells JSON: ./output/web_generated/generated_cells.json   │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  📝 Next Steps:                                                │  │
│  │  1. Check the output directory for generated artifacts        │  │
│  │  2. Review the notebook plan and generated cells              │  │
│  │  3. Import the cells into a Jupyter notebook                  │  │
│  │  4. Customize and run your multi-agent system                 │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  📥 Available Downloads:                                               │
│  [📓 Notebook]  [🌐 HTML]  [📄 Word Doc]  [📦 ZIP Bundle]  [📋 Copy] │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

**Features:**
- Success message
- Key metadata (architecture, cell count, etc.)
- File paths with monospace formatting
- Next steps guide
- Download buttons for all formats
- Copy result info button

---

### History Panel

```
┌─ 📜 Recent Generations ──────────────────────────────────── [Clear History] ┐
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  1/13/2026, 3:45:23 AM                                                │ │
│  │  Create a customer support chatbot that can handle...                 │ │
│  │  [stub] [gpt-4]                                                       │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  1/13/2026, 3:42:15 AM                                                │ │
│  │  Create a router-based system for document processing...              │ │
│  │  [live] [default]                                                     │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  1/13/2026, 3:38:02 AM                                                │ │
│  │  Multi-agent system for code review and analysis...                   │ │
│  │  [stub] [default]                                                     │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Features:**
- Shows last 10 generations
- Timestamp for each entry
- Truncated prompt text
- Mode and model tags
- Click to reuse configuration
- Clear history button

---

### Error Display

```
┌─ ⚠️ Error ─────────────────────────────────────────────────────────────┐
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  Generation failed. Please try again or contact support if the    │ │
│  │  problem persists.                                                │ │
│  │                                                                   │ │
│  │  Please check your inputs and try again.                         │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Theme Comparison

### Dark Theme (Default)
- Background: Deep navy (#0f172a)
- Cards: Slate (#1e293b)
- Text: Light gray (#f1f5f9)
- Accent: Indigo (#6366f1)
- Perfect for low-light environments
- Reduces eye strain

### Light Theme
- Background: White (#ffffff)
- Cards: Light gray (#f8fafc)
- Text: Dark slate (#0f172a)
- Accent: Indigo (#6366f1)
- Better for bright environments
- Traditional document feel

---

## Responsive Design

### Desktop (>768px)
- Two-column grid for advanced options
- Side-by-side layout
- Hover effects enabled
- Full feature set

### Mobile (<768px)
- Single column layout
- Stacked elements
- Touch-optimized buttons
- Same features, optimized spacing

---

## Interactive Elements

### Buttons
- **Primary**: Blue, full-width, prominent
- **Secondary**: Gray, inline, for actions
- **Icon**: Circular, header controls
- **Hover**: Lift effect, color change
- **Active**: Scale down slightly
- **Disabled**: Reduced opacity

### Form Controls
- **Text Input**: Border highlight on focus
- **Select**: Dropdown with custom styling
- **Slider**: Custom thumb with hover effect
- **Checkbox**: Accent color checkmark
- **All**: Smooth transitions

### Cards
- **Hover**: Slight lift (2px)
- **Shadow**: Increases on hover
- **Border**: Left accent for status
- **Animation**: Slide down when shown

---

## Accessibility Features

### Keyboard Navigation
- Tab through all controls
- Enter/Space to activate
- Escape to close panels
- Logical tab order

### Visual Indicators
- Focus outlines on all interactive elements
- Color contrast meets WCAG AA
- Icons supplement text
- Status communicated visually and textually

### Screen Readers
- ARIA labels on all inputs
- Role attributes for interactive elements
- Live regions for updates
- Descriptive button text

---

## Performance

- **Load Time**: <1 second
- **Bundle Size**: ~20KB total (HTML + CSS + JS)
- **No Dependencies**: Pure vanilla JavaScript
- **Smooth Animations**: 60fps transitions
- **LocalStorage**: Minimal usage (<1MB)

---

## Browser Support

✅ Chrome 90+
✅ Firefox 88+
✅ Safari 14+
✅ Edge 90+
✅ Mobile browsers
✅ Tablet devices

---

## Color Palette

### Dark Theme
```
Primary:   #6366f1 (Indigo)
Success:   #10b981 (Green)
Error:     #ef4444 (Red)
Warning:   #f59e0b (Amber)
BG:        #0f172a (Navy)
Card:      #1e293b (Slate)
Text:      #f1f5f9 (White)
```

### Light Theme
```
Primary:   #6366f1 (Indigo)
Success:   #059669 (Green)
Error:     #dc2626 (Red)
Warning:   #d97706 (Amber)
BG:        #ffffff (White)
Card:      #f8fafc (Gray)
Text:      #0f172a (Navy)
```

---

## Summary

The enhanced web UI provides:
- **Power**: Advanced configuration options
- **Simplicity**: Defaults work out of the box
- **Feedback**: Real-time progress and status
- **History**: Learn from past generations
- **Accessibility**: Works for everyone
- **Performance**: Fast and responsive
- **Flexibility**: Multiple export formats
- **Polish**: Smooth animations and transitions

All features are optional - the interface scales from simple to advanced based on user needs.
