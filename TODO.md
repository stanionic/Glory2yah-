# CSS Modernization Plan - TODO

## Phase 1: Core Design System (style.css → g2y-app.css unification)
- [x] 1. Create unified CSS variables file (`static/css/variables.css`)

## Phase 2: Component Styles
- [x] 2. Modernize `static/css/style.css` - Replace old hardcoded colors (--royal-blue, --golden, --white) with --g2y-* vars, remove duplicate animations, add .dark-mode support
- [x] 3. Modernize `static/css/g2y-app.css` - Remove duplicate :root vars, remove duplicate animations, add dark mode, use --g2y-* vars
- [x] 4. Modernize `static/css/admin.css` - Replace all hardcoded hex colors with --g2y-* vars, replace standalone gradients, add dark mode
- [x] 5. Modernize `static/css/gkach.css` - Replace hardcoded hex colors with --g2y-* vars, add dark mode, use --g2y-* vars
- [x] 6. Modernize `static/css/konferans.css` - Replace hardcoded hex colors with --g2y-* vars, add dark mode, use --g2y-* vars
- [x] 7. Modernize `static/css/pwa.css` - Use --g2y-* vars instead of hardcoded colors, add .dark-mode class support

## Phase 3: Ecole Biblique & Dok
- [x] 8. Modernize `ecole_biblique/static/css/style.css` - Map --eb-* vars to --g2y-* system, add dark mode
- [x] 9. Modernize `dok/static/style.css` - Integrate with --g2y-* system

## Phase 4: Template Updates
- [x] 10. Update templates to include variables.css
- [ ] 11. Update all templates to use modern CSS classes (in progress)

## Phase 5: Testing
- [ ] 12. Run the app and verify all pages render correctly
- [ ] 13. Check dark mode toggle works
- [ ] 14. Verify responsive behavior