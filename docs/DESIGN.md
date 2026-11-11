---
name: Institutional Excellence Green
colors:
  surface: '#f7faf4'
  surface-dim: '#d8dbd5'
  surface-bright: '#f7faf4'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f5ee'
  surface-container: '#ecefe9'
  surface-container-high: '#e6e9e3'
  surface-container-highest: '#e0e3dd'
  on-surface: '#191d19'
  on-surface-variant: '#41493d'
  inverse-surface: '#2d312d'
  inverse-on-surface: '#eff2eb'
  outline: '#717a6c'
  outline-variant: '#c1c9ba'
  surface-tint: '#316b27'
  primary: '#002800'
  on-primary: '#ffffff'
  primary-container: '#004000'
  on-primary-container: '#70ae61'
  inverse-primary: '#97d785'
  secondary: '#026e00'
  on-secondary: '#ffffff'
  secondary-container: '#00f900'
  on-secondary-container: '#026d00'
  tertiary: '#1e2220'
  on-tertiary: '#ffffff'
  tertiary-container: '#333735'
  on-tertiary-container: '#9ca09d'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#b2f39f'
  primary-fixed-dim: '#97d785'
  on-primary-fixed: '#002200'
  on-primary-fixed-variant: '#175210'
  secondary-fixed: '#77ff61'
  secondary-fixed-dim: '#02e600'
  on-secondary-fixed: '#002200'
  on-secondary-fixed-variant: '#015300'
  tertiary-fixed: '#e0e3e0'
  tertiary-fixed-dim: '#c4c7c5'
  on-tertiary-fixed: '#181c1b'
  on-tertiary-fixed-variant: '#444846'
  background: '#f7faf4'
  on-background: '#191d19'
  surface-variant: '#e0e3dd'
typography:
  headline-xl:
    fontFamily: Hanken Grotesk
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Hanken Grotesk
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Hanken Grotesk
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Hanken Grotesk
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Hanken Grotesk
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
  label-sm:
    fontFamily: Hanken Grotesk
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  container-max: 1280px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 32px
---

## Brand & Style

This design system establishes a professional, authoritative, yet modern administrative environment for educational management in Peru. The visual language balances the heritage of an established institution with the efficiency of modern SaaS tooling.

The style is **Corporate / Modern** with a focus on high legibility and structured information density. It utilizes a clean, systematic approach to layout, ensuring that complex data—such as student records, academic scheduling, and financial reports—is presented with clarity and institutional pride. The atmosphere is reliable and disciplined, reflecting the core values of "Colegio Domingo Savio."

The interface should feel:
- **Professional:** Structured and dependable.
- **Academic:** Promoting a sense of order and institutional history.
- **Efficient:** Minimizing friction in administrative workflows.

## Colors

The palette is derived directly from the institutional identity, utilizing a high-contrast green spectrum to denote hierarchy and action.

- **Primary (#004000):** A deep forest green used for headers, primary buttons, and critical branding elements. It represents stability and authority.
- **Secondary/Accent (#00FF00):** A vibrant lime green used sparingly for highlights, success states, and interactive accents. Due to its high vibrance, it is primarily used as a border accent or a decorative element to maintain WCAG accessibility.
- **Tertiary/Surface (#F4F7F4):** A very light, green-tinted neutral used for backgrounds to reduce eye strain compared to pure white.
- **Neutral (#2D312D):** A deep charcoal with a slight green undertone for body text and interface borders, ensuring a cohesive "dark-on-light" reading experience.

Status colors (Error: #D32F2F, Warning: #FBC02D, Info: #0288D1) should be desaturated slightly to harmonize with the green-dominant environment.

## Typography

The design system utilizes **Hanken Grotesk** for all typographic roles. This typeface provides a sharp, contemporary geometric feel that remains highly legible in data-heavy tables and forms.

For the Peruvian Spanish context, ensure all glyphs (ñ, á, é, í, ó, ú) are rendered with consistent weight. Headlines use a bold weight to establish clear section breaks. Body text maintains a comfortable 1.5x line height for extended reading of administrative circulars. Labels and metadata should use slightly tighter tracking to differentiate from narrative content.

## Layout & Spacing

The layout follows a **Fixed Grid** model for desktop and a **Fluid Grid** for mobile.

- **Desktop (12 columns):** Max-width of 1280px, centered. 24px gutters. Use 32px external margins.
- **Tablet (8 columns):** Fluid width. 16px gutters.
- **Mobile (4 columns):** Fluid width. 16px external margins.

The spacing system is built on an 8px base unit. Component padding should strictly follow multiples of 4px for fine-tuning (e.g., 12px padding for small buttons, 16px for cards). In administrative dashboards, vertical density is preferred to minimize scrolling through lists.

## Elevation & Depth

Visual hierarchy is established through **Tonal Layers** and **Low-contrast Outlines**. 

To maintain a professional, flat aesthetic, shadows are used very sparingly—only to indicate temporary "floating" elements like dropdowns or modals.
- **Surface Level 0:** The main application background (#F4F7F4).
- **Surface Level 1:** White containers for content cards, featuring a 1px border in a muted green-grey (#D1D9D1).
- **Surface Level 2:** Active states or focused inputs, using a subtle inner shadow or a 2px border in Primary Green.

Depth is primarily communicated via color saturation: interactive elements are more saturated, while background structures are desaturated.

## Shapes

The shape language is defined as **Rounded**, providing a sophisticated and approachable look that softens the "sharpness" of institutional data.

- **Standard Elements (Buttons, Inputs):** 0.5rem (8px) corner radius.
- **Large Containers (Cards, Modals):** 1rem (16px) corner radius.
- **Extra Large (Feature Blocks):** 1.5rem (24px) corner radius.

This consistency in curvature ensures that the UI feels cohesive and intentionally designed, moving away from generic browser defaults.

## Components

### Buttons
- **Primary:** Background #004000, Text #FFFFFF. 0.5rem radius. Bold weight.
- **Secondary:** Background transparent, Border 2px #004000, Text #004000.
- **Accent/Ghost:** Text #004000, background changes to light green tint on hover.

### Input Fields
Inputs use a white background with a 1px border. On focus, the border shifts to Primary Green with a subtle "Secondary Green" outer glow (2px). Labels are always visible above the field in `label-md`.

### Cards
Cards are the primary container for data. They feature a white background, 1rem rounded corners, and a 1px soft border. For high-priority items, a 4px left-hand border in the Secondary Lime Green can be added to draw attention.

### Chips & Badges
Used for student status (e.g., "Inscrito", "Pendiente"). These use high-chroma backgrounds with dark text for maximum visibility within lists.

### Navigation
The sidebar navigation uses the Primary Green (#004000) as a background, with white text at 80% opacity for inactive items and 100% opacity for active items. Active states are marked with a Secondary Green (#00FF00) vertical indicator on the left edge.