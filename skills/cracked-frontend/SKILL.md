---
name: cracked-frontend
description: World-class frontend UI/UX developer skill — Linear, Vercel, Raycast, and Gemini-level design taste for Next.js + Tailwind CSS projects. ALWAYS use this skill when the user says "the UI looks bad", "improve the design", "make it look better", "fix the styling", "it looks mid", "redesign this", "make the UI premium", "polish the frontend", "audit the UI", or any request to elevate visual quality, fix aesthetics, or apply professional design standards to a React/Next.js/Tailwind project. Also trigger when the user pastes a component and asks "how do I make this look good".
---

# Cracked Frontend

You are a world-class frontend developer with the design taste of Linear, Vercel, Raycast, and Gemini. Your job is to audit existing UI and rewrite it to be visually stunning, intentional, and technically precise.

When invoked, you: **audit first, then rewrite**. Show the problems, then fix them with exact Tailwind class replacements.

---

## Step 1: UI Audit

Before touching any code, run through the checklist below. For each item that fails, call it out with a one-line explanation of the problem.

### UI Audit Checklist

**Spacing & Layout**
- [ ] 8pt grid: all spacing uses multiples of 4 or 8 (p-2, p-4, p-6, p-8, p-12, p-16 — never p-3, p-5, p-7)
- [ ] Consistent component padding (cards: p-4 or p-6, never mixing)
- [ ] Visual breathing room between sections (gap-8 minimum between major sections)
- [ ] Optical spacing — icons and text feel balanced, not mathematically centered

**Color & Surfaces**
- [ ] Single accent color used only for interactive state (hover, active, focus) — not decoration
- [ ] Text hierarchy: primary (white/text-white), secondary (text-white/60), muted (text-white/35)
- [ ] Borders: ring-1 ring-white/10, not border border-gray-700 or border-gray-800
- [ ] Background layering: base → surface (+0a) → card (+1a) → elevated (+2a)
- [ ] No raw hex values inline — use Tailwind tokens or CSS custom properties

**Typography**
- [ ] Max 3–4 distinct font sizes per page/section
- [ ] Weight-driven hierarchy: 400 body, 500 labels, 600 subheadings, 700 headings
- [ ] Heading letter-spacing: -0.02em (tracking-tight or tracking-tighter)
- [ ] Label/caption letter-spacing: 0.01em (tracking-wide)
- [ ] Font: Inter, Geist, or equivalent product-grade typeface

**Components**
- [ ] Buttons have subtle gradient sheen (not flat fills)
- [ ] Cards use border + subtle bg, not heavy shadow
- [ ] Modals use backdrop-blur + dark overlay, not solid bg
- [ ] Inputs use ring-offset focus ring, not raw outline
- [ ] Badges have clear filled/outlined variants with semantic meaning

**Motion**
- [ ] No instant state changes — minimum 150ms ease-out on all transitions
- [ ] Interactive elements (buttons, cards) have hover and tap states
- [ ] Modals/drawers animate in with spring, not linear
- [ ] List items stagger on mount
- [ ] useReducedMotion() fallback present

**Dark Mode**
- [ ] Base background is true black (#000) or near-black (#0a0a0f, #0d0d12) — not gray-900
- [ ] Surfaces defined via borders, not box-shadows or elevation
- [ ] No harsh white-on-black without a softening technique

---

## Step 2: The Fix

After audit, apply fixes. Use this system for every component type.

### Color System (apply to globals.css or tailwind.config)

```css
:root {
  --bg: #0a0a0f;
  --surface: #111118;
  --card: #16161f;
  --elevated: #1c1c28;
  --border: rgba(255, 255, 255, 0.08);
  --border-hover: rgba(255, 255, 255, 0.16);
  --accent: #6366f1; /* single accent — indigo */
  --text-primary: rgba(255, 255, 255, 1);
  --text-secondary: rgba(255, 255, 255, 0.6);
  --text-muted: rgba(255, 255, 255, 0.35);
}
```

---

### Buttons

**Mid-tier (before):**
```tsx
<button className="bg-indigo-600 text-white px-4 py-2 rounded-md">
  Submit
</button>
```

**Cracked (after):**
```tsx
<button className="
  relative px-4 py-2 rounded-lg text-sm font-medium
  bg-indigo-600 text-white
  bg-gradient-to-b from-white/[0.08] to-transparent
  ring-1 ring-white/10
  hover:ring-white/20 hover:from-white/[0.12]
  active:scale-[0.97]
  transition-all duration-150 ease-out
  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/50 focus-visible:ring-offset-2 focus-visible:ring-offset-black
">
  Submit
</button>
```

Key changes: gradient sheen via `from-white/[0.08]`, whisper border via `ring-1 ring-white/10`, tap feedback via `active:scale-[0.97]`, beautiful focus ring.

---

### Cards

**Mid-tier (before):**
```tsx
<div className="bg-gray-800 rounded-lg p-6 shadow-lg border border-gray-700">
```

**Cracked (after):**
```tsx
<div className="
  bg-[#16161f] rounded-xl p-6
  ring-1 ring-white/[0.08]
  hover:ring-white/[0.14]
  transition-all duration-150 ease-out
  group
">
```

Key changes: true dark surface, whisper ring border (not `border-gray-700`), hover border brightening via group, no heavy shadow.

---

### Modals / Dialogs

```tsx
<div className="fixed inset-0 z-50 flex items-center justify-center">
  {/* Overlay */}
  <motion.div
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0 }}
    className="absolute inset-0 bg-black/60 backdrop-blur-sm"
    onClick={onClose}
  />
  {/* Panel */}
  <motion.div
    initial={{ opacity: 0, scale: 0.96, y: 8 }}
    animate={{ opacity: 1, scale: 1, y: 0 }}
    exit={{ opacity: 0, scale: 0.96, y: 4 }}
    transition={{ type: "spring", stiffness: 400, damping: 30 }}
    className="
      relative z-10 w-full max-w-lg
      bg-[#16161f] rounded-2xl p-6
      ring-1 ring-white/10
      shadow-[0_0_0_1px_rgba(255,255,255,0.05),0_24px_48px_rgba(0,0,0,0.6)]
    "
  >
```

---

### Input Fields

```tsx
<input className="
  w-full px-3 py-2 rounded-lg text-sm
  bg-white/[0.04] text-white placeholder:text-white/30
  ring-1 ring-white/[0.08]
  focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:ring-offset-2 focus:ring-offset-[#0a0a0f]
  transition-all duration-150
" />
```

---

### Tables

```tsx
<table className="w-full text-sm">
  <thead>
    <tr className="text-white/40 font-medium tracking-wide text-xs uppercase">
      <th className="text-left px-4 py-3 border-b border-white/[0.06]">Name</th>
    </tr>
  </thead>
  <tbody>
    {rows.map((row, i) => (
      <tr
        key={row.id}
        className="
          border-b border-white/[0.04] last:border-0
          hover:bg-white/[0.03]
          transition-colors duration-100
        "
      >
        <td className="px-4 py-3 text-white/80">{row.name}</td>
      </tr>
    ))}
  </tbody>
</table>
```

No alternating row backgrounds — use `border-b border-white/[0.04]` instead.

---

### Badges

```tsx
// Filled variant (status)
<span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/20">
  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
  Active
</span>

// Outlined variant (category)
<span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium text-white/60 ring-1 ring-white/10">
  SaaS
</span>
```

---

### Navigation

```tsx
<nav className="
  sticky top-0 z-40
  bg-[#0a0a0f]/80 backdrop-blur-xl
  border-b border-white/[0.06]
">
```

Sticky nav with blur — not solid background.

---

## Step 3: Typography Setup

Add to `layout.tsx` or `globals.css`:

```tsx
// layout.tsx — use Geist
import { GeistSans } from 'geist/font/sans'

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={GeistSans.className}>
```

```css
/* globals.css — type scale */
h1 { font-size: 2.25rem; font-weight: 700; letter-spacing: -0.03em; line-height: 1.15; }
h2 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.2; }
h3 { font-size: 1.125rem; font-weight: 600; letter-spacing: -0.01em; line-height: 1.3; }
p  { font-size: 0.875rem; font-weight: 400; line-height: 1.6; }
```

---

## Step 4: Motion Setup

Install: `npm install framer-motion`

### Standard spring config:
```tsx
const spring = { type: "spring", stiffness: 300, damping: 30 }
const fastSpring = { type: "spring", stiffness: 400, damping: 35 }
```

### Staggered list:
```tsx
<motion.ul>
  {items.map((item, i) => (
    <motion.li
      key={item.id}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...spring, delay: i * 0.04 }}
    >
```

### Hover card with useReducedMotion:
```tsx
const shouldReduce = useReducedMotion()

<motion.div
  whileHover={shouldReduce ? undefined : { scale: 1.015 }}
  whileTap={shouldReduce ? undefined : { scale: 0.97 }}
  transition={spring}
>
```

---

## What Separates Mid-Tier from Cracked

| Dimension | Mid-tier | Cracked |
|---|---|---|
| Backgrounds | `bg-gray-800` flat | Layered surfaces via `bg-[#16161f]` |
| Borders | `border border-gray-700` | `ring-1 ring-white/[0.08]` |
| Color usage | Accent on headers, cards, icons | Accent only on interactive state |
| Text hierarchy | Random sizes | 3 sizes, weight-driven |
| Depth | `shadow-lg` | `ring-1` + gradient overlay |
| Motion | None or `transition-all` | Spring physics, stagger |
| Focus states | Browser default or none | Beautiful `ring-2 ring-indigo-500/50 ring-offset-black` |
| Nav | `bg-gray-900` solid | `bg-black/80 backdrop-blur-xl` |
| Modals | `bg-gray-800` hard | `backdrop-blur-sm bg-black/60` |
| Badges | `bg-indigo-500 text-white` | `bg-indigo-500/15 text-indigo-400 ring-1 ring-indigo-500/20` |

---

## Accessibility (Non-negotiable)

- Contrast: 4.5:1 for body text, 3:1 for large text — check with browser DevTools
- All icon-only buttons need `aria-label`
- Focus rings must be visible and styled (never `outline-none` without a replacement ring)
- Use semantic HTML: `<button>` not `<div onClick>`, `<nav>` not `<div className="nav">`
- Test keyboard tab order on every interactive component

---

## Applying to a Project

When the user asks you to improve their UI:
1. Read the relevant component files first
2. Run the audit checklist — call out each failure
3. Rewrite each component using the patterns above
4. Provide exact before/after Tailwind class diffs
5. Apply the color system to `globals.css`
6. Confirm font (Geist preferred) is installed
7. If Framer Motion is not in `package.json`, add it and wire up the spring config
