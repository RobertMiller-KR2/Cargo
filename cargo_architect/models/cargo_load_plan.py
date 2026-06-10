from collections import defaultdict
import math
import json
import re
from urllib.parse import quote_plus
from odoo import api, fields, models, _
from odoo.exceptions import UserError

CARGO_ARCHITECT_MODULE_VERSION = '19.0.2.0.40'
CARGO_ARCHITECT_APP_VERSION = 'v2.0.40'


class CargoLoadPlan(models.Model):
    _name = 'cargo.architect.load.plan'
    _description = 'Cargo Architect Load Plan'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New Load Plan'))
    state = fields.Selection([
        ('draft', 'Draft'),
        ('optimized', 'Optimized'),
        ('review', 'Ready For Review'),
        ('approved', 'Approved'),
        ('released', 'Released To Warehouse'),
        ('loaded', 'Loaded'),
    ], default='draft')
    submitted_by_id = fields.Many2one('res.users', string='Submitted By', readonly=True, copy=False)
    submitted_date = fields.Datetime(string='Submitted Date', readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)
    approved_date = fields.Datetime(string='Approved Date', readonly=True, copy=False)
    released_by_id = fields.Many2one('res.users', string='Released By', readonly=True, copy=False)
    released_date = fields.Datetime(string='Released Date', readonly=True, copy=False)
    loaded_by_id = fields.Many2one('res.users', string='Loaded By', readonly=True, copy=False)
    loaded_date = fields.Datetime(string='Loaded Date', readonly=True, copy=False)
    approval_note = fields.Text(string='Approval / Release Notes', copy=False)
    approval_blocker = fields.Char(compute='_compute_approval_status', store=False)
    can_approve_load = fields.Boolean(compute='_compute_approval_status', store=False)

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    partner_id = fields.Many2one('res.partner', string='Customer')
    branding_profile_id = fields.Many2one('cargo.architect.branding.profile', string='Branding Profile')
    baseline_trailer_count = fields.Integer(string='Baseline Trailer Count', default=1)
    freight_cost_per_trailer = fields.Float(string='Freight Cost / Trailer')
    loaded_miles = fields.Float(string='Loaded Miles')
    co2_lbs_per_mile = fields.Float(string='CO₂ lb / Mile', default=22.4)
    optimized_trailer_count = fields.Integer(compute='_compute_metrics', store=True, string='Optimized Trailer Count')
    estimated_cost_savings = fields.Float(compute='_compute_metrics', store=True, string='Estimated Cost Savings')
    estimated_co2_reduction_lbs = fields.Float(compute='_compute_metrics', store=True, string='Estimated CO₂ Reduction')
    recommended_trailer_preset_id = fields.Many2one('cargo.architect.trailer.preset', compute='_compute_metrics', store=True, string='Recommended Trailer')
    trailer_selection_summary = fields.Char(compute='_compute_metrics', store=True, string='Trailer Selection Summary')
    business_intelligence_summary = fields.Char(compute='_compute_metrics', store=True, string='Business Intelligence Summary')
    trailer_preset_id = fields.Many2one('cargo.architect.trailer.preset', string='Trailer', required=True)
    picking_ids = fields.Many2many('stock.picking', string='Source Transfers')
    line_ids = fields.One2many('cargo.architect.load.line', 'plan_id', string='Load Items', copy=True)
    paste_load_items_text = fields.Text(string='Paste Items', copy=False, help='Paste lines such as P001-008 (1 pallet, 24 items each). First quantity is pallet count; optional second quantity is items per pallet.')
    placement_ids = fields.One2many('cargo.architect.placement', 'plan_id', string='Placements', copy=False)
    optimization_mode = fields.Selection([
        ('balanced', 'Balanced'),
        ('cube', 'Max Cube Utilization'),
        ('weight', 'Best Weight Balance'),
        ('front', 'Front-First Loading'),
    ], default='balanced', string='Optimization Mode')
    manual_edit_summary = fields.Char(compute='_compute_metrics', store=True, string='Manual Edit / Lock Summary')
    multi_trailer_plan_summary = fields.Char(compute='_compute_metrics', store=True, string='Multi-Trailer Plan Summary')
    placement_undo_stack_json = fields.Text(string='Placement Undo Stack', default='[]', copy=False)
    placement_redo_stack_json = fields.Text(string='Placement Redo Stack', default='[]', copy=False)

    length_in = fields.Float(related='trailer_preset_id.length_in', store=True, readonly=False)
    width_in = fields.Float(related='trailer_preset_id.width_in', store=True, readonly=False)
    height_in = fields.Float(related='trailer_preset_id.height_in', store=True, readonly=False)
    max_payload_lbs = fields.Float(related='trailer_preset_id.max_payload_lbs', store=True, readonly=False)

    total_weight_lbs = fields.Float(compute='_compute_metrics', store=True)
    loaded_qty = fields.Integer(compute='_compute_metrics', store=True)
    requested_qty = fields.Integer(compute='_compute_metrics', store=True)
    total_pallet_qty = fields.Integer(compute='_compute_metrics', store=True, string='Total Pallets')
    loaded_pallet_qty = fields.Integer(compute='_compute_metrics', store=True, string='Loaded Pallets')
    total_inventory_item_qty = fields.Integer(compute='_compute_metrics', store=True, string='Total Items')
    loaded_inventory_item_qty = fields.Integer(compute='_compute_metrics', store=True, string='Loaded Items')
    lines_missing_items_per_pallet = fields.Integer(compute='_compute_metrics', store=True, string='Lines Missing Items / Pallet')
    item_quantity_summary = fields.Char(compute='_compute_metrics', store=True, string='Item Quantity Summary')
    cube_utilization = fields.Float(compute='_compute_metrics', store=True)
    floor_utilization = fields.Float(compute='_compute_metrics', store=True)
    free_cube_ft3 = fields.Float(compute='_compute_metrics', store=True, string='Free Cube (ft³)')
    remaining_payload_lbs = fields.Float(compute='_compute_metrics', store=True, string='Remaining Payload')
    floor_load_lbs_sqft = fields.Float(compute='_compute_metrics', store=True, string='Floor Load lb/sq ft')
    load_stability_status = fields.Selection([('pass', 'PASS'), ('warning', 'WARNING'), ('fail', 'FAIL')], compute='_compute_metrics', store=True, string='Stability Status')
    capacity_summary = fields.Char(compute='_compute_metrics', store=True, string='Capacity Summary')
    load_sequence_summary = fields.Text(compute='_compute_warehouse_operations', store=True, string='Load Sequence')
    unload_sequence_summary = fields.Text(compute='_compute_warehouse_operations', store=True, string='Unload Sequence')
    loading_instructions = fields.Text(compute='_compute_warehouse_operations', store=True, string='Loading Instructions')
    forklift_accessibility_status = fields.Char(compute='_compute_warehouse_operations', store=True, string='Forklift Accessibility')
    qr_load_passport_url = fields.Char(compute='_compute_warehouse_operations', store=True, string='QR Load Passport URL')
    load_quality_score = fields.Float(compute='_compute_metrics', store=True)
    utilization_score = fields.Float(compute='_compute_metrics', store=True, string='Utilization Score')
    weight_balance_score = fields.Float(compute='_compute_metrics', store=True, string='Weight Balance Score')
    axle_score = fields.Float(compute='_compute_metrics', store=True, string='Axle Score')
    stability_score = fields.Float(compute='_compute_metrics', store=True, string='Stability Score')
    lateral_cog_offset_in = fields.Float(compute='_compute_metrics', store=True, string='Lateral COG Offset')
    vertical_cog_in = fields.Float(compute='_compute_metrics', store=True, string='Vertical COG')
    static_stability_factor = fields.Float(compute='_compute_metrics', store=True, string='Estimated Static Stability Factor')
    stability_reason_summary = fields.Char(compute='_compute_metrics', store=True, string='Stability Basis')
    securement_status = fields.Selection([('pass', 'PASS'), ('warning', 'WARNING'), ('fail', 'FAIL')], compute='_compute_metrics', store=True, string='Securement Status')
    cargo_shift_risk = fields.Selection([('very_low', 'Very Low'), ('low', 'Low'), ('moderate', 'Moderate'), ('high', 'High'), ('critical', 'Critical')], compute='_compute_metrics', store=True, string='Cargo Shift Risk')
    void_space_summary = fields.Char(compute='_compute_metrics', store=True, string='Void Space Summary')
    largest_void_ft3 = fields.Float(compute='_compute_metrics', store=True, string='Largest Estimated Void')
    recommended_strap_count = fields.Integer(compute='_compute_metrics', store=True, string='Recommended Straps')
    recommended_load_bar_count = fields.Integer(compute='_compute_metrics', store=True, string='Recommended Load Bars')
    blocking_recommendations = fields.Text(compute='_compute_metrics', store=True, string='Blocking Recommendations')
    securement_reason_summary = fields.Char(compute='_compute_metrics', store=True, string='Securement Basis')
    securement_score = fields.Float(compute='_compute_metrics', store=True, string='Securement Score')
    void_front_pct = fields.Float(compute='_compute_metrics', store=True, string='Front Void %')
    void_center_pct = fields.Float(compute='_compute_metrics', store=True, string='Center Void %')
    void_rear_pct = fields.Float(compute='_compute_metrics', store=True, string='Rear Void %')
    void_left_pct = fields.Float(compute='_compute_metrics', store=True, string='Left Void %')
    void_right_pct = fields.Float(compute='_compute_metrics', store=True, string='Right Void %')
    recommended_blocking_points = fields.Integer(compute='_compute_metrics', store=True, string='Recommended Blocking Points')
    fit_status = fields.Selection([('pass', 'PASS'), ('warning', 'WARNING'), ('fail', 'FAIL')], compute='_compute_metrics', store=True)
    weight_status = fields.Selection([('pass', 'PASS'), ('warning', 'WARNING'), ('fail', 'FAIL')], compute='_compute_metrics', store=True)
    axle_status = fields.Selection([('pass', 'PASS'), ('warning', 'WARNING'), ('fail', 'FAIL')], compute='_compute_metrics', store=True)
    overall_status = fields.Selection([('pass', 'PASS'), ('warning', 'WARNING'), ('fail', 'FAIL')], compute='_compute_metrics', store=True)
    center_of_gravity_in = fields.Float(compute='_compute_metrics', store=True)
    front_quarter_lbs = fields.Float(compute='_compute_metrics', store=True, string='Front 0-25% Weight')
    front_mid_lbs = fields.Float(compute='_compute_metrics', store=True, string='Front-Mid 25-50% Weight')
    rear_mid_lbs = fields.Float(compute='_compute_metrics', store=True, string='Rear-Mid 50-75% Weight')
    rear_quarter_lbs = fields.Float(compute='_compute_metrics', store=True, string='Rear 75-100% Weight')
    front_half_lbs = fields.Float(compute='_compute_metrics', store=True, string='Front Half Weight')
    rear_half_lbs = fields.Float(compute='_compute_metrics', store=True, string='Rear Half Weight')
    left_side_lbs = fields.Float(compute='_compute_metrics', store=True, string='Left Side Weight')
    right_side_lbs = fields.Float(compute='_compute_metrics', store=True, string='Right Side Weight')
    side_balance_delta_lbs = fields.Float(compute='_compute_metrics', store=True, string='Side Balance Difference')
    side_balance_score = fields.Float(compute='_compute_metrics', store=True, string='Side Balance Score')
    side_balance_status = fields.Selection([('pass', 'PASS'), ('warning', 'WARNING'), ('fail', 'FAIL')], compute='_compute_metrics', store=True, string='Side Balance Status')
    steer_axle_lbs = fields.Float(compute='_compute_metrics', store=True)
    drive_axle_lbs = fields.Float(compute='_compute_metrics', store=True)
    trailer_axle_lbs = fields.Float(compute='_compute_metrics', store=True)
    placement_json = fields.Text(copy=False, default='[]')
    unplaced_json = fields.Text(copy=False, default='{}')
    unplaced_warning = fields.Char(compute='_compute_unplaced_warning', store=False)
    has_unplaced_items = fields.Boolean(compute='_compute_unplaced_warning', store=False)

    show_company_logo = fields.Boolean(string='Show Company Logo on Report', default=True)
    show_company_name = fields.Boolean(string='Show Company Name on Report', default=True)
    show_company_address = fields.Boolean(string='Show Company Address on Report', default=True)


    def ca_report_option(self, option_name, default=True):
        """Return a global Cargo Architect report option from Settings.

        Options are persisted as ir.config_parameter records. Missing values
        return the supplied default, but explicit False values must remain False
        so unchecked settings actually hide report header/footer sections.
        """
        param = 'cargo_architect.report_%s' % option_name
        value = self.env['ir.config_parameter'].sudo().get_param(param)
        if value in (None, ''):
            return bool(default)
        if value is False:
            return False
        return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 'on')

    def ca_app_version_label(self):
        return CARGO_ARCHITECT_APP_VERSION

    def ca_module_version_label(self):
        return CARGO_ARCHITECT_MODULE_VERSION

    def _status_rank(self, status):
        return {'pass': 0, 'warning': 1, 'fail': 2}.get(status or 'pass', 0)

    def _worst_status(self, *statuses):
        rank_map = {'pass': 0, 'warning': 1, 'fail': 2}
        reverse = {0: 'pass', 1: 'warning', 2: 'fail'}
        return reverse.get(max(rank_map.get(s or 'pass', 0) for s in statuses), 'pass')

    def _analyze_real_world_stability(self, total_weight, left_side, right_side, loaded_ratio, fit_status):
        """Return physics-inspired cargo stability indicators.

        This is still an engineering planning estimate, not a certified vehicle
        dynamics calculation. It replaces the older purely heuristic stability
        flag with practical thresholds based on side imbalance, lateral COG
        offset, vertical COG, rollover margin, and stack support.
        """
        self.ensure_one()
        total_weight = total_weight or 0.0
        width = self.width_in or 0.0
        height = self.height_in or 0.0
        reasons = []
        score = 100.0
        status = 'pass'

        side_delta_pct = abs(left_side - right_side) / total_weight * 100.0 if total_weight else 0.0
        if side_delta_pct > 15.0:
            status = self._worst_status(status, 'fail')
            reasons.append(_('Side imbalance %.1f%% exceeds 15%% fail threshold') % side_delta_pct)
            score -= 35.0
        elif side_delta_pct > 10.0:
            status = self._worst_status(status, 'warning')
            reasons.append(_('Side imbalance %.1f%% exceeds 10%% warning threshold') % side_delta_pct)
            score -= 18.0
        elif side_delta_pct > 5.0:
            reasons.append(_('Side imbalance %.1f%% is above preferred 5%% target') % side_delta_pct)
            score -= 7.0

        x_moment = y_moment = z_moment = 0.0
        for placement in self.placement_ids:
            weight = self._placement_weight_lbs(placement)
            x_moment += weight * (placement.x_in + placement.length_in / 2.0)
            y_moment += weight * (placement.y_in + placement.width_in / 2.0)
            z_moment += weight * (placement.z_in + placement.height_in / 2.0)
        lateral_cog = y_moment / total_weight if total_weight else (width / 2.0 if width else 0.0)
        lateral_offset = abs(lateral_cog - (width / 2.0)) if width else 0.0
        lateral_offset_pct = lateral_offset / width * 100.0 if width else 0.0
        vertical_cog = z_moment / total_weight if total_weight else 0.0
        ssf = (width / (2.0 * vertical_cog)) if width and vertical_cog else 0.0

        if lateral_offset_pct > 10.0:
            status = self._worst_status(status, 'fail')
            reasons.append(_('Lateral COG offset %.1f in (%.1f%% of width) exceeds 10%% fail threshold') % (lateral_offset, lateral_offset_pct))
            score -= 30.0
        elif lateral_offset_pct > 5.0:
            status = self._worst_status(status, 'warning')
            reasons.append(_('Lateral COG offset %.1f in (%.1f%% of width) exceeds 5%% warning threshold') % (lateral_offset, lateral_offset_pct))
            score -= 15.0

        if ssf and ssf < 0.85:
            status = self._worst_status(status, 'fail')
            reasons.append(_('Estimated static stability factor %.2f is below 0.85 fail threshold') % ssf)
            score -= 30.0
        elif ssf and ssf < 1.10:
            status = self._worst_status(status, 'warning')
            reasons.append(_('Estimated static stability factor %.2f is below 1.10 warning threshold') % ssf)
            score -= 15.0

        if height and vertical_cog > height * 0.65:
            status = self._worst_status(status, 'fail')
            reasons.append(_('Vertical COG %.1f in is above 65%% of trailer height') % vertical_cog)
            score -= 25.0
        elif height and vertical_cog > height * 0.50:
            status = self._worst_status(status, 'warning')
            reasons.append(_('Vertical COG %.1f in is above 50%% of trailer height') % vertical_cog)
            score -= 10.0

        # Stack support checks: items above floor need broad direct support below.
        worst_support = 100.0
        heavy_stack_warning = False
        placements = list(self.placement_ids)
        for upper in placements:
            if (upper.z_in or 0.0) <= 0.01:
                continue
            upper_area = max((upper.length_in or 0.0) * (upper.width_in or 0.0), 0.0)
            if not upper_area:
                continue
            support_area = 0.0
            support_weight = 0.0
            for lower in placements:
                lower_top = (lower.z_in or 0.0) + (lower.height_in or 0.0)
                if abs(lower_top - (upper.z_in or 0.0)) > 1.0:
                    continue
                ox = max(0.0, min((upper.x_in or 0.0) + (upper.length_in or 0.0), (lower.x_in or 0.0) + (lower.length_in or 0.0)) - max((upper.x_in or 0.0), (lower.x_in or 0.0)))
                oy = max(0.0, min((upper.y_in or 0.0) + (upper.width_in or 0.0), (lower.y_in or 0.0) + (lower.width_in or 0.0)) - max((upper.y_in or 0.0), (lower.y_in or 0.0)))
                area = ox * oy
                if area > 0.0:
                    support_area += area
                    support_weight += self._placement_weight_lbs(lower) * min(1.0, area / max((lower.length_in or 0.0) * (lower.width_in or 0.0), 1.0))
            support_pct = min(100.0, support_area / upper_area * 100.0)
            worst_support = min(worst_support, support_pct)
            if support_pct < 70.0:
                status = self._worst_status(status, 'fail')
                score -= 30.0
            elif support_pct < 85.0:
                status = self._worst_status(status, 'warning')
                score -= 12.0
            if support_weight and self._placement_weight_lbs(upper) > support_weight * 1.25:
                heavy_stack_warning = True
        if worst_support < 70.0:
            reasons.append(_('Stack support %.1f%% is below 70%% fail threshold') % worst_support)
        elif worst_support < 85.0:
            reasons.append(_('Stack support %.1f%% is below preferred 85%% target') % worst_support)
        if heavy_stack_warning:
            status = self._worst_status(status, 'warning')
            reasons.append(_('One or more upper items are heavier than the directly supported base area'))
            score -= 8.0

        if fit_status == 'fail' or loaded_ratio < 100.0:
            status = self._worst_status(status, 'fail')
            reasons.append(_('Fit is incomplete; stability cannot pass until all requested items are placed'))
            score = min(score, 60.0)

        if not reasons:
            reasons.append(_('Side balance, lateral COG, vertical COG, rollover margin, and stack support are within planning thresholds'))
        return {
            'status': status,
            'score': max(0.0, min(100.0, score)),
            'lateral_offset_in': lateral_offset,
            'vertical_cog_in': vertical_cog,
            'ssf': ssf,
            'summary': '; '.join(str(r) for r in reasons[:4]),
        }

    @api.depends('state', 'line_ids.quantity', 'line_ids.length_in', 'line_ids.width_in', 'line_ids.height_in', 'placement_ids', 'unplaced_json', 'total_weight_lbs', 'max_payload_lbs', 'steer_axle_lbs', 'drive_axle_lbs', 'trailer_axle_lbs')
    def _compute_approval_status(self):
        for plan in self:
            blocker = ''
            if not plan.line_ids:
                blocker = _('No load items have been added.')
            elif any((line.length_in or 0.0) <= 0.0 or (line.width_in or 0.0) <= 0.0 or (line.height_in or 0.0) <= 0.0 or (line.quantity or 0) <= 0 for line in plan.line_ids):
                blocker = _('One or more load lines are missing dimensions or quantity.')
            elif not plan.placement_ids:
                blocker = _('Optimize the layout before approval.')
            elif plan._get_unplaced_dict():
                blocker = plan.get_unplaced_warning_message()
            elif plan.max_payload_lbs and plan.total_weight_lbs > plan.max_payload_lbs:
                blocker = _('Load exceeds max trailer payload by %.1f lb.') % (plan.total_weight_lbs - plan.max_payload_lbs)
            elif plan.steer_axle_lbs > 12000:
                blocker = _('Steer axle exceeds the planning limit.')
            elif plan.drive_axle_lbs > 34000:
                blocker = _('Drive axles exceed the planning limit.')
            elif plan.trailer_axle_lbs > 34000:
                blocker = _('Trailer axles exceed the planning limit.')
            plan.approval_blocker = blocker
            plan.can_approve_load = not bool(blocker)

    @api.depends('unplaced_json')
    def _compute_unplaced_warning(self):
        for plan in self:
            unplaced = plan._get_unplaced_dict()
            plan.has_unplaced_items = bool(unplaced)
            if unplaced:
                details = ', '.join('%s: %s' % (name, qty) for name, qty in sorted(unplaced.items()))
                plan.unplaced_warning = _('Not all items fit: %s') % details
            else:
                plan.unplaced_warning = ''

    @api.depends('placement_ids.name', 'placement_ids.x_in', 'placement_ids.y_in', 'placement_ids.z_in', 'placement_ids.length_in', 'placement_ids.width_in', 'placement_ids.height_in', 'placement_ids.weight_lbs', 'line_ids.name', 'state')
    def _compute_warehouse_operations(self):
        """Compute v1.3.0 warehouse operation summaries.

        These fields are intentionally computed from placements so reports and
        forms stay synchronized whenever a load is re-optimized.
        """
        for plan in self:
            load_rows = plan.get_load_sequence_rows()
            unload_rows = plan.get_unload_sequence_rows()
            accessible_rows = plan.get_forklift_accessibility_rows()
            plan.load_sequence_summary = '\n'.join('%s. %s - %s' % (
                row.get('sequence'), row.get('name'), row.get('display_position')) for row in load_rows[:50])
            plan.unload_sequence_summary = '\n'.join('%s. %s - unload from rear access' % (
                row.get('sequence'), row.get('name')) for row in unload_rows[:50])
            plan.loading_instructions = plan._build_loading_instructions(load_rows, accessible_rows)
            accessible_count = len([r for r in accessible_rows if r.get('accessible')])
            total_count = len(accessible_rows)
            if not total_count:
                plan.forklift_accessibility_status = _('No optimized placements available.')
            elif accessible_count == total_count:
                plan.forklift_accessibility_status = _('PASS - %s of %s items are forklift accessible.') % (accessible_count, total_count)
            else:
                plan.forklift_accessibility_status = _('REVIEW - %s of %s items are directly accessible from the rear.') % (accessible_count, total_count)
            plan.qr_load_passport_url = plan._get_load_passport_url()

    def _split_weight_left_right(self, y_in, width_in, weight_lbs):
        """Return (left_weight, right_weight) by footprint overlap, not center point.

        Prior releases assigned the full item weight to whichever side contained
        the item's centerline. Wide items placed from Y=0 could span both sides
        but still count as 100% left-side weight, which made side-balance reports
        show Right Side = 0% and prevented Best Balance from scoring lanes
        correctly.  This prorates weight by the item's actual width overlap.
        """
        width = float(width_in or 0.0)
        weight = float(weight_lbs or 0.0)
        if width <= 0.0 or weight <= 0.0:
            return 0.0, 0.0
        trailer_width = float(self.width_in or 0.0)
        half_width = trailer_width / 2.0
        y0 = max(0.0, float(y_in or 0.0))
        y1 = min(trailer_width, y0 + width) if trailer_width else y0 + width
        left_overlap = max(0.0, min(y1, half_width) - min(max(y0, 0.0), half_width)) if trailer_width else width
        right_overlap = max(0.0, y1 - max(y0, half_width)) if trailer_width else 0.0
        covered = left_overlap + right_overlap
        if covered <= 0.0:
            return weight, 0.0
        return weight * (left_overlap / covered), weight * (right_overlap / covered)

    @api.depends('line_ids.quantity', 'line_ids.items_per_pallet', 'line_ids.weight_lbs', 'line_ids.product_id.weight', 'line_ids.product_preset_id.weight_lbs', 'placement_ids.weight_lbs', 'placement_ids.locked', 'optimization_mode', 'placement_ids.line_id.weight_lbs', 'placement_ids.length_in', 'placement_ids.width_in', 'placement_ids.height_in', 'placement_ids.x_in', 'placement_ids.y_in', 'placement_ids.z_in', 'max_payload_lbs', 'unplaced_json', 'baseline_trailer_count', 'freight_cost_per_trailer', 'loaded_miles', 'co2_lbs_per_mile')
    def _compute_metrics(self):
        for plan in self:
            requested = sum(plan.line_ids.mapped('quantity'))
            loaded = len(plan.placement_ids)
            total_pallet_qty = requested
            loaded_pallet_qty = loaded
            total_inventory_item_qty = sum(int(line.quantity or 0) * int(line.items_per_pallet or 0) for line in plan.line_ids if int(line.items_per_pallet or 0) > 0)
            # Loaded item count follows actual loaded placements, so partially loaded plans do not overstate sellable/unit quantity.
            loaded_inventory_item_qty = 0
            for placement in plan.placement_ids:
                line = placement.line_id
                if line and int(line.items_per_pallet or 0) > 0:
                    loaded_inventory_item_qty += int(line.items_per_pallet or 0)
            lines_missing_items_per_pallet = sum(1 for line in plan.line_ids if not int(line.items_per_pallet or 0))
            if total_inventory_item_qty:
                item_quantity_summary = _('%(loaded_items)s / %(total_items)s items loaded on %(loaded_pallets)s / %(total_pallets)s pallets.') % {
                    'loaded_items': loaded_inventory_item_qty,
                    'total_items': total_inventory_item_qty,
                    'loaded_pallets': loaded_pallet_qty,
                    'total_pallets': total_pallet_qty,
                }
            elif lines_missing_items_per_pallet:
                item_quantity_summary = _('%(loaded_pallets)s / %(total_pallets)s pallets loaded. Items / Pallet not entered for %(missing)s line(s).') % {
                    'loaded_pallets': loaded_pallet_qty,
                    'total_pallets': total_pallet_qty,
                    'missing': lines_missing_items_per_pallet,
                }
            else:
                item_quantity_summary = _('%(loaded_pallets)s / %(total_pallets)s pallets loaded.') % {'loaded_pallets': loaded_pallet_qty, 'total_pallets': total_pallet_qty}
            total_weight = sum(plan._placement_weight_lbs(p) for p in plan.placement_ids)
            used_cube = sum(p.length_in * p.width_in * p.height_in for p in plan.placement_ids)
            used_floor = sum(p.length_in * p.width_in for p in plan.placement_ids if p.z_in <= 0.01)
            container_cube = plan.length_in * plan.width_in * plan.height_in
            container_floor = plan.length_in * plan.width_in
            free_cube_ft3 = max(container_cube - used_cube, 0.0) / 1728.0 if container_cube else 0.0
            remaining_payload = (plan.max_payload_lbs or 0.0) - total_weight
            floor_load = total_weight / (container_floor / 144.0) if container_floor else 0.0
            cube_util = used_cube / container_cube * 100.0 if container_cube else 0.0
            floor_util = used_floor / container_floor * 100.0 if container_floor else 0.0
            moment = sum(plan._placement_weight_lbs(p) * (p.x_in + p.length_in / 2.0) for p in plan.placement_ids)
            cg = moment / total_weight if total_weight else 0.0
            zones = [0.0, 0.0, 0.0, 0.0]
            for placement in plan.placement_ids:
                center_x = placement.x_in + placement.length_in / 2.0
                zone_index = min(3, max(0, int((center_x / plan.length_in) * 4))) if plan.length_in else 0
                zones[zone_index] += plan._placement_weight_lbs(placement)
            stack_count = sum(1 for p in plan.placement_ids if p.z_in > 0.01)
            stack_eff = stack_count / loaded * 100.0 if loaded else 0.0
            loaded_ratio = loaded / requested * 100.0 if requested else 0.0
            steer, drive, trailer = plan._estimate_axles()

            utilization_score = max(0.0, min(100.0, min(cube_util, 100.0) * 0.65 + min(floor_util, 100.0) * 0.35))
            front_half = zones[0] + zones[1]
            rear_half = zones[2] + zones[3]
            left_side = 0.0
            right_side = 0.0
            for placement in plan.placement_ids:
                weight = plan._placement_weight_lbs(placement)
                left_part, right_part = plan._split_weight_left_right(placement.y_in, placement.width_in, weight)
                left_side += left_part
                right_side += right_part
            front_rear_delta = abs(front_half - rear_half) / total_weight * 100.0 if total_weight else 0.0
            side_delta_pct = abs(left_side - right_side) / total_weight * 100.0 if total_weight else 0.0
            side_delta_lbs = abs(left_side - right_side)
            front_rear_score = max(0.0, min(100.0, 100.0 - (front_rear_delta * 1.7)))
            side_balance_score = max(0.0, min(100.0, 100.0 - (side_delta_pct * 2.2)))
            weight_balance_score = max(0.0, min(100.0, front_rear_score * 0.70 + side_balance_score * 0.30))
            if side_delta_pct > 30.0:
                side_balance_status = 'fail'
            elif side_delta_pct > 15.0:
                side_balance_status = 'warning'
            else:
                side_balance_status = 'pass'
            axle_utils = [
                (steer / 12000.0 * 100.0) if steer else 0.0,
                (drive / 34000.0 * 100.0) if drive else 0.0,
                (trailer / 34000.0 * 100.0) if trailer else 0.0,
            ]
            worst_axle_util = max(axle_utils) if axle_utils else 0.0
            axle_score = max(0.0, min(100.0, 100.0 - max(0.0, worst_axle_util - 85.0) * 2.0))
            unplaced = plan._get_unplaced_dict()

            fit_status = 'fail' if unplaced else ('warning' if loaded_ratio < 100.0 else 'pass')
            if plan.max_payload_lbs and total_weight > plan.max_payload_lbs:
                weight_status = 'fail'
            elif plan.max_payload_lbs and total_weight > plan.max_payload_lbs * 0.92:
                weight_status = 'warning'
            else:
                weight_status = 'pass'
            if steer > 12000 or drive > 34000 or trailer > 34000:
                axle_status = 'fail'
            elif worst_axle_util > 92.0:
                axle_status = 'warning'
            else:
                axle_status = 'pass'

            stability_analysis = plan._analyze_real_world_stability(total_weight, left_side, right_side, loaded_ratio, fit_status)
            stability_score = stability_analysis['score']
            stability_status = stability_analysis['status']
            securement_analysis = plan._analyze_cargo_securement(total_weight, free_cube_ft3, floor_util, side_delta_pct, stack_count, loaded, stability_status)
            quality = max(0.0, min(100.0, utilization_score * 0.35 + weight_balance_score * 0.25 + axle_score * 0.25 + stability_score * 0.15))

            if unplaced:
                missing = ', '.join('%s x %s' % (qty, name) for name, qty in sorted(unplaced.items())[:4])
                extra = '...' if len(unplaced) > 4 else ''
                capacity_summary = _('Review required: not all items fit (%s%s).') % (missing, extra)
            elif remaining_payload < 0:
                capacity_summary = _('Over payload by %.1f lb.') % abs(remaining_payload)
            else:
                capacity_summary = _('Available: %.1f ft³ free, %.1f lb payload remaining.') % (free_cube_ft3, max(remaining_payload, 0.0))

            # Overall status is a compliance status, not an optimization-quality status.
            # Balance/stability advisories can lower the Load Quality score, but they
            # should not force OVERALL WARNING when all hard loading constraints pass.
            hard_statuses = (fit_status, weight_status, axle_status)
            if 'fail' in hard_statuses or stability_status == 'fail':
                overall_status = 'fail'
            elif 'warning' in hard_statuses:
                overall_status = 'warning'
            else:
                overall_status = 'pass'

            plan.requested_qty = requested
            plan.loaded_qty = loaded
            plan.total_pallet_qty = total_pallet_qty
            plan.loaded_pallet_qty = loaded_pallet_qty
            plan.total_inventory_item_qty = total_inventory_item_qty
            plan.loaded_inventory_item_qty = loaded_inventory_item_qty
            plan.lines_missing_items_per_pallet = lines_missing_items_per_pallet
            plan.item_quantity_summary = item_quantity_summary
            plan.total_weight_lbs = total_weight
            plan.cube_utilization = cube_util
            plan.floor_utilization = floor_util
            plan.free_cube_ft3 = free_cube_ft3
            plan.remaining_payload_lbs = remaining_payload
            plan.floor_load_lbs_sqft = floor_load
            plan.load_stability_status = stability_status
            plan.capacity_summary = capacity_summary
            plan.load_quality_score = quality
            plan.utilization_score = utilization_score
            plan.weight_balance_score = weight_balance_score
            plan.axle_score = axle_score
            plan.stability_score = stability_score
            plan.lateral_cog_offset_in = stability_analysis['lateral_offset_in']
            plan.vertical_cog_in = stability_analysis['vertical_cog_in']
            plan.static_stability_factor = stability_analysis['ssf']
            plan.stability_reason_summary = stability_analysis['summary']
            plan.securement_status = securement_analysis['status']
            plan.cargo_shift_risk = securement_analysis['risk']
            plan.void_space_summary = securement_analysis['void_summary']
            plan.largest_void_ft3 = securement_analysis['largest_void_ft3']
            plan.recommended_strap_count = securement_analysis['strap_count']
            plan.recommended_load_bar_count = securement_analysis['load_bar_count']
            plan.blocking_recommendations = securement_analysis['blocking']
            plan.securement_reason_summary = securement_analysis['summary']
            plan.securement_score = securement_analysis.get('securement_score', 100.0)
            plan.void_front_pct = securement_analysis.get('void_front_pct', 0.0)
            plan.void_center_pct = securement_analysis.get('void_center_pct', 0.0)
            plan.void_rear_pct = securement_analysis.get('void_rear_pct', 0.0)
            plan.void_left_pct = securement_analysis.get('void_left_pct', 0.0)
            plan.void_right_pct = securement_analysis.get('void_right_pct', 0.0)
            plan.recommended_blocking_points = securement_analysis.get('blocking_points', 0)
            plan.fit_status = fit_status
            plan.weight_status = weight_status
            plan.axle_status = axle_status
            plan.overall_status = overall_status
            plan.center_of_gravity_in = cg
            plan.front_quarter_lbs = zones[0]
            plan.front_mid_lbs = zones[1]
            plan.rear_mid_lbs = zones[2]
            plan.rear_quarter_lbs = zones[3]
            plan.front_half_lbs = zones[0] + zones[1]
            plan.rear_half_lbs = zones[2] + zones[3]
            plan.left_side_lbs = left_side
            plan.right_side_lbs = right_side
            plan.side_balance_delta_lbs = side_delta_lbs
            plan.side_balance_score = side_balance_score
            plan.side_balance_status = side_balance_status
            plan.steer_axle_lbs = steer
            plan.drive_axle_lbs = drive
            plan.trailer_axle_lbs = trailer
            optimized_trailers = plan._estimate_optimized_trailer_count(requested, loaded)
            baseline_trailers = max(plan.baseline_trailer_count or 1, optimized_trailers or 1)
            trailers_saved = max(baseline_trailers - optimized_trailers, 0)
            plan.optimized_trailer_count = optimized_trailers
            plan.estimated_cost_savings = trailers_saved * (plan.freight_cost_per_trailer or 0.0)
            plan.estimated_co2_reduction_lbs = trailers_saved * (plan.loaded_miles or 0.0) * (plan.co2_lbs_per_mile or 0.0)
            recommended = plan._recommended_trailer_preset(used_cube, total_weight, requested_qty=requested)
            plan.recommended_trailer_preset_id = recommended.id if recommended else False
            if recommended and recommended != plan.trailer_preset_id:
                plan.trailer_selection_summary = _('Recommended trailer: %s') % recommended.display_name
            elif recommended:
                plan.trailer_selection_summary = _('Current trailer is appropriate for this load.')
            else:
                plan.trailer_selection_summary = _('No trailer recommendation available.')
            plan.business_intelligence_summary = _('Estimated savings: $ %(cost).2f; CO₂ reduction: %(co2).1f lb; optimized trailers: %(trailers)s.') % {
                'cost': plan.estimated_cost_savings or 0.0,
                'co2': plan.estimated_co2_reduction_lbs or 0.0,
                'trailers': optimized_trailers,
            }
            locked_count = len(plan.placement_ids.filtered('locked'))
            plan.manual_edit_summary = _('%s locked placement(s). Optimizer will preserve locked positions.') % locked_count if locked_count else _('No locked placements.')
            plan.multi_trailer_plan_summary = _('Estimated %s trailer(s) required for current requested load. Baseline: %s.') % (optimized_trailers, baseline_trailers)

    def _estimate_optimized_trailer_count(self, total_requested, loaded):
        self.ensure_one()
        if not total_requested:
            return 0
        if loaded <= 0:
            return max(1, self.baseline_trailer_count or 1)
        if loaded >= total_requested:
            return 1
        import math
        return max(1, int(math.ceil(float(total_requested) / float(loaded))))

    def _recommended_trailer_preset(self, used_cube, total_weight, requested_qty=None):
        """Return the smallest trailer preset that is proven to fit.

        v2.0.9 fixes the previous cube-only recommendation behavior.  A
        trailer is now eligible only when the physical packing simulation can
        place every requested item and the payload limit passes.  This prevents
        reports from recommending a 48 ft dry van only because the load has
        enough theoretical cube when the real row/width/stack pattern cannot
        fit in that trailer.
        """
        self.ensure_one()
        rows = self.get_trailer_evaluation_rows(used_cube=used_cube, total_weight=total_weight, requested_qty=requested_qty)
        passing = [row for row in rows if row.get('fits_all')]
        if not passing:
            # Keep the current trailer as the safest fallback only if the actual
            # optimized layout already loaded all requested pieces.
            if self.trailer_preset_id and (self.requested_qty or 0) and (self.loaded_qty or 0) >= (self.requested_qty or 0):
                return self.trailer_preset_id
            return False
        passing.sort(key=lambda row: (row.get('cube_in3') or 0.0, row.get('length_in') or 0.0))
        return self.env['cargo.architect.trailer.preset'].browse(passing[0].get('trailer_id'))

    def get_trailer_evaluation_rows(self, used_cube=None, total_weight=None, requested_qty=None):
        """Evaluate each trailer by simulated physical fit, not cube alone.

        The matrix is intentionally conservative: if the simulator cannot place
        every item, the trailer is marked FAIL and is not recommended.  The
        current trailer can use the actual optimized placement result, so a
        known-good current plan remains eligible.
        """
        self.ensure_one()
        Trailer = self.env['cargo.architect.trailer.preset']
        domain = [('active', '=', True)] if 'active' in Trailer._fields else []
        trailers = Trailer.search(domain)
        used_cube = float(used_cube if used_cube is not None else sum(
            (p.length_in or 0.0) * (p.width_in or 0.0) * (p.height_in or 0.0)
            for p in self.placement_ids
        ))
        total_weight = float(total_weight if total_weight is not None else (self.total_weight_lbs or 0.0))
        requested_qty = int(requested_qty if requested_qty is not None else (self.requested_qty or sum(max(0, l.quantity) for l in self.line_ids)))
        rows = []
        for trailer in trailers:
            cube = (trailer.length_in or 0.0) * (trailer.width_in or 0.0) * (trailer.height_in or 0.0)
            payload_ok = (trailer.max_payload_lbs or 0.0) >= total_weight
            if trailer == self.trailer_preset_id and requested_qty and (self.loaded_qty or 0) >= requested_qty and payload_ok:
                loaded = self.loaded_qty or requested_qty
                unplaced = 0
                fits_all = True
                used_len = max([(p.x_in or 0.0) + (p.length_in or 0.0) for p in self.placement_ids] or [0.0])
                used_height = max([(p.z_in or 0.0) + (p.height_in or 0.0) for p in self.placement_ids] or [0.0])
                score = self.load_quality_score or 0.0
            else:
                sim = self._simulate_trailer_fit_for_recommendation(trailer, total_weight)
                loaded = sim.get('loaded_qty', 0)
                unplaced = max(requested_qty - loaded, 0)
                fits_all = bool(payload_ok and requested_qty and loaded >= requested_qty)
                used_len = sim.get('used_length_in') or 0.0
                used_height = sim.get('used_height_in') or 0.0
                score = sim.get('score') or 0.0
            empty_cube = max(cube - used_cube, 0.0) if fits_all else 0.0
            if not payload_ok:
                status = _('FAIL - Payload')
            elif fits_all:
                status = _('PASS')
            else:
                status = _('FAIL - Fit')
            rows.append({
                'trailer_id': trailer.id,
                'name': trailer.display_name,
                'fits_all': fits_all,
                'status': status,
                'loaded_qty': loaded,
                'requested_qty': requested_qty,
                'unplaced_qty': unplaced,
                'empty_cube_ft3': empty_cube / 1728.0 if fits_all else 0.0,
                'score': score,
                'length_in': trailer.length_in or 0.0,
                'cube_in3': cube,
                'used_length_in': used_len,
                'used_height_in': used_height,
            })
        rows.sort(key=lambda row: (not row.get('fits_all'), row.get('cube_in3') or 0.0, row.get('length_in') or 0.0))
        return rows

    def _simulate_trailer_fit_for_recommendation(self, trailer, total_weight=0.0):
        """Conservative non-persistent fit simulation for trailer selection.

        This does not create or alter placement records. It mirrors the normal
        planner's core constraints: rotations, bounds, collision checks, basic
        support for stacked items, and Best Fill / level-load candidate scoring.
        """
        self.ensure_one()
        length_in = float(trailer.length_in or 0.0)
        width_in = float(trailer.width_in or 0.0)
        height_in = float(trailer.height_in or 0.0)
        if length_in <= 0.0 or width_in <= 0.0 or height_in <= 0.0:
            return {'loaded_qty': 0, 'used_length_in': 0.0, 'used_height_in': 0.0, 'score': 0.0}

        items = []
        for line in self.line_ids:
            for _i in range(max(0, int(line.quantity or 0))):
                items.append({
                    'length': float(line.length_in or 0.0),
                    'width': float(line.width_in or 0.0),
                    'height': float(line.height_in or 0.0),
                    'weight': float(line.weight_lbs or 0.0),
                    'allow_rotate': bool(line.allow_rotate),
                })
        mode = self.optimization_mode or 'balanced'
        if mode == 'cube':
            items.sort(key=lambda x: (x['length'] * x['width'] * x['height'], x['height'], x['weight']), reverse=True)
        elif mode == 'weight':
            items.sort(key=lambda x: (x['weight'], x['length'] * x['width'], x['height']), reverse=True)
        elif mode == 'front':
            items.sort(key=lambda x: (x['length'] * x['width'], x['height'], x['weight']), reverse=True)
        else:
            items.sort(key=lambda x: (x['height'], x['length'] * x['width'], x['weight']), reverse=True)

        placements = []

        def intersects(a, b):
            return not (
                a['x'] + a['length'] <= b['x'] + 0.001 or b['x'] + b['length'] <= a['x'] + 0.001 or
                a['y'] + a['width'] <= b['y'] + 0.001 or b['y'] + b['width'] <= a['y'] + 0.001 or
                a['z'] + a['height'] <= b['z'] + 0.001 or b['z'] + b['height'] <= a['z'] + 0.001
            )

        def supported(candidate):
            if candidate['z'] <= 0.01:
                return True
            footprint = candidate['length'] * candidate['width']
            if footprint <= 0.0:
                return False
            support = 0.0
            for p in placements:
                if abs((p['z'] + p['height']) - candidate['z']) <= 0.05:
                    ox = max(0.0, min(candidate['x'] + candidate['length'], p['x'] + p['length']) - max(candidate['x'], p['x']))
                    oy = max(0.0, min(candidate['y'] + candidate['width'], p['y'] + p['width']) - max(candidate['y'], p['y']))
                    support += ox * oy
            return support >= footprint * 0.55

        def axis_points(axis, size, trailer_size):
            points = {0.0}
            for p in placements:
                if axis == 'x':
                    points.add(round(p['x'], 3)); points.add(round(p['x'] + p['length'], 3))
                elif axis == 'y':
                    points.add(round(p['y'], 3)); points.add(round(p['y'] + p['width'], 3))
                else:
                    points.add(round(p['z'], 3)); points.add(round(p['z'] + p['height'], 3))
            return sorted(v for v in points if v >= -0.001 and v + size <= trailer_size + 0.001)

        def option_score(c):
            half_wid = width_in / 2.0
            centerline_distance = abs((c['y'] + c['width'] / 2.0) - half_wid)
            same_band = []
            for p in placements + [c]:
                overlap_x = max(0.0, min(c['x'] + c['length'], p['x'] + p['length']) - max(c['x'], p['x']))
                min_len = max(1.0, min(c['length'], p['length']))
                if overlap_x >= min_len * 0.45 and abs(c['z'] - p['z']) <= 0.05:
                    same_band.append((p['y'], p['y'] + p['width']))
            same_band.sort()
            merged = []
            for a, b in same_band:
                if not merged or a > merged[-1][1] + 0.25:
                    merged.append([a, b])
                else:
                    merged[-1][1] = max(merged[-1][1], b)
            occupied_width = sum(max(0.0, b - a) for a, b in merged)
            width_void = max(0.0, width_in - occupied_width) / width_in if width_in else 1.0
            tops = [p['z'] + p['height'] for p in placements + [c]]
            avg_top = sum(tops) / len(tops) if tops else 0.0
            level_penalty = (sum(abs(t - avg_top) for t in tops) / len(tops)) / max(height_in, 1.0) if len(tops) > 1 else 0.0
            return (c['z'], width_void, level_penalty, c['x'], centerline_distance, c['y'])

        for item in items:
            # v2.0.15: Always consider safe floor rotation during optimization.
            # The height is never changed, so this honors the Cargo Architect rule
            # that rotation may swap length/width only. Some imported lines/presets
            # were arriving with allow_rotate unchecked, which prevented pairable
            # cartons such as P001-010 from using two-across rows.
            rotations = [(item['length'], item['width'])]
            if abs(item['length'] - item['width']) > 0.01:
                rotations.append((item['width'], item['length']))
            valid = []
            for l, w in rotations:
                h = item['height']
                if l <= 0.0 or w <= 0.0 or h <= 0.0 or l > length_in + 0.001 or w > width_in + 0.001 or h > height_in + 0.001:
                    continue
                for z in axis_points('z', h, height_in):
                    for x in axis_points('x', l, length_in):
                        y_candidates = set(axis_points('y', w, width_in))
                        # Force consideration of centered and right-lane pairing
                        # positions so a narrow row is not the only tested option.
                        y_candidates.add(max(0.0, min(width_in - w, (width_in - w) / 2.0)))
                        y_candidates.add(max(0.0, width_in - w))
                        y_candidates.add(max(0.0, min(width_in - w, (width_in / 2.0) - w)))
                        y_candidates.add(max(0.0, min(width_in - w, width_in / 2.0)))
                        for y in sorted(y_candidates):
                            c = {'x': x, 'y': y, 'z': z, 'length': l, 'width': w, 'height': h, 'weight': item['weight']}
                            if c['x'] + l > length_in + 0.001 or c['y'] + w > width_in + 0.001 or c['z'] + h > height_in + 0.001:
                                continue
                            if not supported(c):
                                continue
                            if any(intersects(c, p) for p in placements):
                                continue
                            valid.append(c)
            if not valid:
                continue
            placements.append(sorted(valid, key=option_score)[0])

        loaded = len(placements)
        used_length = max([p['x'] + p['length'] for p in placements] or [0.0])
        used_height = max([p['z'] + p['height'] for p in placements] or [0.0])
        used_volume = sum(p['length'] * p['width'] * p['height'] for p in placements)
        trailer_volume = length_in * width_in * height_in
        fill_score = (used_volume / trailer_volume * 100.0) if trailer_volume else 0.0
        fit_score = (loaded / len(items) * 100.0) if items else 0.0
        score = (fit_score * 0.75) + (fill_score * 0.25)
        return {'loaded_qty': loaded, 'used_length_in': used_length, 'used_height_in': used_height, 'score': score}

    def get_business_intelligence_rows(self):
        self.ensure_one()
        optimized = self.optimized_trailer_count or 0
        baseline = self.baseline_trailer_count or 0
        saved = max(baseline - optimized, 0)
        return [
            {'label': _('Baseline Trailers'), 'value': baseline},
            {'label': _('Optimized Trailers'), 'value': optimized},
            {'label': _('Trailers Saved'), 'value': saved},
            {'label': _('Estimated Cost Savings'), 'value': '$ {:,.2f}'.format(self.estimated_cost_savings or 0.0)},
            {'label': _('Estimated CO₂ Reduction'), 'value': '{:,.1f} lb'.format(self.estimated_co2_reduction_lbs or 0.0)},
            {'label': _('Recommended Trailer'), 'value': self.recommended_trailer_preset_id.display_name if self.recommended_trailer_preset_id else _('No recommendation')},
            {'label': _('Selection Summary'), 'value': self.trailer_selection_summary or ''},
        ]

    def _estimate_axles(self):
        self.ensure_one()
        empty_steer = 11000.0
        empty_drive = 14000.0
        empty_trailer = 10000.0
        drive_payload = trailer_payload = 0.0
        fifth = self.trailer_preset_id.fifth_wheel_position_in or 36.0
        tandem = self.trailer_preset_id.trailer_axle_position_in or max(self.length_in - 120.0, self.length_in * 0.72)
        if tandem <= fifth:
            return empty_steer, empty_drive, empty_trailer
        for p in self.placement_ids:
            center_x = p.x_in + p.length_in / 2.0
            trailer_share = max(0.0, min(1.0, (center_x - fifth) / (tandem - fifth)))
            weight = self._placement_weight_lbs(p)
            trailer_payload += weight * trailer_share
            drive_payload += weight * (1.0 - trailer_share)
        return empty_steer, empty_drive + drive_payload, empty_trailer + trailer_payload

    def _get_picking_load_sources(self, picking):
        """Return stock records that can be imported from a picking.

        Odoo 19 deployments may not expose move_ids_without_package on
        stock.picking.  This helper supports multiple stock picking APIs:
        - move_ids_without_package, when available on older/alternate builds
        - move_ids / move_ids_without_package replacement fields
        - move_line_ids, as a final fallback
        """
        for field_name in ('move_ids_without_package', 'move_ids', 'move_ids_without_package_ids'):
            if field_name in picking._fields:
                records = picking[field_name]
                if records:
                    return records
        if 'move_line_ids' in picking._fields:
            return picking.move_line_ids
        return self.env['stock.move']

    def _get_stock_record_qty(self, record):
        """Read a usable quantity from either stock.move or stock.move.line."""
        for field_name in ('product_uom_qty', 'quantity', 'quantity_done', 'qty_done', 'reserved_uom_qty'):
            if field_name in record._fields:
                value = record[field_name]
                if value:
                    return value
        return 0.0


    def _product_weight_lbs(self, product):
        """Return product weight converted to pounds when Odoo stores kg.

        Odoo's standard product.weight is commonly stored in kg. Cargo Architect
        line/preset/report fields are in pounds, so use this only as a fallback
        when no Cargo Architect preset weight or load-line override exists.
        """
        if not product:
            return 0.0
        weight = getattr(product, 'weight', 0.0) or 0.0
        return weight * 2.2046226218 if weight else 0.0

    def _best_product_weight_lbs(self, product=False, preset=False, line_weight=0.0):
        """Weight priority: edited load-line weight, preset lb weight, product kg->lb."""
        if line_weight and line_weight > 0:
            return line_weight
        if preset and preset.weight_lbs and preset.weight_lbs > 0:
            return preset.weight_lbs
        return self._product_weight_lbs(product)


    def _placement_weight_lbs(self, placement):
        """Return placement weight with load-line/product fallback for older records."""
        if not placement:
            return 0.0
        if placement.weight_lbs and placement.weight_lbs > 0:
            return placement.weight_lbs
        line = placement.line_id
        if line:
            return self._best_product_weight_lbs(line.product_id, line.product_preset_id, line.weight_lbs or 0.0)
        return 0.0


    def _find_product_preset_for_product(self, product):
        """Find the best Cargo Architect preset for an Odoo product.

        Supports both variant-level and template-level preset assignments.
        Variant match wins; template match is used as fallback.
        """
        if not product:
            return self.env['cargo.architect.product.preset']
        Preset = self.env['cargo.architect.product.preset']
        preset = Preset.search([('product_id', '=', product.id), ('active', '=', True)], limit=1)
        if preset:
            return preset
        tmpl = getattr(product, 'product_tmpl_id', False)
        if tmpl:
            preset = Preset.search([('product_tmpl_id', '=', tmpl.id), ('active', '=', True)], limit=1)
            if preset:
                return preset
        # Final fallback: older data may not have active set explicitly.
        preset = Preset.search([('product_id', '=', product.id)], limit=1)
        if preset:
            return preset
        if tmpl:
            return Preset.search([('product_tmpl_id', '=', tmpl.id)], limit=1)
        return Preset

    def _line_values_from_product(self, product, qty=1.0):
        """Return load-line values using the product's assigned preset first."""
        preset = self._find_product_preset_for_product(product)
        return {
            'product_id': product.id,
            'product_preset_id': preset.id if preset else False,
            'name': product.display_name,
            'quantity': int(round(qty)) or 1,
            'length_in': preset.length_in if preset else 48.0,
            'width_in': preset.width_in if preset else 40.0,
            'height_in': preset.height_in if preset else 48.0,
            'weight_lbs': self._best_product_weight_lbs(product, preset),
            'allow_rotate': preset.allow_rotate if preset else True,
            'stackable': preset.stackable if preset else True,
            'max_stack': preset.max_stack if preset else 0,
        }


    def _find_product_or_preset_by_code(self, code):
        """Return (product, preset) for pasted item code.

        Matching is intentionally broad so warehouse-friendly codes like
        P001-008 can resolve against product internal reference, barcode,
        product name, or Cargo Architect product preset name.
        """
        code = (code or '').strip()
        if not code:
            return False, False
        Product = self.env['product.product']
        Preset = self.env['cargo.architect.product.preset']

        product = Product.search([('default_code', '=', code)], limit=1)
        if not product:
            product = Product.search([('barcode', '=', code)], limit=1)
        if not product:
            product = Product.search([('name', '=', code)], limit=1)
        if not product:
            product = Product.search([('display_name', 'ilike', code)], limit=1)

        preset = False
        if product:
            preset = self._find_product_preset_for_product(product)
        if not preset:
            preset = Preset.search([('name', '=', code), ('active', '=', True)], limit=1)
        if not preset:
            preset = Preset.search([('name', 'ilike', code), ('active', '=', True)], limit=1)
        if preset and not product and preset.product_id:
            product = preset.product_id
        return product, preset

    def _line_values_from_code(self, code, qty=1):
        product, preset = self._find_product_or_preset_by_code(code)
        if product:
            vals = self._line_values_from_product(product, qty=qty)
            if preset:
                vals.update({
                    'product_preset_id': preset.id,
                    'length_in': preset.length_in,
                    'width_in': preset.width_in,
                    'height_in': preset.height_in,
                    'weight_lbs': self._best_product_weight_lbs(product, preset),
                    'allow_rotate': preset.allow_rotate,
                    'stackable': preset.stackable,
                    'max_stack': preset.max_stack,
                })
            return vals
        if preset:
            return {
                'product_preset_id': preset.id,
                'name': preset.name,
                'quantity': int(round(qty)) or 1,
                'length_in': preset.length_in,
                'width_in': preset.width_in,
                'height_in': preset.height_in,
                'weight_lbs': preset.weight_lbs or 0.0,
                'allow_rotate': preset.allow_rotate,
                'stackable': preset.stackable,
                'max_stack': preset.max_stack,
            }
        # Keep unknown codes visible instead of failing import; user can select a preset later.
        return {
            'name': code,
            'quantity': int(round(qty)) or 1,
            'length_in': 48.0,
            'width_in': 40.0,
            'height_in': 48.0,
            'weight_lbs': 0.0,
            'allow_rotate': True,
            'stackable': True,
            'max_stack': 0,
        }

    def _parse_pasted_load_items(self, pasted_text):
        """Parse pasted warehouse item lines.

        Supported examples:
            P001-008 (1 pallet)
            P001-008 (2 pallets, 24 items each)
            P001-008 (2 pallets x 24)
            P001-008 (2 pallets @ 24 per pallet)

        Returns [(code, pallet_qty, items_per_pallet), ...].
        ``items_per_pallet`` is optional and is stored for reporting; pallet_qty
        remains the number of physical pallet placements to optimize.
        """
        items = []
        bad_lines = []
        pattern = re.compile(r'^\s*([A-Za-z0-9][A-Za-z0-9_.\-/]*)\s*(?:\((.*?)\))?\s*$', re.IGNORECASE)

        def _positive_int(value, default=0):
            try:
                number = int(round(float(value)))
                return number if number > 0 else default
            except Exception:
                return default

        for raw in (pasted_text or '').splitlines():
            line = (raw or '').strip()
            if not line:
                continue
            match = pattern.match(line)
            if not match:
                bad_lines.append(line)
                continue

            code = match.group(1).strip()
            detail = (match.group(2) or '').strip()
            pallet_qty = 1
            items_per_pallet = 0

            if detail:
                # Pallet quantity: prefer the number explicitly tied to pallet/plt.
                pallet_match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:pallets?|plts?)\b', detail, re.IGNORECASE)
                if pallet_match:
                    pallet_qty = _positive_int(pallet_match.group(1), default=0)
                else:
                    first_number = re.search(r'([0-9]+(?:\.[0-9]+)?)', detail)
                    pallet_qty = _positive_int(first_number.group(1), default=0) if first_number else 1

                # Items per pallet: support x/@ syntax and natural language.
                # Examples: "2 pallets x 24", "2 pallets @ 24", "2 pallets, 24 items each".
                per_match = re.search(r'(?:x|×|@)\s*([0-9]+(?:\.[0-9]+)?)', detail, re.IGNORECASE)
                if not per_match:
                    per_match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:items?|pcs?|pieces?|units?|each|ea|cartons?|cases?|ctns?)\s*(?:each|ea|per\s*pallet|/\s*pallet)?', detail, re.IGNORECASE)
                if per_match:
                    candidate = _positive_int(per_match.group(1), default=0)
                    # Avoid treating "1 pallet" as items-per-pallet when no second quantity exists.
                    if not (candidate == pallet_qty and re.search(r'\b(?:pallets?|plts?)\b', detail, re.IGNORECASE) and len(re.findall(r'[0-9]+(?:\.[0-9]+)?', detail)) == 1):
                        items_per_pallet = candidate

            if pallet_qty <= 0:
                bad_lines.append(line)
                continue
            items.append((code, pallet_qty, items_per_pallet))
        return items, bad_lines

    def action_replace_lines_from_paste(self):
        """Replace Items To Load from pasted warehouse list.

        Supported examples:
            P001-008 (1 pallet)
            P001-013 (4 pallets, 24 items each)
            P001-019 (4 pallets x 20)
        Blank lines are ignored.
        """
        Line = self.env['cargo.architect.load.line']
        for plan in self:
            if plan.state in ('approved', 'released', 'loaded'):
                raise UserError(_('Approved, released, or loaded plans are locked. Unlock/reopen the plan before replacing items.'))
            parsed, bad_lines = plan._parse_pasted_load_items(plan.paste_load_items_text)
            if not parsed:
                raise UserError(_('Paste one or more item lines such as P001-008 (1 pallet, 24 items each).'))
            if bad_lines:
                raise UserError(_('These pasted lines could not be read:\n%s') % '\n'.join(bad_lines[:10]))

            # Replace current load items and clear any old optimized placements because
            # the requested freight changed.
            plan._snapshot_placements(_('Before Paste Import')) if hasattr(plan, '_snapshot_placements') else None
            plan.placement_ids.unlink()
            plan.line_ids.unlink()
            vals_list = []
            seq = 10
            for code, qty, items_per_pallet in parsed:
                vals = plan._line_values_from_code(code, qty=qty)
                vals.update({'plan_id': plan.id, 'sequence': seq, 'items_per_pallet': items_per_pallet})
                vals_list.append(vals)
                seq += 10
            Line.create(vals_list)
            plan.write({
                'paste_load_items_text': False,
                'state': 'draft',
                'unplaced_json': '{}',
            })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Items Imported'),
                'message': _('Pasted items were imported into Items To Load.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def _approval_notification(self, title, message, notif_type='success', sticky=False):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': notif_type,
                'sticky': sticky,
            }
        }

    def _ensure_can_modify(self):
        for plan in self:
            if plan.state in ('approved', 'released', 'loaded'):
                raise UserError(_('This load plan is %s and is locked. Reset it to Draft before making changes.') % dict(plan._fields['state'].selection).get(plan.state, plan.state))

    def action_reset_to_draft(self):
        for plan in self:
            plan.write({
                'state': 'draft',
                'submitted_by_id': False,
                'submitted_date': False,
                'approved_by_id': False,
                'approved_date': False,
                'released_by_id': False,
                'released_date': False,
                'loaded_by_id': False,
                'loaded_date': False,
            })
        return self._approval_notification(_('Load Plan Reset'), _('The load plan has been reset to Draft.'))

    def action_submit_for_review(self):
        for plan in self:
            if plan.state == 'draft':
                plan.action_optimize_layout()
            plan.write({
                'state': 'review',
                'submitted_by_id': self.env.user.id,
                'submitted_date': fields.Datetime.now(),
            })
        return self._approval_notification(_('Ready For Review'), _('The load plan has been submitted for review.'))

    def action_approve_load_plan(self):
        for plan in self:
            if plan.approval_blocker:
                raise UserError(_('Cannot approve this load plan:\n%s') % plan.approval_blocker)
            plan.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })
        return self._approval_notification(_('Load Plan Approved'), _('The load plan has been approved and locked.'))

    def action_release_to_warehouse(self):
        for plan in self:
            if plan.state != 'approved':
                raise UserError(_('Only approved load plans can be released to the warehouse.'))
            plan.write({
                'state': 'released',
                'released_by_id': self.env.user.id,
                'released_date': fields.Datetime.now(),
            })
        return self._approval_notification(_('Released To Warehouse'), _('The load plan has been released to warehouse operations.'))

    def action_mark_loaded(self):
        for plan in self:
            if plan.state not in ('released', 'approved'):
                raise UserError(_('Only approved or released load plans can be marked loaded.'))
            plan.write({
                'state': 'loaded',
                'loaded_by_id': self.env.user.id,
                'loaded_date': fields.Datetime.now(),
            })
        return self._approval_notification(_('Load Plan Loaded'), _('The load plan has been marked loaded.'))

    def action_import_from_pickings(self):
        self._ensure_can_modify()
        for plan in self:
            if not plan.picking_ids:
                raise UserError(_('Select one or more transfers first.'))
            commands = [(5, 0, 0)]
            grouped = defaultdict(float)
            product_by_key = {}
            for picking in plan.picking_ids:
                for move in plan._get_picking_load_sources(picking):
                    product = move.product_id if 'product_id' in move._fields else False
                    if not product:
                        continue
                    qty = plan._get_stock_record_qty(move)
                    if not qty:
                        qty = 1.0
                    key = product.id
                    grouped[key] += qty
                    product_by_key[key] = product
            if not grouped:
                raise UserError(_('No stock move or move line quantities were found on the selected transfers.'))
            for product_id, qty in grouped.items():
                product = product_by_key[product_id]
                commands.append((0, 0, plan._line_values_from_product(product, qty)))
            plan.line_ids = commands
        return True


    def action_refresh_product_dimensions(self):
        """Refresh all load lines from their assigned product presets."""
        self._ensure_can_modify()
        for plan in self:
            for line in plan.line_ids:
                line.action_refresh_from_product_preset()
        return True

    def action_update_all_product_presets_from_lines(self):
        """Create/update product presets from every line on the load plan."""
        self._ensure_can_modify()
        for plan in self:
            for line in plan.line_ids:
                if line.product_id or line.product_preset_id:
                    line.action_create_update_product_preset()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Product Presets Updated'),
                'message': _('All eligible product presets were created/updated from the load lines.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def _ensure_line_weights(self):
        """Fill missing line weights before optimization without overwriting edits."""
        for plan in self:
            for line in plan.line_ids:
                if (line.weight_lbs or 0.0) <= 0.0:
                    preset = line.product_preset_id or (plan._find_product_preset_for_product(line.product_id) if line.product_id else False)
                    line.weight_lbs = plan._best_product_weight_lbs(line.product_id, preset, 0.0)
        return True

    def _placement_history_snapshot(self, label=None):
        """Return a lightweight snapshot of the current manual placement state.

        v2.0.33 keeps a placement history stack so users can safely undo/redo
        manual planner edits, lock/unlock changes, and optimization runs.
        """
        self.ensure_one()
        return {
            'label': label or _('Placement Change'),
            'optimization_mode': self.optimization_mode or 'balanced',
            'state': self.state,
            'unplaced_json': self.unplaced_json or '{}',
            'placement_json': self.placement_json or '[]',
            'placements': [{
                'sequence': p.sequence,
                'line_id': p.line_id.id if p.line_id else False,
                'name': p.name,
                'x_in': p.x_in,
                'y_in': p.y_in,
                'z_in': p.z_in,
                'length_in': p.length_in,
                'width_in': p.width_in,
                'height_in': p.height_in,
                'weight_lbs': p.weight_lbs,
                'locked': p.locked,
            } for p in self.placement_ids.sorted(lambda p: p.sequence or 0)],
        }

    def _history_stack(self, field_name):
        self.ensure_one()
        try:
            value = json.loads(getattr(self, field_name) or '[]')
            return value if isinstance(value, list) else []
        except Exception:
            return []

    def _push_placement_history(self, label=None, clear_redo=True):
        """Push current placement state onto the undo stack.

        The stack is capped to 25 entries to avoid unbounded JSON growth.
        """
        self.ensure_one()
        stack = self._history_stack('placement_undo_stack_json')
        stack.append(self._placement_history_snapshot(label=label))
        stack = stack[-25:]
        vals = {'placement_undo_stack_json': json.dumps(stack)}
        if clear_redo:
            vals['placement_redo_stack_json'] = '[]'
        self.write(vals)

    def _apply_placement_history_snapshot(self, snapshot):
        self.ensure_one()
        if not snapshot:
            return False
        self.placement_ids.unlink()
        commands = [(0, 0, vals) for vals in snapshot.get('placements', [])]
        vals = {
            'optimization_mode': snapshot.get('optimization_mode') or self.optimization_mode or 'balanced',
            'state': snapshot.get('state') or self.state or 'draft',
            'unplaced_json': snapshot.get('unplaced_json') or '{}',
            'placement_json': snapshot.get('placement_json') or '[]',
        }
        if commands:
            vals['placement_ids'] = commands
        self.write(vals)
        # Rebuild placement_json with fresh database ids after restoring.
        self.placement_json = json.dumps([{
            'id': p.id, 'name': p.name, 'x': p.x_in, 'y': p.y_in, 'z': p.z_in,
            'length': p.length_in, 'width': p.width_in, 'height': p.height_in,
            'weight': p.weight_lbs, 'locked': p.locked,
        } for p in self.placement_ids.sorted(lambda p: p.sequence or 0)])
        return True

    def action_undo_placement_change(self):
        self._ensure_can_modify()
        for plan in self:
            undo_stack = plan._history_stack('placement_undo_stack_json')
            if not undo_stack:
                raise UserError(_('There are no placement changes to undo.'))
            current = plan._placement_history_snapshot(label=_('Redo Snapshot'))
            snapshot = undo_stack.pop()
            redo_stack = plan._history_stack('placement_redo_stack_json')
            redo_stack.append(current)
            redo_stack = redo_stack[-25:]
            plan.write({
                'placement_undo_stack_json': json.dumps(undo_stack),
                'placement_redo_stack_json': json.dumps(redo_stack),
            })
            plan._apply_placement_history_snapshot(snapshot)
        return self._approval_notification(_('Undo Complete'), _('The previous placement state has been restored.'), 'success')

    def action_redo_placement_change(self):
        self._ensure_can_modify()
        for plan in self:
            redo_stack = plan._history_stack('placement_redo_stack_json')
            if not redo_stack:
                raise UserError(_('There are no placement changes to redo.'))
            current = plan._placement_history_snapshot(label=_('Undo Snapshot'))
            snapshot = redo_stack.pop()
            undo_stack = plan._history_stack('placement_undo_stack_json')
            undo_stack.append(current)
            undo_stack = undo_stack[-25:]
            plan.write({
                'placement_undo_stack_json': json.dumps(undo_stack),
                'placement_redo_stack_json': json.dumps(redo_stack),
            })
            plan._apply_placement_history_snapshot(snapshot)
        return self._approval_notification(_('Redo Complete'), _('The placement change has been reapplied.'), 'success')

    def _snapshot_layout_state(self):
        """Capture current placement state so optimization trials can be rolled back safely."""
        self.ensure_one()
        return {
            'optimization_mode': self.optimization_mode or 'balanced',
            'state': self.state,
            'unplaced_json': self.unplaced_json or '{}',
            'placement_json': self.placement_json or '[]',
            'placements': [{
                'sequence': p.sequence,
                'line_id': p.line_id.id if p.line_id else False,
                'name': p.name,
                'x_in': p.x_in,
                'y_in': p.y_in,
                'z_in': p.z_in,
                'length_in': p.length_in,
                'width_in': p.width_in,
                'height_in': p.height_in,
                'weight_lbs': p.weight_lbs,
                'locked': p.locked,
            } for p in self.placement_ids.sorted(lambda p: p.sequence or 0)],
        }

    def _restore_layout_state(self, snapshot):
        """Restore a snapshot produced by _snapshot_layout_state."""
        self.ensure_one()
        self.placement_ids.unlink()
        commands = [(0, 0, vals) for vals in snapshot.get('placements', [])]
        vals = {
            'optimization_mode': snapshot.get('optimization_mode') or 'balanced',
            'state': snapshot.get('state') or 'draft',
            'unplaced_json': snapshot.get('unplaced_json') or '{}',
            'placement_json': snapshot.get('placement_json') or '[]',
        }
        if commands:
            vals['placement_ids'] = commands
        self.write(vals)

    def _layout_unplaced_count(self):
        self.ensure_one()
        try:
            return sum(int(v) for v in json.loads(self.unplaced_json or '{}').values())
        except Exception:
            return 0

    def _snapshot_score(self, snapshot):
        """Return Best Balance sort score.

        v2.0.7 keeps the hard rule from v2.0.3: maximum fit wins first.
        After that, true centerline-prorated side balance is scored before
        front/rear balance so a layout that fits every item will not leave
        all weight visually and mathematically on one side when a comparable
        side-by-side layout exists.
        """
        self.ensure_one()
        placements = snapshot.get('placements', []) or []
        try:
            unplaced = sum(int(v) for v in json.loads(snapshot.get('unplaced_json') or '{}').values())
        except Exception:
            unplaced = 0
        loaded = len(placements)
        total_weight = 0.0
        front_weight = 0.0
        rear_weight = 0.0
        left_weight = 0.0
        right_weight = 0.0
        half = (self.length_in or 0.0) / 2.0
        for p in placements:
            weight = float(p.get('weight_lbs') or 0.0)
            center_x = float(p.get('x_in') or 0.0) + float(p.get('length_in') or 0.0) / 2.0
            total_weight += weight
            if center_x <= half:
                front_weight += weight
            else:
                rear_weight += weight
            left_part, right_part = self._split_weight_left_right(p.get('y_in') or 0.0, p.get('width_in') or 0.0, weight)
            left_weight += left_part
            right_weight += right_part
        front_rear_delta = abs(front_weight - rear_weight) / total_weight if total_weight else 1.0
        side_delta = abs(left_weight - right_weight) / total_weight if total_weight else 1.0

        # v2.0.8: maximum fit still wins first, but when two layouts load the
        # same items the next priority is practical trailer fill.  A layout that
        # uses the trailer width in paired/blocked rows and leaves less usable
        # void space is safer in transport than a mathematically balanced layout
        # with long single-file lanes and large gaps.
        container_volume = (self.length_in or 0.0) * (self.width_in or 0.0) * (self.height_in or 0.0)
        used_volume = 0.0
        max_x = max_y = max_z = 0.0
        top_levels = []
        for p in placements:
            length = float(p.get('length_in') or 0.0)
            width = float(p.get('width_in') or 0.0)
            height = float(p.get('height_in') or 0.0)
            x = float(p.get('x_in') or 0.0)
            y = float(p.get('y_in') or 0.0)
            z = float(p.get('z_in') or 0.0)
            used_volume += length * width * height
            max_x = max(max_x, x + length)
            max_y = max(max_y, y + width)
            max_z = max(max_z, z + height)
            top_levels.append(z + height)
        bounding_volume = max_x * max(max_y, self.width_in or max_y) * max_z if max_x and max_z else container_volume
        void_ratio = max(0.0, (bounding_volume - used_volume) / bounding_volume) if bounding_volume else 1.0
        if len(top_levels) > 1:
            avg_top = sum(top_levels) / len(top_levels)
            level_penalty = (sum(abs(t - avg_top) for t in top_levels) / len(top_levels)) / max(self.height_in or 1.0, 1.0)
        else:
            level_penalty = 0.0
        return (unplaced, -loaded, void_ratio, level_penalty, side_delta, front_rear_delta)

    def _run_best_balance_full_fit_guard(self, starting_snapshot):
        """Best Balance must never load fewer items than another available strategy.

        The optimizer tries the requested Best Weight Balance layout first, then
        retries the stable packing modes. The selected result is always the layout
        with the fewest unplaced items; balance is only used as a tie-breaker.
        This prevents a balanced layout from excluding items that the normal
        optimizer can load.
        """
        self.ensure_one()
        candidates = [('best_balance', self._snapshot_layout_state())]
        if starting_snapshot and starting_snapshot.get('placements'):
            candidates.append(('previous', starting_snapshot))

        original_mode = self.optimization_mode or 'weight'
        for mode in ('balanced', 'cube', 'front'):
            self._restore_layout_state(starting_snapshot)
            self.write({'optimization_mode': mode})
            self._optimize_layout()
            candidates.append((mode, self._snapshot_layout_state()))

        # Pick highest fit first. If multiple strategies load the same count,
        # choose the tightest, most level layout before weight balance.
        best_label, best_snapshot = sorted(candidates, key=lambda item: self._snapshot_score(item[1]))[0]
        self._restore_layout_state(best_snapshot)
        # Keep the UI mode as Best Weight Balance only when it really won.
        self.write({'optimization_mode': 'weight' if best_label == 'best_balance' else (best_snapshot.get('optimization_mode') or original_mode)})
        return best_label

    def action_optimize_layout(self):
        self._ensure_can_modify()
        warning_messages = []
        for plan in self:
            plan._ensure_line_weights()
            starting_snapshot = plan._snapshot_layout_state()
            plan._optimize_layout()
            if (plan.optimization_mode or '') == 'weight':
                plan._run_best_balance_full_fit_guard(starting_snapshot)
            unplaced = plan._get_unplaced_dict()
            if unplaced:
                details = ', '.join('%s: %s' % (name, qty) for name, qty in sorted(unplaced.items()))
                warning_messages.append('%s - %s' % (plan.display_name, details))
        if warning_messages:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Load Plan Warning - Items Do Not Fit'),
                    'message': _('The layout was calculated, but not all items fit:\n%s') % '\n'.join(warning_messages),
                    'type': 'warning',
                    'sticky': True,
                }
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Load Plan Optimized'),
                'message': _('All requested items fit in the selected trailer/container.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def _get_unplaced_dict(self):
        self.ensure_one()
        try:
            data = json.loads(self.unplaced_json or '{}')
            return {str(k): int(v) for k, v in data.items() if int(v)}
        except Exception:
            return {}

    def get_unplaced_warning_message(self):
        self.ensure_one()
        unplaced = self._get_unplaced_dict()
        if not unplaced:
            return ''
        details = ', '.join('%s: %s' % (name, qty) for name, qty in sorted(unplaced.items()))
        return _('Not all items fit: %s') % details

    def _expanded_items(self):
        items = []
        for line in self.line_ids:
            for _i in range(max(0, line.quantity)):
                items.append({
                    'line': line,
                    'name': line.name,
                    'length': line.length_in,
                    'width': line.width_in,
                    'height': line.height_in,
                    'weight': line.weight_lbs,
                    'allow_rotate': line.allow_rotate,
                    'stackable': line.stackable,
                    'max_stack': line.max_stack,
                })
        mode = self.optimization_mode or 'balanced'
        if mode == 'cube':
            items.sort(key=lambda x: (x['length'] * x['width'] * x['height'], x['height'], x['weight']), reverse=True)
        elif mode == 'weight':
            items.sort(key=lambda x: (x['weight'], x['length'] * x['width'], x['height']), reverse=True)
        elif mode == 'front':
            items.sort(key=lambda x: (x['length'] * x['width'], x['height'], x['weight']), reverse=True)
        else:
            items.sort(key=lambda x: (x['height'], x['length'] * x['width'], x['weight']), reverse=True)
        return items

    def _optimize_layout(self):
        self.ensure_one()
        # v2.0.0: preserve user-locked manual placements and optimize all
        # remaining items around those locked positions. This gives users a
        # practical manual-edit workflow without losing work on recalculation.
        locked_records = self.placement_ids.filtered('locked')
        unlocked_records = self.placement_ids - locked_records
        unlocked_records.unlink()

        locked_counts = defaultdict(int)
        placements = []
        free = [(0.0, 0.0, 0.0, self.length_in, self.width_in, self.height_in)]

        def add_free_fragments(x, y, z, l, w, h):
            free.extend([
                (x + l, y, z, max(0.0, self.length_in - (x + l)), w, h),
                (x, y + w, z, l, max(0.0, self.width_in - (y + w)), h),
                (x, y, z + h, l, w, max(0.0, self.height_in - (z + h))),
            ])

        for locked in locked_records:
            locked_counts[locked.line_id.id if locked.line_id else locked.name] += 1
            data = {
                'line': locked.line_id,
                'name': locked.name,
                'x': locked.x_in or 0.0, 'y': locked.y_in or 0.0, 'z': locked.z_in or 0.0,
                'length': locked.length_in or 0.0, 'width': locked.width_in or 0.0, 'height': locked.height_in or 0.0,
                'weight': self._placement_weight_lbs(locked),
                'allow_rotate': bool(locked.line_id.allow_rotate) if locked.line_id else False,
                'stackable': bool(locked.line_id.stackable) if locked.line_id else True,
                'max_stack': locked.line_id.max_stack if locked.line_id else 0,
                'locked': True,
            }
            placements.append(data)
            add_free_fragments(data['x'], data['y'], data['z'], data['length'], data['width'], data['height'])

        items = []
        for item in self._expanded_items():
            key = item['line'].id if item.get('line') else item['name']
            if locked_counts.get(key, 0) > 0:
                locked_counts[key] -= 1
                continue
            items.append(item)
        free = [f for f in free if f[3] > 1.0 and f[4] > 1.0 and f[5] > 1.0]
        unplaced = defaultdict(int)

        def intersects(a, b):
            return not (
                a['x'] + a['length'] <= b['x'] or b['x'] + b['length'] <= a['x'] or
                a['y'] + a['width'] <= b['y'] or b['y'] + b['width'] <= a['y'] or
                a['z'] + a['height'] <= b['z'] or b['z'] + b['height'] <= a['z']
            )

        def supported(candidate):
            if candidate['z'] <= 0.01:
                return True
            support = 0.0
            footprint = candidate['length'] * candidate['width']
            for p in placements:
                if abs((p['z'] + p['height']) - candidate['z']) <= 0.05:
                    ox = max(0.0, min(candidate['x'] + candidate['length'], p['x'] + p['length']) - max(candidate['x'], p['x']))
                    oy = max(0.0, min(candidate['y'] + candidate['width'], p['y'] + p['width']) - max(candidate['y'], p['y']))
                    support += ox * oy
            return support >= footprint * 0.55

        for item in items:
            # v2.0.15: Always consider safe floor rotation during optimization.
            # The height is never changed, so this honors the Cargo Architect rule
            # that rotation may swap length/width only. Some imported lines/presets
            # were arriving with allow_rotate unchecked, which prevented pairable
            # cartons such as P001-010 from using two-across rows.
            rotations = [(item['length'], item['width'])]
            if abs(item['length'] - item['width']) > 0.01:
                rotations.append((item['width'], item['length']))
            placed = None
            # Gather valid placements first. In Best Weight Balance mode, score
            # each candidate by both front/rear and left/right weight balance.
            # This prevents heavier SKUs from being concentrated on one side
            # when rotation/side-by-side placement is available.
            candidates = sorted(free, key=lambda s: (s[2], s[0], s[1], s[3] * s[4] * s[5]))
            valid_options = []
            for sx, sy, sz, sl, sw, sh in candidates:
                for length, width in rotations:
                    if length <= sl + 0.001 and width <= sw + 0.001 and item['height'] <= sh + 0.001:
                        # v2.0.6: evaluate multiple width-lane positions inside
                        # each free space. Previous builds only tested sy, so
                        # even Best Balance could keep every item on the left
                        # side.  These y candidates allow right-edge and center
                        # lane placements while preserving collision/support
                        # checks and full-fit behavior.
                        y_positions = [sy]
                        right_y = sy + max(0.0, sw - width)
                        center_y = sy + max(0.0, (sw - width) / 2.0)
                        # Also test positions straddling the trailer centerline
                        # when they are inside this free space. This helps
                        # rotated cartons/pallets sit side-by-side instead of
                        # always using the left lane.
                        half_wid = (self.width_in or 0.0) / 2.0
                        centerline_right = max(sy, min(sy + sw - width, half_wid))
                        centerline_left = max(sy, min(sy + sw - width, half_wid - width))
                        for yp in (right_y, center_y, centerline_right, centerline_left):
                            if yp >= sy - 0.001 and yp + width <= sy + sw + 0.001:
                                y_positions.append(yp)
                        seen_y = set()
                        for cand_y in y_positions:
                            key_y = round(cand_y, 3)
                            if key_y in seen_y:
                                continue
                            seen_y.add(key_y)
                            candidate = {'x': sx, 'y': cand_y, 'z': sz, 'length': length, 'width': width, 'height': item['height']}
                            if not supported(candidate):
                                continue
                            if any(intersects(candidate, p) for p in placements):
                                continue
                            valid_options.append(candidate)
            if valid_options:
                def balance_option_score(candidate):
                    front = rear = left = right = 0.0
                    half_len = (self.length_in or 0.0) / 2.0
                    half_wid = (self.width_in or 0.0) / 2.0
                    trailer_width = self.width_in or 0.0
                    candidate_with_weight = dict(candidate, weight=item.get('weight') or 0.0)
                    trial = placements + [candidate_with_weight]
                    for p in trial:
                        weight = float(p.get('weight') or 0.0)
                        cx = float(p.get('x') or 0.0) + float(p.get('length') or 0.0) / 2.0
                        py = float(p.get('y') or 0.0)
                        pw = float(p.get('width') or 0.0)
                        if cx <= half_len:
                            front += weight
                        else:
                            rear += weight
                        left_part, right_part = self._split_weight_left_right(py, pw, weight)
                        left += left_part
                        right += right_part
                    total = front + rear
                    fr_delta = abs(front - rear) / total if total else 1.0
                    side_delta = abs(left - right) / total if total else 1.0
                    centerline_distance = abs((candidate['y'] + candidate['width'] / 2.0) - half_wid)

                    # v2.0.8 Best Fill scoring:
                    # Prefer using the trailer width in each length band, so items like
                    # P001-010 can rotate and pair side-by-side instead of forming a
                    # narrow single-file row with empty space.  This is a transport
                    # stability score, not only a weight-balance score.
                    same_band = []
                    cand_x1 = candidate['x']
                    cand_x2 = candidate['x'] + candidate['length']
                    cand_z = candidate['z']
                    for p in trial:
                        px1 = float(p.get('x') or 0.0)
                        px2 = px1 + float(p.get('length') or 0.0)
                        pz = float(p.get('z') or 0.0)
                        overlap_x = max(0.0, min(cand_x2, px2) - max(cand_x1, px1))
                        min_len = max(1.0, min(candidate['length'], float(p.get('length') or 0.0)))
                        if overlap_x >= min_len * 0.45 and abs(pz - cand_z) <= 0.05:
                            same_band.append((float(p.get('y') or 0.0), float(p.get('y') or 0.0) + float(p.get('width') or 0.0)))
                    same_band.sort()
                    merged = []
                    for a, b in same_band:
                        if not merged or a > merged[-1][1] + 0.25:
                            merged.append([a, b])
                        else:
                            merged[-1][1] = max(merged[-1][1], b)
                    occupied_width = sum(max(0.0, b - a) for a, b in merged)
                    width_void = max(0.0, trailer_width - occupied_width) / trailer_width if trailer_width else 1.0
                    side_edge_gap = 0.0
                    if merged and trailer_width:
                        side_edge_gap = (max(0.0, merged[0][0]) + max(0.0, trailer_width - merged[-1][1])) / trailer_width

                    # Keep tops as level as possible.  Lower placements are still
                    # preferred, but when stacking is needed this discourages tall
                    # uneven towers beside low voids.
                    top_levels = [float(p.get('z') or 0.0) + float(p.get('height') or 0.0) for p in trial]
                    if len(top_levels) > 1:
                        avg_top = sum(top_levels) / len(top_levels)
                        level_penalty = (sum(abs(t - avg_top) for t in top_levels) / len(top_levels)) / max(self.height_in or 1.0, 1.0)
                    else:
                        level_penalty = 0.0
                    # v2.0.11 paired-width loading fix:
                    # If an item has a rotation that allows two units across the
                    # trailer width, strongly prefer that rotation and place the
                    # first unit on an edge lane instead of centered down the
                    # middle. Centered single-file rows can look mathematically
                    # side-balanced because they straddle the centerline, but they
                    # leave large open channels on both sides and allow more
                    # movement during transport. Edge-started, two-across rows
                    # reduce void space and create better lateral blocking.
                    pairable_two_across = False
                    for _rot_l, rot_w in rotations:
                        if trailer_width and rot_w <= (trailer_width / 2.0) + 0.001:
                            pairable_two_across = True
                            break
                    pair_width_penalty = 0.0
                    pair_lane_penalty = 0.0
                    if pairable_two_across:
                        # Penalize the wider/non-pairable orientation when a
                        # two-across rotation is available. Example: P001-010
                        # 40x50 should prefer rotated 50x40 so two pieces use
                        # 80 inches of a 98 inch trailer width instead of a
                        # single 50 inch centered lane.
                        if candidate['width'] > (trailer_width / 2.0) + 0.001:
                            pair_width_penalty = 10.0
                        else:
                            touches_left = candidate['y'] <= 1.0
                            touches_right = candidate['y'] + candidate['width'] >= trailer_width - 1.0
                            # When no meaningful same-band neighbor exists yet,
                            # do not center the first item. Put it against an
                            # outside lane so the next same item can pair beside it.
                            if not (touches_left or touches_right):
                                pair_lane_penalty = 1.0
                    return (pair_width_penalty, pair_lane_penalty, width_void, level_penalty, side_edge_gap, side_delta, fr_delta, candidate['z'], candidate['x'], centerline_distance)

                mode = self.optimization_mode or ''
                if mode == 'weight':
                    # v2.0.8: Best Balance now means best filled, level, stable
                    # layout first; side/front balance follows after void and
                    # levelness when the same quantity fits.
                    placed = sorted(valid_options, key=balance_option_score)[0]
                elif mode == 'balanced':
                    placed = sorted(valid_options, key=balance_option_score)[0]
                elif mode == 'front':
                    # Front-load mode still works nose-to-rear, but within the
                    # same forward band it uses Best Fill scoring to avoid
                    # long one-sided rows.
                    placed = sorted(valid_options, key=lambda c: (c['x'], balance_option_score(c), c['z']))[0]
                else:
                    # Cube mode is now a true fill/void-minimizing mode rather
                    # than simply choosing the first low/front free space.
                    placed = sorted(valid_options, key=balance_option_score)[0]
            if not placed:
                unplaced[item['name']] += 1
                continue
            placed.update(item)
            placements.append(placed)
            x, y, z = placed['x'], placed['y'], placed['z']
            l, w, h = placed['length'], placed['width'], placed['height']
            add_free_fragments(x, y, z, l, w, h)
            free = [f for f in free if f[3] > 1.0 and f[4] > 1.0 and f[5] > 1.0]

        def compact_pairable_groups_for_transport():
            """Post-process pairable SKUs into tight two-across blocks.

            The general free-space optimizer can still create visually centered
            single-file rows because those rows pass fit and sometimes score as
            mathematically balanced.  For transport, pairable cartons should be
            block-loaded: two across the trailer width and stacked in even rows
            when possible. This pass repacks each pairable line after the
            non-pairable placements, preserving 100% fit and avoiding overlap.
            """
            if not placements:
                return
            trailer_w = float(self.width_in or 0.0)
            trailer_l = float(self.length_in or 0.0)
            trailer_h = float(self.height_in or 0.0)
            if trailer_w <= 0.0 or trailer_l <= 0.0 or trailer_h <= 0.0:
                return
            by_key = defaultdict(list)
            for p in placements:
                if p.get('locked'):
                    continue
                line = p.get('line')
                key = line.id if line else p.get('name')
                by_key[key].append(p)
            for key, group in list(by_key.items()):
                if len(group) < 2:
                    continue
                sample = group[0]
                line = sample.get('line')
                base_l = float(line.length_in if line else sample.get('length') or 0.0)
                base_w = float(line.width_in if line else sample.get('width') or 0.0)
                h = float(line.height_in if line else sample.get('height') or 0.0)
                if base_l <= 0.0 or base_w <= 0.0 or h <= 0.0:
                    continue
                # Pick the orientation with the narrowest width that can fit two-across.
                orientation_options = [(base_l, base_w), (base_w, base_l)] if abs(base_l - base_w) > 0.01 else [(base_l, base_w)]
                pair_orients = [(l, w) for l, w in orientation_options if (2.0 * w) <= trailer_w + 0.001 and l <= trailer_l + 0.001]
                if not pair_orients:
                    continue
                row_l, row_w = sorted(pair_orients, key=lambda lw: (lw[1], lw[0]))[0]
                stack_cap = 1
                if bool(line.stackable) if line else True:
                    max_stack = int(line.max_stack or 0) if line else 0
                    stack_cap = max(1, min(max_stack if max_stack else 2, int(trailer_h // h) if h else 1))
                # v2.0.15: build rows as two-across lanes centered around the
                # trailer centerline.  Capacity is still two sides times stack
                # levels, but leftover rows are filled side-by-side at the
                # lowest level before stacking one side. This avoids the v2.0.14
                # behavior where the last partial row could stack entirely on
                # one side and create a side-balance warning.
                row_capacity = max(1, 2 * stack_cap)
                rows_needed = int(math.ceil(float(len(group)) / float(row_capacity)))
                needed_length = rows_needed * row_l
                pair_y0 = max(0.0, (trailer_w - (2.0 * row_w)) / 2.0)
                side_y_positions = [pair_y0, pair_y0 + row_w]
                center_y = max(0.0, (trailer_w - row_w) / 2.0)
                others = [p for p in placements if p not in group]
                base_x = max([float(p.get('x') or 0.0) + float(p.get('length') or 0.0) for p in others if not p.get('locked')] or [0.0])
                # Prefer the original group start if it has enough room and no overlap.
                original_x = min(float(p.get('x') or 0.0) for p in group)
                candidate_starts = [original_x, base_x, max(0.0, trailer_l - needed_length)]
                chosen = None
                for start_x in sorted(set(round(x, 3) for x in candidate_starts)):
                    if start_x < -0.001 or start_x + needed_length > trailer_l + 0.001:
                        continue
                    trial = []
                    idx = 0
                    for row in range(rows_needed):
                        x = start_x + row * row_l
                        remaining = len(group) - idx
                        row_take = min(row_capacity, remaining)
                        placed_this_row = 0
                        # Fill lowest levels across both sides first: 2 items
                        # become left/right level 1, not a one-sided stack.
                        for level in range(stack_cap):
                            for side in range(2):
                                if idx >= len(group) or placed_this_row >= row_take:
                                    break
                                y = side_y_positions[side] if row_take > 1 else center_y
                                trial.append({'x': x, 'y': y, 'z': level * h, 'length': row_l, 'width': row_w, 'height': h})
                                idx += 1
                                placed_this_row += 1
                            if idx >= len(group) or placed_this_row >= row_take:
                                break
                        if idx >= len(group):
                            break
                    if len(trial) != len(group):
                        continue
                    ok = True
                    for c in trial:
                        if c['x'] + c['length'] > trailer_l + 0.001 or c['y'] + c['width'] > trailer_w + 0.001 or c['z'] + c['height'] > trailer_h + 0.001:
                            ok = False; break
                        if any(intersects(c, o) for o in others):
                            ok = False; break
                    if ok:
                        chosen = trial
                        break
                if not chosen:
                    continue
                for p, c in zip(group, chosen):
                    p['x'] = c['x']; p['y'] = c['y']; p['z'] = c['z']
                    p['length'] = c['length']; p['width'] = c['width']; p['height'] = c['height']

        compact_pairable_groups_for_transport()


        def compact_mixed_width_rows_for_transport():
            """Pair different SKUs side-by-side when their widths fit.

            v2.0.23: Previous transport compaction handled same-SKU pairs such
            as two P001-010 cartons. This pass looks for unlocked placements at
            the same stack level that can share a row even when they come from
            different product lines. It keeps the row centered in the trailer,
            prefers similar heights for level rows, validates trailer bounds,
            validates support for stacked rows, and refuses any move that would
            collide with existing placements.
            """
            if not placements:
                return
            tw = float(self.width_in or 0.0)
            tl = float(self.length_in or 0.0)
            th = float(self.height_in or 0.0)
            if tw <= 0.0 or tl <= 0.0 or th <= 0.0:
                return

            def support_ok(candidate, others):
                if float(candidate.get('z') or 0.0) <= 0.01:
                    return True
                footprint = float(candidate.get('length') or 0.0) * float(candidate.get('width') or 0.0)
                if footprint <= 0.0:
                    return False
                support = 0.0
                cz = float(candidate.get('z') or 0.0)
                for o in others:
                    oz_top = float(o.get('z') or 0.0) + float(o.get('height') or 0.0)
                    if abs(oz_top - cz) <= 0.05:
                        ox = max(0.0, min(candidate['x'] + candidate['length'], float(o.get('x') or 0.0) + float(o.get('length') or 0.0)) - max(candidate['x'], float(o.get('x') or 0.0)))
                        oy = max(0.0, min(candidate['y'] + candidate['width'], float(o.get('y') or 0.0) + float(o.get('width') or 0.0)) - max(candidate['y'], float(o.get('y') or 0.0)))
                        support += ox * oy
                return support >= footprint * 0.70

            def can_apply_pair(a, b, ca, cb):
                for c in (ca, cb):
                    if c['x'] < -0.001 or c['y'] < -0.001 or c['z'] < -0.001:
                        return False
                    if c['x'] + c['length'] > tl + 0.001 or c['y'] + c['width'] > tw + 0.001 or c['z'] + c['height'] > th + 0.001:
                        return False
                if intersects(ca, cb):
                    return False
                others = [p for p in placements if p is not a and p is not b]
                if any(intersects(ca, o) for o in others):
                    return False
                if any(intersects(cb, o) for o in others):
                    return False
                if not support_ok(ca, others):
                    return False
                if not support_ok(cb, others):
                    return False
                return True

            def compute_side_weights_for_dicts(items):
                left = right = 0.0
                for item in items:
                    weight = float(item.get('weight') or 0.0)
                    y = float(item.get('y') or 0.0)
                    width = float(item.get('width') or 0.0)
                    lpart, rpart = self._split_weight_left_right(y, width, weight)
                    left += lpart
                    right += rpart
                return left, right

            changed = True
            max_passes = 3
            pass_count = 0
            while changed and pass_count < max_passes:
                changed = False
                pass_count += 1
                movable = [p for p in placements if not p.get('locked')]
                # Group by stack level so we pair floor with floor, level 2 with level 2, etc.
                levels = defaultdict(list)
                for p in movable:
                    levels[round(float(p.get('z') or 0.0), 2)].append(p)
                for _z, level_items in levels.items():
                    # Work front-to-back and pair consecutive row candidates.
                    level_items = sorted(level_items, key=lambda p: (float(p.get('x') or 0.0), float(p.get('y') or 0.0)))
                    used = set()
                    for i, a in enumerate(level_items):
                        if id(a) in used:
                            continue
                        best = None
                        for b in level_items[i+1:]:
                            if id(b) in used or b is a:
                                continue
                            # Prefer mixed-SKU pairs first, but still allow same-SKU if they escaped the same-SKU pass.
                            aw = float(a.get('width') or 0.0); bw = float(b.get('width') or 0.0)
                            al = float(a.get('length') or 0.0); bl = float(b.get('length') or 0.0)
                            ah = float(a.get('height') or 0.0); bh = float(b.get('height') or 0.0)
                            if aw <= 0.0 or bw <= 0.0 or al <= 0.0 or bl <= 0.0 or ah <= 0.0 or bh <= 0.0:
                                continue
                            combined_w = aw + bw
                            if combined_w > tw + 0.001:
                                continue
                            # Very uneven heights can make a poor transport row unless stacking still supports it.
                            height_delta = abs(ah - bh)
                            if height_delta > max(8.0, min(ah, bh) * 0.25):
                                continue
                            row_x = min(float(a.get('x') or 0.0), float(b.get('x') or 0.0))
                            row_l = max(al, bl)
                            if row_x + row_l > tl + 0.001:
                                row_x = max(0.0, tl - row_l)
                            y0 = max(0.0, (tw - combined_w) / 2.0)
                            # Put heavier item on the lighter current side when possible.
                            lw, rw = compute_side_weights_for_dicts(placements)
                            a_weight = float(a.get('weight') or 0.0); b_weight = float(b.get('weight') or 0.0)
                            if lw > rw:
                                left_item, right_item = (b, a) if a_weight >= b_weight else (a, b)
                            else:
                                left_item, right_item = (a, b) if a_weight >= b_weight else (b, a)
                            def cand_for(p, y):
                                return {
                                    'x': row_x,
                                    'y': y,
                                    'z': float(p.get('z') or 0.0),
                                    'length': float(p.get('length') or 0.0),
                                    'width': float(p.get('width') or 0.0),
                                    'height': float(p.get('height') or 0.0),
                                }
                            left_c = cand_for(left_item, y0)
                            right_c = cand_for(right_item, y0 + float(left_item.get('width') or 0.0))
                            if not can_apply_pair(left_item, right_item, left_c, right_c):
                                continue
                            # Score by tight fill, levelness, and improvement to side balance.
                            before_l, before_r = compute_side_weights_for_dicts(placements)
                            trial = []
                            for p in placements:
                                if p is left_item:
                                    q = dict(p); q.update(left_c); trial.append(q)
                                elif p is right_item:
                                    q = dict(p); q.update(right_c); trial.append(q)
                                else:
                                    trial.append(p)
                            after_l, after_r = compute_side_weights_for_dicts(trial)
                            before_delta = abs(before_l - before_r)
                            after_delta = abs(after_l - after_r)
                            waste = max(0.0, tw - combined_w)
                            score = (after_delta - before_delta, waste, height_delta, row_x)
                            if best is None or score < best[0]:
                                best = (score, left_item, right_item, left_c, right_c)
                        if not best:
                            continue
                        _, left_item, right_item, left_c, right_c = best
                        left_item.update(left_c)
                        right_item.update(right_c)
                        used.add(id(left_item)); used.add(id(right_item))
                        changed = True

        compact_mixed_width_rows_for_transport()

        # v2.0.18: define trailer dimensions in the parent optimizer scope so
        # the centerline helper does not rely on variables scoped inside the
        # previous compacting helper.
        trailer_w = float(self.width_in or 0.0)
        trailer_l = float(self.length_in or 0.0)
        trailer_h = float(self.height_in or 0.0)

        def center_wide_single_across_groups():
            """Center wide one-across placements on the trailer centerline.

            P001-056 style freight can only fit one-across, but placing it tight
            to a wall creates a permanent side-balance penalty that paired
            freight cannot fully overcome.  If a placement consumes most of the
            trailer width and can be moved without creating an overlap, center it
            so the unused clearance is split evenly left/right.
            """
            if not placements or trailer_w <= 0.0:
                return
            def can_move_to_y(p, new_y):
                candidate = {
                    'x': float(p.get('x') or 0.0), 'y': float(new_y or 0.0), 'z': float(p.get('z') or 0.0),
                    'length': float(p.get('length') or 0.0), 'width': float(p.get('width') or 0.0), 'height': float(p.get('height') or 0.0),
                }
                if candidate['y'] < -0.001 or candidate['y'] + candidate['width'] > trailer_w + 0.001:
                    return False
                for other in placements:
                    if other is p:
                        continue
                    if intersects(candidate, other):
                        return False
                return True
            for p in placements:
                if p.get('locked'):
                    continue
                width = float(p.get('width') or 0.0)
                if width <= 0.0 or width < trailer_w * 0.60 or width >= trailer_w - 0.001:
                    continue
                centered_y = max(0.0, (trailer_w - width) / 2.0)
                if abs(float(p.get('y') or 0.0) - centered_y) <= 0.05:
                    continue
                if can_move_to_y(p, centered_y):
                    p['y'] = centered_y

        center_wide_single_across_groups()

        def mandatory_dense_compaction_front_left():
            """v2.0.36: Always close avoidable gaps regardless of weight spread.

            Earlier versions could leave large visual/product-group gaps because
            weight balance, sequence grouping, or mixed-row post-processing kept
            placements distributed across the trailer. Cargo Architect's primary
            packing objective is now dense physical loading: if all items fit,
            pack unlocked freight front-left and upward with the smallest
            practical bounding footprint. Weight spread remains calculated and
            reported, but it cannot intentionally create empty areas unless an
            axle/payload hard limit would fail.
            """
            if not placements:
                return
            tl = float(self.length_in or 0.0)
            tw = float(self.width_in or 0.0)
            th = float(self.height_in or 0.0)
            if tl <= 0.0 or tw <= 0.0 or th <= 0.0:
                return

            locked = [p for p in placements if p.get('locked')]
            movable = [p for p in placements if not p.get('locked')]
            if not movable:
                return

            def bounds_ok(c):
                return (
                    c['x'] >= -0.001 and c['y'] >= -0.001 and c['z'] >= -0.001 and
                    c['x'] + c['length'] <= tl + 0.001 and
                    c['y'] + c['width'] <= tw + 0.001 and
                    c['z'] + c['height'] <= th + 0.001
                )

            def support_ok(c, placed):
                if float(c.get('z') or 0.0) <= 0.01:
                    return True
                footprint = float(c.get('length') or 0.0) * float(c.get('width') or 0.0)
                if footprint <= 0.0:
                    return False
                support = 0.0
                cz = float(c.get('z') or 0.0)
                for o in placed:
                    top = float(o.get('z') or 0.0) + float(o.get('height') or 0.0)
                    if abs(top - cz) <= 0.05:
                        ox = max(0.0, min(c['x'] + c['length'], float(o.get('x') or 0.0) + float(o.get('length') or 0.0)) - max(c['x'], float(o.get('x') or 0.0)))
                        oy = max(0.0, min(c['y'] + c['width'], float(o.get('y') or 0.0) + float(o.get('width') or 0.0)) - max(c['y'], float(o.get('y') or 0.0)))
                        support += ox * oy
                return support >= footprint * 0.70

            def collides(c, placed):
                return any(intersects(c, o) for o in placed)

            def candidate_positions(placed):
                xs = {0.0}
                ys = {0.0}
                zs = {0.0}
                for o in placed:
                    xs.add(round(float(o.get('x') or 0.0) + float(o.get('length') or 0.0), 3))
                    ys.add(round(float(o.get('y') or 0.0) + float(o.get('width') or 0.0), 3))
                    zs.add(round(float(o.get('z') or 0.0) + float(o.get('height') or 0.0), 3))
                    # Also allow alignment with existing starts to fill gaps beside freight.
                    xs.add(round(float(o.get('x') or 0.0), 3))
                    ys.add(round(float(o.get('y') or 0.0), 3))
                return sorted(xs), sorted(ys), sorted(zs)

            # Largest floor footprint first generally produces the smallest front-left block.
            movable_sorted = sorted(
                movable,
                key=lambda p: (
                    float(p.get('length') or 0.0) * float(p.get('width') or 0.0),
                    float(p.get('height') or 0.0),
                    float(p.get('weight') or 0.0),
                ),
                reverse=True,
            )

            placed_new = list(locked)
            new_positions = []
            for p in movable_sorted:
                length = float(p.get('length') or 0.0)
                width = float(p.get('width') or 0.0)
                height = float(p.get('height') or 0.0)
                if length <= 0.0 or width <= 0.0 or height <= 0.0:
                    return
                orientations = [(length, width)]
                # Preserve height and allow length/width floor rotation when it produces a tighter block.
                if abs(length - width) > 0.01:
                    orientations.append((width, length))
                best = None
                xs, ys, zs = candidate_positions(placed_new)
                for zc in zs:
                    for xc in xs:
                        for yc in ys:
                            for ol, ow in orientations:
                                c = {'x': float(xc), 'y': float(yc), 'z': float(zc), 'length': ol, 'width': ow, 'height': height}
                                if not bounds_ok(c):
                                    continue
                                if collides(c, placed_new):
                                    continue
                                if not support_ok(c, placed_new):
                                    continue
                                # Dense compaction score: lowest/front-left, smallest current bounding box.
                                max_x = max([float(o.get('x') or 0.0) + float(o.get('length') or 0.0) for o in placed_new] + [c['x'] + c['length']])
                                max_y = max([float(o.get('y') or 0.0) + float(o.get('width') or 0.0) for o in placed_new] + [c['y'] + c['width']])
                                max_z = max([float(o.get('z') or 0.0) + float(o.get('height') or 0.0) for o in placed_new] + [c['z'] + c['height']])
                                score = (max_x, max_y, max_z, c['z'], c['x'], c['y'])
                                if best is None or score < best[0]:
                                    best = (score, c)
                if best is None:
                    # Do not risk losing a full-fit layout. If dense repack cannot
                    # place everything, keep the previous optimizer output.
                    return
                new_c = best[1]
                q = dict(p)
                q.update(new_c)
                placed_new.append(q)
                new_positions.append((p, new_c))

            # Apply only after every movable placement was successfully repacked.
            for p, c in new_positions:
                p['x'] = c['x']; p['y'] = c['y']; p['z'] = c['z']
                p['length'] = c['length']; p['width'] = c['width']; p['height'] = c['height']

        mandatory_dense_compaction_front_left()


        def full_fit_preservation_recovery():
            """v2.0.36: never accept a post-processing result that loses fit.

            Dense compaction and transport-row post-processors are allowed to move
            freight, but they must not reduce the loaded count. If the normal pass
            leaves items unplaced while a conservative physical repack can place
            more items, rebuild the unlocked placements from that full-fit repack.
            This fixes the v2.0.36 case where the trailer evaluation could prove
            28/28 fit while the saved final layout contained only 24/28.
            """
            nonlocal placements, unplaced
            tl = float(self.length_in or 0.0)
            tw = float(self.width_in or 0.0)
            th = float(self.height_in or 0.0)
            if tl <= 0.0 or tw <= 0.0 or th <= 0.0:
                return

            requested_items = []
            locked = [p for p in placements if p.get('locked')]
            locked_counts = defaultdict(int)
            for lp in locked:
                line = lp.get('line')
                key = line.id if line else lp.get('name')
                locked_counts[key] += 1
            for item in self._expanded_items():
                line = item.get('line')
                key = line.id if line else item.get('name')
                if locked_counts.get(key, 0):
                    locked_counts[key] -= 1
                    continue
                requested_items.append(item)
            current_loaded = len([p for p in placements if not p.get('locked')])
            if not requested_items:
                return

            def rec_intersects(a, b):
                return not (
                    a['x'] + a['length'] <= b['x'] + 0.001 or b['x'] + b['length'] <= a['x'] + 0.001 or
                    a['y'] + a['width'] <= b['y'] + 0.001 or b['y'] + b['width'] <= a['y'] + 0.001 or
                    a['z'] + a['height'] <= b['z'] + 0.001 or b['z'] + b['height'] <= a['z'] + 0.001
                )

            def rec_supported(candidate, placed):
                if candidate['z'] <= 0.01:
                    return True
                footprint = candidate['length'] * candidate['width']
                if footprint <= 0.0:
                    return False
                support = 0.0
                for o in placed:
                    if abs((o['z'] + o['height']) - candidate['z']) <= 0.05:
                        ox = max(0.0, min(candidate['x'] + candidate['length'], o['x'] + o['length']) - max(candidate['x'], o['x']))
                        oy = max(0.0, min(candidate['y'] + candidate['width'], o['y'] + o['width']) - max(candidate['y'], o['y']))
                        support += ox * oy
                return support >= footprint * 0.55

            def rec_axis_points(axis, size, placed):
                points = {0.0}
                for o in placed:
                    if axis == 'x':
                        points.add(round(o['x'], 3)); points.add(round(o['x'] + o['length'], 3))
                    elif axis == 'y':
                        points.add(round(o['y'], 3)); points.add(round(o['y'] + o['width'], 3))
                    else:
                        points.add(round(o['z'], 3)); points.add(round(o['z'] + o['height'], 3))
                limit = tl if axis == 'x' else tw if axis == 'y' else th
                return sorted(v for v in points if v >= -0.001 and v + size <= limit + 0.001)

            def rec_score(c, placed):
                max_x = max([o['x'] + o['length'] for o in placed] + [c['x'] + c['length']])
                max_y = max([o['y'] + o['width'] for o in placed] + [c['y'] + c['width']])
                max_z = max([o['z'] + o['height'] for o in placed] + [c['z'] + c['height']])
                # Fit preservation first, then dense front-left block.  Weight
                # balance intentionally does not spread freight in this recovery.
                return (max_x, max_y, max_z, c['z'], c['x'], c['y'])

            items_sorted = sorted(
                requested_items,
                key=lambda i: (float(i.get('length') or 0.0) * float(i.get('width') or 0.0) * float(i.get('height') or 0.0), float(i.get('height') or 0.0), float(i.get('weight') or 0.0)),
                reverse=True,
            )
            placed_new = [dict(p) for p in locked]
            missing = defaultdict(int)
            for item in items_sorted:
                base_l = float(item.get('length') or 0.0)
                base_w = float(item.get('width') or 0.0)
                h = float(item.get('height') or 0.0)
                if base_l <= 0.0 or base_w <= 0.0 or h <= 0.0:
                    missing[item.get('name') or 'Unknown'] += 1
                    continue
                rotations = [(base_l, base_w)]
                if abs(base_l - base_w) > 0.01:
                    rotations.append((base_w, base_l))
                valid = []
                for l, w in rotations:
                    if l > tl + 0.001 or w > tw + 0.001 or h > th + 0.001:
                        continue
                    for z in rec_axis_points('z', h, placed_new):
                        for x in rec_axis_points('x', l, placed_new):
                            y_candidates = set(rec_axis_points('y', w, placed_new))
                            y_candidates.add(max(0.0, min(tw - w, (tw - w) / 2.0)))
                            y_candidates.add(max(0.0, tw - w))
                            y_candidates.add(max(0.0, min(tw - w, (tw / 2.0) - w)))
                            y_candidates.add(max(0.0, min(tw - w, tw / 2.0)))
                            for y in sorted(y_candidates):
                                c = {
                                    'line': item.get('line'), 'name': item.get('name'),
                                    'x': float(x), 'y': float(y), 'z': float(z),
                                    'length': l, 'width': w, 'height': h,
                                    'weight': float(item.get('weight') or 0.0),
                                    'allow_rotate': item.get('allow_rotate'),
                                    'stackable': item.get('stackable'),
                                    'max_stack': item.get('max_stack'),
                                    'locked': False,
                                }
                                if c['x'] + l > tl + 0.001 or c['y'] + w > tw + 0.001 or c['z'] + h > th + 0.001:
                                    continue
                                if any(rec_intersects(c, o) for o in placed_new):
                                    continue
                                if not rec_supported(c, placed_new):
                                    continue
                                valid.append(c)
                if not valid:
                    missing[item.get('name') or 'Unknown'] += 1
                    continue
                placed_new.append(sorted(valid, key=lambda c: rec_score(c, placed_new))[0])

            recovered_loaded = len([p for p in placed_new if not p.get('locked')])
            if recovered_loaded > current_loaded:
                placements = placed_new
                unplaced = missing
            elif not missing and unplaced:
                # Defensive guard: if this recovery found a full-fit result, use it
                # even when the count comparison is equal due to locked placements.
                placements = placed_new
                unplaced = missing

        full_fit_preservation_recovery()

        commands = []
        seq = 1
        for locked in locked_records:
            locked.sequence = seq
            seq += 1
        for p in placements:
            if p.get('locked'):
                continue
            commands.append((0, 0, {
                'sequence': seq,
                'line_id': p['line'].id if p.get('line') else False,
                'name': p['name'],
                'x_in': p['x'], 'y_in': p['y'], 'z_in': p['z'],
                'length_in': p['length'], 'width_in': p['width'], 'height_in': p['height'],
                'weight_lbs': p['weight'],
                'locked': False,
            }))
            seq += 1
        if commands:
            self.write({'placement_ids': commands})
        self.placement_json = json.dumps(placements, default=lambda o: getattr(o, 'id', str(o)))
        self.unplaced_json = json.dumps(dict(unplaced))
        self.state = 'optimized'

    def get_item_quantity_report_rows(self):
        """Return load-line inventory quantity rollups for forms/reports.

        Pallet quantity remains the physical optimizer quantity. Items / Pallet
        is an inventory/reporting quantity and lets the report show how many
        sellable/warehouse units are represented by the planned pallets.
        """
        self.ensure_one()
        rows = []
        for line in self.line_ids.sorted(lambda l: (l.sequence, l.id)):
            rows.append({
                'name': line.name,
                'pallet_qty': int(line.quantity or 0),
                'items_per_pallet': int(line.items_per_pallet or 0),
                'total_item_qty': int(line.total_item_qty or 0),
                'weight_lbs': float(line.weight_lbs or 0.0),
                'total_weight_lbs': float(line.weight_lbs or 0.0) * int(line.quantity or 0),
            })
        return rows

    def get_report_item_summary(self):
        """Return one summarized row per unique loaded item for QWeb reports."""
        self.ensure_one()
        grouped = {}
        order = []
        for placement in self.placement_ids:
            line = placement.line_id
            key = (
                line.id if line else 0,
                placement.name or '',
                round(placement.length_in or 0.0, 4),
                round(placement.width_in or 0.0, 4),
                round(placement.height_in or 0.0, 4),
                round(self._placement_weight_lbs(placement), 4),
                int(line.items_per_pallet or 0) if line else 0,
            )
            if key not in grouped:
                grouped[key] = {
                    'name': placement.name or (line.name if line else ''),
                    'length_in': placement.length_in or 0.0,
                    'width_in': placement.width_in or 0.0,
                    'height_in': placement.height_in or 0.0,
                    'unit_weight_lbs': self._placement_weight_lbs(placement),
                    'quantity': 0,
                    'items_per_pallet': int(line.items_per_pallet or 0) if line else 0,
                    'total_item_qty': 0,
                    'total_weight_lbs': 0.0,
                }
                order.append(key)
            grouped[key]['quantity'] += 1
            if line and line.items_per_pallet:
                grouped[key]['total_item_qty'] += int(line.items_per_pallet or 0)
            grouped[key]['total_weight_lbs'] += self._placement_weight_lbs(placement)
        return [grouped[key] for key in order]

    def get_weight_distribution_rows(self):
        """Return trailer weight distribution rows for forms/reports."""
        self.ensure_one()
        total = self.total_weight_lbs or 0.0
        rows = [
            ('Front 0-25%', self.front_quarter_lbs or 0.0),
            ('Front-Mid 25-50%', self.front_mid_lbs or 0.0),
            ('Rear-Mid 50-75%', self.rear_mid_lbs or 0.0),
            ('Rear 75-100%', self.rear_quarter_lbs or 0.0),
            ('Front Half', self.front_half_lbs or 0.0),
            ('Rear Half', self.rear_half_lbs or 0.0),
        ]
        return [{
            'label': label,
            'weight_lbs': weight,
            'percent': (weight / total * 100.0) if total else 0.0,
        } for label, weight in rows]

    def get_side_balance_rows(self):
        """Return left/right trailer balance rows for reports and forms."""
        self.ensure_one()
        total = self.total_weight_lbs or 0.0
        left = self.left_side_lbs or 0.0
        right = self.right_side_lbs or 0.0
        return [
            {'label': _('Left Side'), 'weight_lbs': left, 'percent': (left / total * 100.0) if total else 0.0},
            {'label': _('Right Side'), 'weight_lbs': right, 'percent': (right / total * 100.0) if total else 0.0},
            {'label': _('Side Difference'), 'weight_lbs': self.side_balance_delta_lbs or 0.0, 'percent': ((self.side_balance_delta_lbs or 0.0) / total * 100.0) if total else 0.0},
        ]

    def get_quality_score_rows(self):
        self.ensure_one()
        return [
            {'label': _('Utilization'), 'score': self.utilization_score or 0.0},
            {'label': _('Weight Balance'), 'score': self.weight_balance_score or 0.0},
            {'label': _('Side-to-Side Balance'), 'score': self.side_balance_score or 0.0},
            {'label': _('Axle Distribution'), 'score': self.axle_score or 0.0},
            {'label': _('Stability / Fit'), 'score': self.stability_score or 0.0},
        ]

    def get_status_indicator_rows(self):
        self.ensure_one()
        label_map = {'pass': 'PASS', 'warning': 'WARNING', 'fail': 'FAIL'}
        return [
            {'label': _('Overall'), 'status': label_map.get(self.overall_status or 'warning')},
            {'label': _('Fit'), 'status': label_map.get(self.fit_status or 'warning')},
            {'label': _('Payload'), 'status': label_map.get(self.weight_status or 'warning')},
            {'label': _('Axles'), 'status': label_map.get(self.axle_status or 'warning')},
        ]

    def get_axle_utilization_rows(self):
        self.ensure_one()
        rows = [
            (_('Steer Axle'), self.steer_axle_lbs or 0.0, 12000.0),
            (_('Drive Axles'), self.drive_axle_lbs or 0.0, 34000.0),
            (_('Trailer Axles'), self.trailer_axle_lbs or 0.0, 34000.0),
        ]
        result = []
        for label, weight, limit in rows:
            percent = weight / limit * 100.0 if limit else 0.0
            status = 'FAIL' if percent > 100.0 else ('WARNING' if percent > 92.0 else 'PASS')
            result.append({'label': label, 'weight_lbs': weight, 'limit_lbs': limit, 'percent': percent, 'bar_width': min(percent, 100.0), 'status': status})
        return result



    def _analyze_cargo_securement(self, total_weight, free_cube_ft3, floor_util, side_delta_pct, stack_count, loaded, stability_status):
        """Return practical cargo securement and void-space guidance.

        v2.0.39 expands this from a simple rear/side void estimate into a
        zone-based planning score. It is still a planning aid rather than a
        certified FMCSA cargo-securement calculation, but it now gives the
        planner actionable void-zone percentages, blocking points, and load-bar
        guidance that can be reviewed before release.
        """
        self.ensure_one()
        total_weight = total_weight or 0.0
        loaded = loaded or 0
        trailer_len = self.length_in or 0.0
        trailer_w = self.width_in or 0.0
        trailer_h = self.height_in or 0.0
        placements = self.placement_ids
        used_len = max([(p.x_in or 0.0) + (p.length_in or 0.0) for p in placements] or [0.0])
        used_w_min = min([(p.y_in or 0.0) for p in placements] or [0.0])
        used_w_max = max([(p.y_in or 0.0) + (p.width_in or 0.0) for p in placements] or [0.0])
        rear_void_in = max(trailer_len - used_len, 0.0)
        used_width = max(used_w_max - used_w_min, 0.0)
        side_void_in = max(trailer_w - used_width, 0.0)

        # Estimate void by length zones. A zone is considered occupied by the
        # footprint area of pallets whose center falls inside that length band.
        # This gives a useful planning signal for rear/center/front gaps without
        # requiring a full voxelization of the trailer interior.
        zone_area = (trailer_len / 3.0) * trailer_w if trailer_len and trailer_w else 0.0
        zone_occupied = [0.0, 0.0, 0.0]
        left_area = 0.0
        right_area = 0.0
        half_w = trailer_w / 2.0 if trailer_w else 0.0
        for p in placements:
            x = p.x_in or 0.0
            y = p.y_in or 0.0
            l = p.length_in or 0.0
            w = p.width_in or 0.0
            cx = x + l / 2.0
            if trailer_len:
                idx = min(2, max(0, int(cx / (trailer_len / 3.0))))
                zone_occupied[idx] += l * w
            if trailer_w:
                left_overlap = max(0.0, min(y + w, half_w) - max(y, 0.0))
                right_overlap = max(0.0, min(y + w, trailer_w) - max(y, half_w))
                left_area += l * left_overlap
                right_area += l * right_overlap

        void_front_pct = max(0.0, min(100.0, 100.0 - (zone_occupied[0] / zone_area * 100.0))) if zone_area else 100.0
        void_center_pct = max(0.0, min(100.0, 100.0 - (zone_occupied[1] / zone_area * 100.0))) if zone_area else 100.0
        void_rear_pct = max(0.0, min(100.0, 100.0 - (zone_occupied[2] / zone_area * 100.0))) if zone_area else 100.0
        side_area = (trailer_len * half_w) if trailer_len and half_w else 0.0
        void_left_pct = max(0.0, min(100.0, 100.0 - (left_area / side_area * 100.0))) if side_area else 100.0
        void_right_pct = max(0.0, min(100.0, 100.0 - (right_area / side_area * 100.0))) if side_area else 100.0

        largest_void_ft3 = max(
            (rear_void_in * trailer_w * trailer_h) / 1728.0 if trailer_w and trailer_h else 0.0,
            (side_void_in * max(used_len, 0.0) * trailer_h) / 1728.0 if used_len and trailer_h else 0.0,
            (max(void_front_pct, void_center_pct, void_rear_pct) / 100.0 * (zone_area or 0.0) * trailer_h / 1728.0) if trailer_h else 0.0,
        )
        void_pct = max(0.0, min(100.0, (100.0 - (self.cube_utilization or 0.0))))
        stack_pct = (float(stack_count) / float(loaded) * 100.0) if loaded else 0.0
        risk_points = 0
        reasons = []
        blocking = []
        blocking_points = 0

        if void_pct >= 55.0:
            risk_points += 4
            reasons.append(_('critical unused cube %.1f%%') % void_pct)
        elif void_pct >= 45.0:
            risk_points += 3
            reasons.append(_('high unused cube %.1f%%') % void_pct)
        elif void_pct >= 30.0:
            risk_points += 2
            reasons.append(_('moderate unused cube %.1f%%') % void_pct)
        elif void_pct >= 20.0:
            risk_points += 1

        if rear_void_in >= 48.0 or void_rear_pct >= 70.0:
            risk_points += 2
            blocking_points += 2
            blocking.append(_('Install rear load bar or rear blocking; rear void %.0f in / rear zone %.0f%% void') % (rear_void_in, void_rear_pct))
        elif rear_void_in >= 24.0 or void_rear_pct >= 50.0:
            risk_points += 1
            blocking_points += 1
            blocking.append(_('Use rear bracing/load bar; rear void %.0f in / rear zone %.0f%% void') % (rear_void_in, void_rear_pct))

        if side_void_in >= 18.0 or max(void_left_pct, void_right_pct) >= 70.0:
            risk_points += 2
            blocking_points += 2
            blocking.append(_('Install side blocking/dunnage; side void %.0f in, left/right void %.0f%% / %.0f%%') % (side_void_in, void_left_pct, void_right_pct))
        elif side_void_in >= 10.0 or max(void_left_pct, void_right_pct) >= 55.0:
            risk_points += 1
            blocking_points += 1
            blocking.append(_('Review side blocking; side void %.0f in, left/right void %.0f%% / %.0f%%') % (side_void_in, void_left_pct, void_right_pct))

        if void_center_pct >= 65.0 and loaded:
            risk_points += 1
            blocking_points += 1
            blocking.append(_('Review center-zone void; use filler, dunnage, or tighter row compaction where practical'))

        if side_delta_pct >= 15.0:
            risk_points += 2
            reasons.append(_('side imbalance %.1f%%') % side_delta_pct)
            blocking.append(_('Re-center or mirror heavy freight before release'))
        elif side_delta_pct >= 10.0:
            risk_points += 1
            reasons.append(_('side imbalance %.1f%%') % side_delta_pct)

        if stack_pct >= 45.0:
            risk_points += 2
            reasons.append(_('high stacked freight %.1f%%') % stack_pct)
            blocking_points += 1
            blocking.append(_('Verify stacked freight is strapped or restrained as a unit'))
        elif stack_pct >= 25.0:
            risk_points += 1

        if stability_status == 'fail':
            risk_points += 3
            reasons.append(_('stability status FAIL'))
        elif stability_status == 'warning':
            risk_points += 1

        if total_weight >= 30000.0:
            risk_points += 2
        elif total_weight >= 15000.0:
            risk_points += 1

        if not blocking:
            blocking.append(_('No major blocking concern detected; verify normal shipper securement practice.'))

        base_straps = int(math.ceil(total_weight / 5000.0)) if total_weight else 1
        length_straps = int(math.ceil((used_len or trailer_len or 1.0) / 96.0))
        strap_count = max(2, base_straps, length_straps)
        if risk_points >= 6:
            strap_count += 2
        elif risk_points >= 3:
            strap_count += 1
        load_bar_count = 0
        if rear_void_in >= 24.0 or void_rear_pct >= 50.0:
            load_bar_count += 1
        if side_void_in >= 18.0 or max(void_left_pct, void_right_pct) >= 70.0:
            load_bar_count += 1
        if void_center_pct >= 75.0 and loaded:
            load_bar_count += 1

        securement_score = max(0.0, min(100.0, 100.0 - risk_points * 9.0 - max(0.0, void_pct - 35.0) * 0.35))
        if risk_points >= 8:
            risk = 'critical'; status = 'fail'
        elif risk_points >= 6:
            risk = 'high'; status = 'fail'
        elif risk_points >= 4:
            risk = 'moderate'; status = 'warning'
        elif risk_points >= 2:
            risk = 'low'; status = 'pass'
        else:
            risk = 'very_low'; status = 'pass'

        void_summary = _('Free cube %.1f ft³; largest void %.1f ft³; front/center/rear void %.0f%% / %.0f%% / %.0f%%; left/right void %.0f%% / %.0f%%.') % (
            free_cube_ft3 or 0.0,
            largest_void_ft3 or 0.0,
            void_front_pct,
            void_center_pct,
            void_rear_pct,
            void_left_pct,
            void_right_pct,
        )
        summary = _('Risk basis: %s') % (', '.join(reasons) if reasons else _('low void/stack/imbalance indicators'))
        return {
            'status': status,
            'risk': risk,
            'void_summary': void_summary,
            'largest_void_ft3': largest_void_ft3,
            'strap_count': strap_count,
            'load_bar_count': load_bar_count,
            'blocking': '\n'.join(blocking),
            'summary': summary,
            'securement_score': securement_score,
            'void_front_pct': void_front_pct,
            'void_center_pct': void_center_pct,
            'void_rear_pct': void_rear_pct,
            'void_left_pct': void_left_pct,
            'void_right_pct': void_right_pct,
            'blocking_points': blocking_points,
        }

    def get_securement_analysis_rows(self):
        self.ensure_one()
        risk_label = dict(self._fields['cargo_shift_risk'].selection).get(self.cargo_shift_risk or 'very_low')
        status_label = dict(self._fields['securement_status'].selection).get(self.securement_status or 'pass')
        return [
            {'label': _('Securement Status'), 'value': status_label},
            {'label': _('Securement Score'), 'value': '{:.0f} / 100'.format(self.securement_score or 0.0)},
            {'label': _('Cargo Shift Risk'), 'value': risk_label},
            {'label': _('Void Space'), 'value': self.void_space_summary or ''},
            {'label': _('Largest Estimated Void'), 'value': '{:,.1f} ft³'.format(self.largest_void_ft3 or 0.0)},
            {'label': _('Void by Length Zone'), 'value': 'Front {:.0f}% / Center {:.0f}% / Rear {:.0f}%'.format(self.void_front_pct or 0.0, self.void_center_pct or 0.0, self.void_rear_pct or 0.0)},
            {'label': _('Void by Side'), 'value': 'Left {:.0f}% / Right {:.0f}%'.format(self.void_left_pct or 0.0, self.void_right_pct or 0.0)},
            {'label': _('Recommended Straps'), 'value': str(self.recommended_strap_count or 0)},
            {'label': _('Recommended Load Bars'), 'value': str(self.recommended_load_bar_count or 0)},
            {'label': _('Recommended Blocking Points'), 'value': str(self.recommended_blocking_points or 0)},
            {'label': _('Blocking Recommendations'), 'value': (self.blocking_recommendations or '').replace('\n', '; ')},
            {'label': _('Securement Basis'), 'value': self.securement_reason_summary or ''},
        ]

    def get_engineering_analysis_rows(self):
        """Rows for v1.2.x engineering analysis cards/reports."""
        self.ensure_one()
        return [
            {'label': _('Free Cube'), 'value': '{:,.1f} ft³'.format(self.free_cube_ft3 or 0.0)},
            {'label': _('Remaining Payload'), 'value': '{:,.1f} lb'.format(self.remaining_payload_lbs or 0.0)},
            {'label': _('Floor Loading'), 'value': '{:,.2f} lb/sq ft'.format(self.floor_load_lbs_sqft or 0.0)},
            {'label': _('Lateral COG Offset'), 'value': '{:,.1f} in'.format(self.lateral_cog_offset_in or 0.0)},
            {'label': _('Vertical COG'), 'value': '{:,.1f} in above floor'.format(self.vertical_cog_in or 0.0)},
            {'label': _('Estimated Stability Factor'), 'value': '{:,.2f}'.format(self.static_stability_factor or 0.0)},
            {'label': _('Stability Status'), 'value': (dict(self._fields['load_stability_status'].selection).get(self.load_stability_status or 'warning') or 'WARNING')},
            {'label': _('Stability Basis'), 'value': self.stability_reason_summary or ''},
            {'label': _('Capacity Summary'), 'value': self.capacity_summary or ''},
        ]


    def get_load_advisory_rows(self):
        """Non-compliance advisory messages for report/dashboard.

        These are informational optimization suggestions and do not change the
        overall PASS/WARNING/FAIL status unless a hard constraint fails.
        """
        self.ensure_one()
        rows = []
        front = self.front_half_lbs or 0.0
        rear = self.rear_half_lbs or 0.0
        total = self.total_weight_lbs or 0.0
        if total:
            rear_pct = rear / total * 100.0
            front_pct = front / total * 100.0
            if abs(front_pct - rear_pct) >= 20.0:
                rows.append({
                    'label': _('Weight Balance Advisory'),
                    'value': _('Front %.1f%% / Rear %.1f%%. Load is biased %s; consider moving weight %s if operationally practical.') % (
                        front_pct, rear_pct, _('rearward') if rear_pct > front_pct else _('forward'), _('forward') if rear_pct > front_pct else _('rearward')
                    ),
                })
        if total:
            left_pct = (self.left_side_lbs or 0.0) / total * 100.0
            right_pct = (self.right_side_lbs or 0.0) / total * 100.0
            if abs(left_pct - right_pct) >= 15.0:
                rows.append({
                    'label': _('Side-to-Side Balance Advisory'),
                    'value': _('Left %.1f%% / Right %.1f%%. Consider rotating or alternating heavy SKUs side-by-side where possible.') % (left_pct, right_pct),
                })
        if (self.load_quality_score or 0.0) < 80.0 and (self.overall_status or 'pass') == 'pass':
            rows.append({
                'label': _('Quality Advisory'),
                'value': _('Load quality is below target, but fit, payload, and axle compliance pass.'),
            })
        if (self.load_stability_status or 'pass') == 'warning' and (self.overall_status or 'pass') == 'pass':
            rows.append({
                'label': _('Stability Advisory'),
                'value': self.stability_reason_summary or _('Stability is acceptable for compliance but could be improved by better balance or reduced stacking concentration.'),
            })
        return rows

    def get_weight_heat_map_rows(self):
        """Return eight trailer-zone rows with relative heat widths for report graphics.

        v1.2.1 expands the heat map from four large zones to eight smaller zones
        so the report clearly shows front-to-back weight concentration.
        """
        self.ensure_one()
        length = self.length_in or 0.0
        total_weight = self.total_weight_lbs or 0.0
        zone_weights = [0.0 for _i in range(8)]
        if length:
            for placement in self.placement_ids:
                center_x = (placement.x_in or 0.0) + (placement.length_in or 0.0) / 2.0
                idx = int((center_x / length) * 8.0)
                idx = max(0, min(7, idx))
                zone_weights[idx] += placement.weight_lbs or 0.0
        # Fallback to the four stored quarter values when placement lines have
        # not yet been regenerated but metrics exist.
        if not any(zone_weights):
            zone_weights = [
                (self.front_quarter_lbs or 0.0) / 2.0,
                (self.front_quarter_lbs or 0.0) / 2.0,
                (self.front_mid_lbs or 0.0) / 2.0,
                (self.front_mid_lbs or 0.0) / 2.0,
                (self.rear_mid_lbs or 0.0) / 2.0,
                (self.rear_mid_lbs or 0.0) / 2.0,
                (self.rear_quarter_lbs or 0.0) / 2.0,
                (self.rear_quarter_lbs or 0.0) / 2.0,
            ]
        labels = [
            _('Zone 1 Front 0-12.5%'), _('Zone 2 12.5-25%'),
            _('Zone 3 25-37.5%'), _('Zone 4 37.5-50%'),
            _('Zone 5 50-62.5%'), _('Zone 6 62.5-75%'),
            _('Zone 7 75-87.5%'), _('Zone 8 Rear 87.5-100%'),
        ]
        max_w = max(zone_weights) if zone_weights else 0.0
        rows = []
        for label, weight in zip(labels, zone_weights):
            pct = weight / total_weight * 100.0 if total_weight else 0.0
            heat = weight / max_w * 100.0 if max_w else 0.0
            level = 'high' if heat >= 75.0 else ('medium' if heat >= 40.0 else 'low')
            rows.append({'label': label, 'weight_lbs': weight, 'percent': pct, 'heat_width': heat, 'heat_level': level})
        return rows

    def get_cog_percent(self):
        self.ensure_one()
        return min(max((self.center_of_gravity_in or 0.0) / (self.length_in or 1.0) * 100.0, 0.0), 100.0)

    def _estimate_additional_fit_for_line(self, line, theoretical_limit):
        """Estimate additional copies that can be physically placed.

        v2.0.7 upgrades the Additional Capacity section from a cube/weight-only
        estimate to a conservative placement-aware estimate. It tests candidate
        positions generated from current placement edges, respects rotation,
        trailer bounds, collision checks, support checks, and remaining payload.
        """
        self.ensure_one()
        if theoretical_limit <= 0:
            return 0
        item_weight = float(line.weight_lbs or 0.0)
        payload_left = max(float(self.remaining_payload_lbs or 0.0), 0.0)
        if item_weight > 0.0:
            theoretical_limit = min(theoretical_limit, int(payload_left // item_weight))
        theoretical_limit = min(int(theoretical_limit), 100)
        if theoretical_limit <= 0:
            return 0

        placements = [{
            'x': p.x_in or 0.0,
            'y': p.y_in or 0.0,
            'z': p.z_in or 0.0,
            'length': p.length_in or 0.0,
            'width': p.width_in or 0.0,
            'height': p.height_in or 0.0,
        } for p in self.placement_ids]

        rotations = [(line.length_in or 0.0, line.width_in or 0.0)]
        if line.allow_rotate and abs((line.length_in or 0.0) - (line.width_in or 0.0)) > 0.01:
            rotations.append((line.width_in or 0.0, line.length_in or 0.0))
        height = line.height_in or 0.0
        if height <= 0.0 or not rotations:
            return 0

        def intersects(a, b):
            return not (
                a['x'] + a['length'] <= b['x'] or b['x'] + b['length'] <= a['x'] or
                a['y'] + a['width'] <= b['y'] or b['y'] + b['width'] <= a['y'] or
                a['z'] + a['height'] <= b['z'] or b['z'] + b['height'] <= a['z']
            )

        def supported(candidate):
            if candidate['z'] <= 0.01:
                return True
            footprint = candidate['length'] * candidate['width']
            support = 0.0
            for p in placements:
                if abs((p['z'] + p['height']) - candidate['z']) <= 0.05:
                    ox = max(0.0, min(candidate['x'] + candidate['length'], p['x'] + p['length']) - max(candidate['x'], p['x']))
                    oy = max(0.0, min(candidate['y'] + candidate['width'], p['y'] + p['width']) - max(candidate['y'], p['y']))
                    support += ox * oy
            return support >= footprint * 0.55

        def axis_positions(axis, size, trailer_size):
            points = {0.0}
            for p in placements:
                points.add(round(p[axis], 3))
                points.add(round(p[axis] + p['length' if axis == 'x' else 'width' if axis == 'y' else 'height'], 3))
            return sorted(v for v in points if v >= -0.001 and v + size <= trailer_size + 0.001)

        added = 0
        while added < theoretical_limit:
            best = None
            for length, width in rotations:
                if length <= 0.0 or width <= 0.0:
                    continue
                for z in axis_positions('z', height, self.height_in or 0.0):
                    for x in axis_positions('x', length, self.length_in or 0.0):
                        for y in axis_positions('y', width, self.width_in or 0.0):
                            candidate = {'x': x, 'y': y, 'z': z, 'length': length, 'width': width, 'height': height}
                            if any(intersects(candidate, p) for p in placements):
                                continue
                            if not supported(candidate):
                                continue
                            side_left, side_right = self._split_weight_left_right(y, width, item_weight or 1.0)
                            side_delta = abs(side_left - side_right)
                            score = (z, side_delta, x, y)
                            if best is None or score < best[0]:
                                best = (score, candidate)
            if not best:
                break
            placements.append(best[1])
            added += 1
        return added

    def get_capacity_analysis_rows(self):
        """Placement-aware additional-capacity estimates.

        v2.0.7 keeps the cube/payload limits but also simulates whether more
        copies can actually be placed around the current layout. This prevents
        the report from recommending extra items that only fit mathematically
        by cube but not physically in the trailer.
        """
        self.ensure_one()
        rows = []
        free_cube_in3 = max((self.length_in or 0.0) * (self.width_in or 0.0) * (self.height_in or 0.0) - sum(p.length_in * p.width_in * p.height_in for p in self.placement_ids), 0.0)
        remaining_payload = max(self.remaining_payload_lbs or 0.0, 0.0)
        for line in self.line_ids:
            item_cube = (line.length_in or 0.0) * (line.width_in or 0.0) * (line.height_in or 0.0)
            item_weight = line.weight_lbs or 0.0
            by_cube = int(free_cube_in3 // item_cube) if item_cube else 0
            by_weight = int(remaining_payload // item_weight) if item_weight else by_cube
            theoretical = max(0, min(by_cube, by_weight)) if item_weight else max(0, by_cube)
            can_add = self._estimate_additional_fit_for_line(line, theoretical)
            if can_add:
                rows.append({'name': line.name, 'can_add': can_add, 'limit': _('placement/payload/cube')})
        return rows[:12]

    def _get_load_passport_url(self):
        self.ensure_one()
        try:
            base_url = self.get_base_url()
        except Exception:
            base_url = ''
        return '%s/web#id=%s&model=cargo.architect.load.plan&view_type=form' % (base_url, self.id or '')

    def get_qr_load_passport_barcode_src(self):
        self.ensure_one()
        data = self.qr_load_passport_url or self._get_load_passport_url() or self.display_name
        # Query-string route avoids very long URL path segments and is more reliable in wkhtmltopdf.
        return '/report/barcode?type=QR&value=%s&width=120&height=120' % quote_plus(data)

    def _placement_zone_label(self, placement):
        """Return a warehouse-friendly trailer zone instead of raw coordinates."""
        length = self.length_in or 1.0
        center_x = (placement.x_in or 0.0) + ((placement.length_in or 0.0) / 2.0)
        pct = (center_x / length) if length else 0.0
        if pct < 0.25:
            return _('Front Zone')
        if pct < 0.50:
            return _('Front-Mid Zone')
        if pct < 0.75:
            return _('Rear-Mid Zone')
        return _('Rear Zone')

    def _placement_position_reference(self, sequence):
        """Human-readable reference for reports, e.g. A01, A02, B01."""
        idx = max(int(sequence or 1) - 1, 0)
        group = chr(ord('A') + min(idx // 24, 25))
        number = (idx % 24) + 1
        return '%s%02d' % (group, number)

    def _placement_stack_level(self, placement):
        if not placement.height_in:
            return 1
        return max(1, int(round((placement.z_in or 0.0) / (placement.height_in or 1.0))) + 1)

    def _placement_report_position(self, placement, sequence):
        return '%s | %s | Stack Level %s' % (
            self._placement_position_reference(sequence),
            self._placement_zone_label(placement),
            self._placement_stack_level(placement),
        )

    def _placement_technical_position(self, placement):
        return 'X %.1f / Y %.1f / Z %.1f' % (placement.x_in or 0.0, placement.y_in or 0.0, placement.z_in or 0.0)

    def get_load_sequence_rows(self):
        """Return recommended loading order: front/low/left first.

        Warehouse staff can use this as a practical loading checklist. It is
        based on the optimized placement coordinates.
        """
        self.ensure_one()
        placements = sorted(self.placement_ids, key=lambda p: ((p.x_in or 0.0), (p.z_in or 0.0), (p.y_in or 0.0), p.sequence or 0))
        rows = []
        for seq, p in enumerate(placements, 1):
            rows.append({
                'sequence': seq,
                'name': p.name,
                'position_ref': self._placement_position_reference(seq),
                'zone': self._placement_zone_label(p),
                'stack_level': self._placement_stack_level(p),
                'display_position': self._placement_report_position(p, seq),
                'technical_position': self._placement_technical_position(p),
                'x_in': p.x_in or 0.0,
                'y_in': p.y_in or 0.0,
                'z_in': p.z_in or 0.0,
                'length_in': p.length_in or 0.0,
                'width_in': p.width_in or 0.0,
                'height_in': p.height_in or 0.0,
                'weight_lbs': self._placement_weight_lbs(p),
            })
        return rows

    def get_unload_sequence_rows(self):
        """Return rear-to-front unloading order for warehouse and stop planning."""
        self.ensure_one()
        placements = sorted(self.placement_ids, key=lambda p: (-(p.x_in or 0.0), (p.z_in or 0.0), (p.y_in or 0.0), p.sequence or 0))
        rows = []
        for seq, p in enumerate(placements, 1):
            rows.append({
                'sequence': seq,
                'name': p.name,
                'position_ref': self._placement_position_reference(seq),
                'zone': self._placement_zone_label(p),
                'stack_level': self._placement_stack_level(p),
                'display_position': self._placement_report_position(p, seq),
                'technical_position': self._placement_technical_position(p),
                'x_in': p.x_in or 0.0,
                'y_in': p.y_in or 0.0,
                'z_in': p.z_in or 0.0,
                'weight_lbs': self._placement_weight_lbs(p),
            })
        return rows

    def get_forklift_accessibility_rows(self):
        """Estimate direct rear forklift accessibility.

        An item is considered directly accessible when no other placement sits
        behind it toward the trailer door while overlapping its Y/Z footprint.
        """
        self.ensure_one()
        rows = []
        placements = list(self.placement_ids)
        for p in placements:
            p_rear = (p.x_in or 0.0) + (p.length_in or 0.0)
            blocked_by = []
            for other in placements:
                if other.id == p.id:
                    continue
                other_front = other.x_in or 0.0
                y_overlap = not ((p.y_in or 0.0) + (p.width_in or 0.0) <= (other.y_in or 0.0) or (other.y_in or 0.0) + (other.width_in or 0.0) <= (p.y_in or 0.0))
                z_overlap = not ((p.z_in or 0.0) + (p.height_in or 0.0) <= (other.z_in or 0.0) or (other.z_in or 0.0) + (other.height_in or 0.0) <= (p.z_in or 0.0))
                if other_front >= p_rear - 0.01 and y_overlap and z_overlap:
                    blocked_by.append(other.name)
            accessible = not blocked_by
            rows.append({
                'name': p.name,
                'position': self._placement_report_position(p, p.sequence or 1),
                'technical_position': self._placement_technical_position(p),
                'accessible': accessible,
                'status': _('Accessible') if accessible else _('Blocked'),
                'blocked_by': ', '.join(blocked_by[:3]) + ('...' if len(blocked_by) > 3 else ''),
            })
        rows.sort(key=lambda r: (0 if r.get('accessible') else 1, r.get('name') or ''))
        return rows

    def _build_loading_instructions(self, load_rows, accessibility_rows):
        if not load_rows:
            return _('Optimize the load plan to generate loading instructions.')
        accessible_count = len([r for r in accessibility_rows if r.get('accessible')])
        total_count = len(accessibility_rows)
        lines = [
            _('1. Stage products by the Load Sequence table before loading.'),
            _('2. Load from trailer nose/front toward the rear using the sequence order.'),
            _('3. Keep stacked items aligned over supported footprints.'),
            _('4. Verify trailer axle and payload indicators before approval/release.'),
            _('5. Forklift direct-access estimate: %s of %s items accessible from rear.') % (accessible_count, total_count),
        ]
        return '\n'.join(lines)

    def action_lock_all_placements(self):
        self._ensure_can_modify()
        for plan in self:
            if not plan.placement_ids:
                raise UserError(_('Optimize the layout before locking placements.'))
            plan._push_placement_history(label=_('Before Lock All'))
            plan.placement_ids.write({'locked': True})
        return self._approval_notification(_('Placements Locked'), _('All current placements are locked. Re-optimization will preserve them.'), 'success')

    def action_unlock_all_placements(self):
        self._ensure_can_modify()
        for plan in self:
            if plan.placement_ids:
                plan._push_placement_history(label=_('Before Unlock All'))
            plan.placement_ids.write({'locked': False})
        return self._approval_notification(_('Placements Unlocked'), _('All placements are unlocked. The optimizer can move them on the next run.'), 'success')

    def action_reoptimize_around_locked(self):
        self._ensure_can_modify()
        return self.action_optimize_layout()

    def action_apply_best_balance_mode(self):
        """Apply Best Balance while preserving the maximum loadable quantity."""
        self._ensure_can_modify()
        for plan in self:
            plan.write({'optimization_mode': 'weight'})
        result = self.action_optimize_layout()
        # If all requested items fit, make the success message specific to Best Balance.
        if result and result.get('params') and result['params'].get('type') == 'success':
            result['params']['title'] = _('Best Balance Applied')
            result['params']['message'] = _('Best Balance was applied without reducing the loaded quantity. If another strategy fit more items, that full-fit layout was kept automatically.')
        return result

    def action_open_planner(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'cargo_architect_planner',
            'name': _('Cargo Architect'),
            'params': {'plan_id': self.id},
        }

    def action_update_placement_position(self, placement_id, x_in, y_in, z_in=0.0, lock=True):
        """Move a placement from the planner canvas and optionally lock it.

        v2.0.15 adds manual drag/drop editing.  This server-side method keeps
        the client simple and protects the load plan from impossible manual
        moves by enforcing trailer bounds and overlap checks before writing the
        placement.
        """
        self.ensure_one()
        self._ensure_can_modify()
        placement = self.env['cargo.architect.placement'].browse(int(placement_id)).exists()
        if not placement or placement.plan_id.id != self.id:
            raise UserError(_('Placement not found on this load plan.'))
        x = max(0.0, float(x_in or 0.0))
        y = max(0.0, float(y_in or 0.0))
        z = max(0.0, float(z_in or 0.0))
        length = float(placement.length_in or 0.0)
        width = float(placement.width_in or 0.0)
        height = float(placement.height_in or 0.0)
        if x + length > (self.length_in or 0.0) + 0.001 or y + width > (self.width_in or 0.0) + 0.001 or z + height > (self.height_in or 0.0) + 0.001:
            return {'ok': False, 'message': _('Cannot move block here. The placement is outside the trailer bounds.')}

        candidate = {'x': x, 'y': y, 'z': z, 'length': length, 'width': width, 'height': height}
        def intersects(a, b):
            return not (
                a['x'] + a['length'] <= b['x'] + 0.001 or b['x'] + b['length'] <= a['x'] + 0.001 or
                a['y'] + a['width'] <= b['y'] + 0.001 or b['y'] + b['width'] <= a['y'] + 0.001 or
                a['z'] + a['height'] <= b['z'] + 0.001 or b['z'] + b['height'] <= a['z'] + 0.001
            )
        def overlap_area(a, b):
            x_overlap = max(0.0, min(a['x'] + a['length'], b['x'] + b['length']) - max(a['x'], b['x']))
            y_overlap = max(0.0, min(a['y'] + a['width'], b['y'] + b['width']) - max(a['y'], b['y']))
            return x_overlap * y_overlap
        support_area = 0.0
        candidate_area = max(length * width, 0.001)
        for other in self.placement_ids:
            if other.id == placement.id:
                continue
            other_box = {
                'x': float(other.x_in or 0.0), 'y': float(other.y_in or 0.0), 'z': float(other.z_in or 0.0),
                'length': float(other.length_in or 0.0), 'width': float(other.width_in or 0.0), 'height': float(other.height_in or 0.0),
            }
            if intersects(candidate, other_box):
                return {'ok': False, 'message': _('Cannot move block here. It overlaps another loaded item.')}
            if z > 0.001 and abs((other_box['z'] + other_box['height']) - z) <= 0.5:
                support_area += overlap_area(candidate, other_box)
        if z > 0.001 and support_area / candidate_area < 0.70:
            return {'ok': False, 'message': _('Cannot stack block here. At least 70% of its footprint must be supported by items directly underneath.')}
        self._push_placement_history(label=_('Before Manual Move'))
        placement.write({'x_in': x, 'y_in': y, 'z_in': z, 'locked': bool(lock)})
        self.placement_json = json.dumps([{
            'id': p.id, 'name': p.name, 'x': p.x_in, 'y': p.y_in, 'z': p.z_in,
            'length': p.length_in, 'width': p.width_in, 'height': p.height_in,
            'weight': p.weight_lbs, 'locked': p.locked,
        } for p in self.placement_ids.sorted(lambda p: p.sequence or 0)])
        return {'ok': True, 'message': _('Placement moved and locked.')}

    def action_print_report(self):
        return self.env.ref('cargo_architect.action_report_cargo_load_plan').report_action(self)
