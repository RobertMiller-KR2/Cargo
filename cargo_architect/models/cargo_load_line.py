from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CargoLoadLine(models.Model):
    _name = 'cargo.architect.load.line'
    _description = 'Cargo Architect Load Line'
    _order = 'sequence, id'

    plan_id = fields.Many2one('cargo.architect.load.plan', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one('product.product')
    product_preset_id = fields.Many2one('cargo.architect.product.preset', string='Cargo Preset')
    name = fields.Char(required=True)
    quantity = fields.Integer(default=1, string='Pallet Qty')
    items_per_pallet = fields.Integer(string='Items / Pallet', default=0, help='Optional number of sellable/warehouse items on each physical pallet.')
    total_item_qty = fields.Integer(string='Total Items', compute='_compute_total_item_qty', store=True)
    length_in = fields.Float(required=True, default=48.0)
    width_in = fields.Float(required=True, default=40.0)
    height_in = fields.Float(required=True, default=48.0)
    weight_lbs = fields.Float(default=0.0)
    allow_rotate = fields.Boolean(default=True)
    stackable = fields.Boolean(default=True)
    max_stack = fields.Integer(default=0)


    @api.depends('quantity', 'items_per_pallet')
    def _compute_total_item_qty(self):
        for line in self:
            line.total_item_qty = int(line.quantity or 0) * int(line.items_per_pallet or 0) if line.items_per_pallet else 0

    def _apply_product_preset(self, preset=False):
        for line in self:
            chosen = preset or line.product_preset_id
            if not chosen and line.product_id:
                chosen = line.plan_id._find_product_preset_for_product(line.product_id) if line.plan_id else self.env['cargo.architect.load.plan']._find_product_preset_for_product(line.product_id)
            if chosen:
                line.product_preset_id = chosen.id
                line.name = line.product_id.display_name if line.product_id else chosen.name
                line.length_in = chosen.length_in
                line.width_in = chosen.width_in
                line.height_in = chosen.height_in
                line.weight_lbs = (line.plan_id or self.env['cargo.architect.load.plan'])._best_product_weight_lbs(line.product_id, chosen, 0.0)
                line.allow_rotate = chosen.allow_rotate
                line.stackable = chosen.stackable
                line.max_stack = chosen.max_stack
            elif line.product_id:
                line.name = line.product_id.display_name
                line.length_in = line.length_in or 48.0
                line.width_in = line.width_in or 40.0
                line.height_in = line.height_in or 48.0
                line.weight_lbs = line.weight_lbs or (line.plan_id or self.env['cargo.architect.load.plan'])._product_weight_lbs(line.product_id)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                plan = line.plan_id or self.env['cargo.architect.load.plan']
                preset = plan._find_product_preset_for_product(line.product_id)
                line._apply_product_preset(preset)

    @api.onchange('product_preset_id')
    def _onchange_product_preset_id(self):
        for line in self:
            if line.product_preset_id:
                line._apply_product_preset(line.product_preset_id)

    def action_refresh_from_product_preset(self):
        for line in self:
            if line.product_id:
                preset = line.plan_id._find_product_preset_for_product(line.product_id) if line.plan_id else False
                line._apply_product_preset(preset)
            elif line.product_preset_id:
                line._apply_product_preset(line.product_preset_id)
        return True

    def action_create_update_product_preset(self):
        """Create or update the Cargo Architect product preset from this load line.

        Use this when dimensions/weight are edited on a load line and the user
        wants those values to become the product default for future loads.
        If the line already has a preset, that preset is updated. Otherwise the
        product's assigned preset is found; if none exists, a new preset is
        created and linked to the product variant and template.
        """
        Preset = self.env['cargo.architect.product.preset']
        for line in self:
            if not line.product_id and not line.product_preset_id:
                raise UserError(_('Select a product or preset before creating/updating a preset.'))

            preset = line.product_preset_id
            if not preset and line.product_id and line.plan_id:
                preset = line.plan_id._find_product_preset_for_product(line.product_id)
            elif not preset and line.product_id:
                preset = self.env['cargo.architect.load.plan']._find_product_preset_for_product(line.product_id)

            vals = {
                'name': line.product_id.display_name if line.product_id else line.name,
                'product_id': line.product_id.id if line.product_id else False,
                'product_tmpl_id': line.product_id.product_tmpl_id.id if line.product_id and line.product_id.product_tmpl_id else False,
                'length_in': line.length_in,
                'width_in': line.width_in,
                'height_in': line.height_in,
                'weight_lbs': line.weight_lbs,
                'allow_rotate': line.allow_rotate,
                'stackable': line.stackable,
                'max_stack': line.max_stack,
                'active': True,
            }
            if preset:
                preset.write(vals)
            else:
                preset = Preset.create(vals)
            line.product_preset_id = preset.id
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Product Preset Updated'),
                'message': _('Cargo Architect preset was created/updated from the edited line dimensions.'),
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # For rows created by imports or inline one2many add, apply preset defaults
        # after creation unless caller explicitly supplied non-default dimensions.
        for record, vals in zip(records, vals_list):
            if record.product_id and not vals.get('product_preset_id'):
                explicit_dims = any(k in vals for k in ('length_in', 'width_in', 'height_in'))
                if not explicit_dims or (record.length_in == 48.0 and record.width_in == 40.0 and record.height_in == 48.0):
                    record.action_refresh_from_product_preset()
        return records
