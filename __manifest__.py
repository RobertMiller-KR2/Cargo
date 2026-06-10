# Copyright (C) 2026 KR Squared, Inc.
# License OPL-1 (Odoo Proprietary License v1.0)
{
    'name': 'Cargo Architect',
    'version': '19.0.2.0.45',
    'category': 'Inventory',
    'summary': '3D cargo load planning, trailer optimization, reports, and warehouse loading guidance',
    'description': '''
Support: cargoarchitect@kr2inc.com
Website: https://cargoarchitect.kr2inc.com/

Cargo Architect for Odoo 19 - v2.0.45
====================================
3D-style cargo load planning, trailer presets, product presets, load optimization, axle estimates, branded load reports, and Odoo 19-safe picking import and backend 3D planner assets, and product preset dimension synchronization, line-to-preset create/update from edited load dimensions, and fully editable load line list/form fields, and top/left/right planner view buttons, report percent-format fix, report top/left/right layout views, axle/load statistics, additional capacity information, and QWeb-safe report percentage formatting. Apps info version: 19.0.2.0.45. Custom load report layout removes Odoo external-layout Tax ID/VAT by default and adds report company-info options. Report items are summarized by product/dimensions with quantity and total weight. Trailer weight distribution is shown in metrics and load report. Report layout diagrams: top, left side, and right side included in the QWeb PDF. Fit warning alerts are shown when any items cannot be placed. v1.0.16 stabilization: corrected weight fallback calculations, axle/weight-distribution values from actual loaded weights, report diagram markup, editable-line/preset synchronization support, and app-info version display. v1.0.17 approval workflow: Draft, Optimized, Ready For Review, Approved, Released To Warehouse, Loaded, with approval validation, locked approved/released/loaded plans, approval metadata, and workflow buttons. v1.1.0 executive dashboard: quality score breakdown, pass/warning/fail indicators, axle utilization graphics, and modern report scorecards. v1.2.0 engineering analysis: weight heat map, center-of-gravity graphic, trailer weight distribution graphic, floor loading analysis, stability/capacity summaries, and additional capacity analysis. v1.2.1 visibility fix: engineering analysis is shown prominently on the load plan form and report, weight heat map expanded to eight trailer rows, and report sections are force-visible after optimization. v1.2.2 registry-load fix: corrected undefined stability status and capacity summary values during stored metric recomputation. v1.3.0 warehouse operations: load sequence, unload sequence, forklift accessibility, loading instructions, and QR load passport. v1.3.1 report layout cleanup: reliable QR barcode widget, corrected page breaks, full-width sequence tables, and nowrap report columns. v1.3.2 report header/footer update: company logo/address moved to top-left, report title removed from header, and report footer added with title, page number, date, and version on each page. v1.3.3 professional report layout fix: removes excess top whitespace, repeats the custom header on all PDF pages, improves fixed footer layout, tightens spacing, and stabilizes page breaks. v1.3.4 report header/footer correction: applies inline header/footer sizing for wkhtmltopdf, prevents company logo/header overlap, preserves consistent footer page/date/version, and reserves safe body space on every page. v1.3.7 settings migration: report option checkboxes moved to Settings > Cargo Architect via res.config.settings and ir.config_parameter; Tax ID/VAT is permanently excluded from load reports. v1.3.7 report pagination polish: section headers stay with their data, related report sections are grouped onto sensible pages, excess body top spacing is reduced, and long sequence/accessibility/layout sections start on clean pages. v1.4.1 business intelligence: cost savings analysis, trailer selection recommendation, carbon footprint estimate, historical KPI dashboard action, and customer branding profiles. v1.4.2 Odoo-native icon: rounded square Cargo Architect app icon with simplified A/trailer/cargo mark for better alignment with Odoo app icons. v1.4.4 simplified trailer icon: removed the A mark and replaced the Apps/menu icon with a simple trailer-focused Odoo-style icon. v2.0.0 advanced planning: manual placement editing, placement locking, re-optimization around locked placements, optimization mode selection, and multi-trailer planning summary. v2.0.3 Best Balance full-fit enforcement: Best Balance now evaluates fallback packing modes and chooses the layout with the fewest unplaced items first; weight balance is only a tie-breaker, so a balanced layout cannot exclude items that another strategy can load. v2.0.8 Best Fill + Level Load: optimizer now treats full trailer fill and practical transport stability as the primary layout-quality goals after maximum fit. Candidate placement scoring favors side-by-side width pairing, lower void space, compact blocked rows, and more level stack tops before weight-balance tie-breakers. This improves P001-010 style rotation decisions so items can be paired across trailer width when it reduces empty space and movement risk.  v2.0.10 settings persistence fix: report option checkboxes now explicitly load and save ir.config_parameter values, backing System Parameters are created on install/upgrade, and unchecked company logo/name/address/footer options remain disabled after Save and are honored by QWeb reports. v2.0.11 version display and paired-width loading fix: report headers/footers and Apps/About information now show 19.0.2.0.11 / v2.0.11 instead of stale v2.0.6/v2.0.2 text. Best Fill placement now strongly favors pairable rotated lanes for items that can fit two-across, avoids centerline single-file rows when side-by-side placement is possible, and scores compact width occupancy ahead of centered placement. v2.0.15 report version source + transport block packing: report version labels now render from code constants, safe floor rotation is considered even when imported rotatable flags are stale, and pairable SKUs are post-processed into two-across stacked blocks when physically possible. v2.0.7 Best Balance refinement: maximum-fit remains the first priority, then centerline-prorated side balance is scored before front/rear balance, balanced/front modes avoid obvious one-sided placements, and additional-capacity recommendations are placement-aware instead of cube-only.
    ''',
    'author': 'KR Squared, Inc.',
    'website': 'https://cargoarchitect.kr2inc.com/',
    'support': 'cargoarchitect@kr2inc.com',
    'maintainer': 'KR Squared, Inc.',
    'license': 'OPL-1',
    'price': 299.00,
    'currency': 'USD',
    'depends': ['base', 'base_setup', 'product', 'stock'],
    'assets': {
        'web.assets_backend': [
            'cargo_architect/static/src/scss/cargo_architect.scss',
            'cargo_architect/static/src/xml/cargo_architect_templates.xml',
            'cargo_architect/static/src/js/cargo_architect_client.js',
        ],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/cargo_architect_data.xml',
        'data/cargo_report_section_defaults.xml',
        'views/cargo_trailer_preset_views.xml',
        'views/cargo_product_preset_views.xml',
        'views/cargo_branding_profile_views.xml',
        'views/cargo_architect_menus.xml',
        'views/cargo_load_plan_views.xml',
        'views/res_config_settings_views.xml',
        'report/cargo_load_plan_report.xml',
    ],
    'images': [
        'static/description/main_screenshot.png',
        'static/description/planner_three_view.png',
        'static/description/report_preview.png',
        'static/description/settings_preview.png',
        'static/description/paste_import_preview.png',
    ],
    'application': True,
    'installable': True,
}

# v2.0.3: Overall PASS/WARNING/FAIL now reflects hard compliance only; balance/stability quality issues are reported as advisories. v2.0.6 side-to-side balance: Best Balance now evaluates left/right weight balance and reports left/right side weights, side difference, score, and advisory status.

# v2.0.6: Side balance now prorates weight by actual item footprint overlap across the trailer centerline; Best Balance scores true left/right weight instead of center-point-only assignment.

# v2.0.7: Best Balance keeps maximum-fit priority, scores centerline-prorated side balance before front/rear balance, improves side-by-side candidate selection, and makes Additional Capacity recommendations placement-aware.

# v2.0.8: Best Fill + Level Load scoring prefers maximum fit, minimal void space, paired width lanes, compact blocking, level tops, then side/front weight balance.

# v2.0.9 Trailer Recommendation Accuracy: trailer recommendations use physical-fit simulation and report a trailer evaluation matrix.

# v2.0.10 Settings Persistence Fix: report option checkboxes explicitly persist to ir.config_parameter and QWeb report sections honor unchecked company/header options.

# v2.0.11 Version Display + Paired Width Loading: report/app version labels are current and the optimizer favors two-across rotated lane placement over centerline single-file rows when items fit side-by-side.
# v2.0.15 Report Version Source + Transport Block Packing: report version labels now render from code constants and pairable items are post-processed into two-across stacked blocks when physically possible.

# v2.0.15 Upgrade Safety Fix: removed direct ir.config_parameter XML records that caused duplicate-key upgrade failures; report option persistence remains through config_parameter fields and set_param.

# v2.0.16 Centerline Pairing + Safe Drag Validation: pairable rows remain centered with equal side clearance; wide one-across freight is centered where possible; drag/drop overlap and bounds rejections return friendly warnings instead of server tracebacks.

# v2.0.18 Runtime scope fix: defines trailer width/length/height in optimizer scope before wide single-across centering, preventing NameError during Optimize Layout while preserving centerline pairing and safe drag validation.

# v2.0.18 Placement unlock controls: adds per-placement Unlock buttons in the placement list and planner, renames the top action to Unlock All, and adds a planner-level Unlock All action.

# v2.0.20 Planner navigation: adds a Back to Load Plan button, manual stack/unstack drag editing in top/left/right views on the 3D planner page that returns to the originating load plan form.

# v2.0.23 Mixed SKU Width Pairing: optimizer can pair different product types side-by-side when combined widths fit, keeps mixed rows centered, checks levelness and stack support, and preserves multi-level/manual stack validation. v2.0.23 Three-View Planner: top, left side, and right side views are visible at the same time on the planner page; each view supports selection highlighting and drag/drop editing appropriate to that projection.

# v2.0.23 Three-View Planner: shows Top, Left Side, and Right Side views at once on the 3D planner page while preserving drag/drop selection, stack/unstack editing, Back to Load Plan, Unlock All, and per-placement unlock controls.

# v2.0.23 Tabbed Load Plan Form: reorganizes the long load plan form into focused tabs for Items, Dashboard, Weight & Engineering, Placements, Warehouse, Business, Approval, and Technical JSON while keeping the primary summary/actions at the top.

# v2.0.26 Printable Report Margin Fix: increases PDF top print margin and body/header safe spacing so report content is not cut off by physical printers.

# v2.0.25 Print Safe Layout Fix: increases left/right printable margins, constrains report content to a centered printable safe box, and prevents wide tables/diagrams from exceeding physical printer boundaries.

# v2.0.26 Real-World Stability Thresholds: stability status now uses side imbalance, lateral COG offset, vertical COG, estimated static stability factor, and stack support thresholds rather than only a heuristic quality score.

# v2.0.33 Load Securement Analysis: adds cargo shift risk, void space analysis, strap/load bar estimates, blocking recommendations, and securement status for reports and load planning.

# v2.0.33 Letter Paper Standardization: uses US Letter landscape paperformat with standard 1-inch margins on all sides and constrains report content to the printable area.
# v2.0.33 Codebase Refactor: splits load line and placement models into separate Python files and introduces a services package for future optimizer modularization while preserving v2.0.28 behavior.

# v2.0.33 Report Layout Rebuild: reserves larger header/footer regions, adds body/page-break top spacers, reduces repeated header/footer height, and constrains diagrams to prevent overlap.

# v2.0.33 Placement History: adds Undo/Redo support for manual placement changes, lock/unlock actions, and optimization snapshots.

# v2.0.33 Advanced Manual Editing: adds multi-select placement editing, group drag/move, align tools, distribute evenly, and snap-to-grid controls in the three-view planner while preserving undo/redo history.

# v2.0.36 Paste Items Import: adds an Items To Load paste area that parses lines like P001-008 (1 pallet), resolves product presets/products, replaces load lines, clears old placements, and returns the plan to Draft for re-optimization.

# v2.0.36 Mandatory Dense Compaction: final optimizer pass repacks all unlocked placements front-left with minimal gaps; weight spread remains advisory unless payload/axle limits fail.

# v2.0.36 Fit Preservation: final post-processing cannot reduce the best loaded count; recovery repack restores full-fit layouts when dense compaction or other post-processing leaves items unplaced despite physical capacity.

# v2.0.37 Paste Items Quantity Per Pallet: paste import now supports item counts per pallet, e.g. P001-008 (2 pallets, 24 items each), and stores/report Items Per Pallet and Total Items on load lines.

# v2.0.39 Load Metrics & Inventory Visibility: adds plan-level total pallet and inventory item rollups, loaded item totals from actual placements, report totals, and validation visibility for missing Items / Pallet values.

# v2.0.40 Report Restoration: restores all detailed report sections after load metrics updates by force-enabling core report section parameters on upgrade while preserving header/company visibility options.

# v2.0.43 Planner item numbering: planner labels show sequential item numbers instead of item names, rotated placements show R in side views, coordinates can be toggled on/off, and placement rows use matching product-type colors.

# v2.0.44 OPL-1 Store Readiness: sets Odoo Proprietary License v1.0 metadata, support contact, website, price/currency, proprietary license file, and copyright notices for Odoo Apps distribution.

# v2.0.45 Odoo Store Submission Package: adds polished static description page, screenshot image assets, final OPL-1/store metadata, and submission-readiness documentation.
