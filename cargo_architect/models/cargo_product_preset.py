from odoo import fields, models


class CargoProductPreset(models.Model):
    _name = 'cargo.architect.product.preset'
    _description = 'Cargo Architect Product Preset'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    product_id = fields.Many2one('product.product', string='Odoo Product Variant')
    product_tmpl_id = fields.Many2one('product.template', string='Odoo Product Template')
    length_in = fields.Float(string='Length (in)', required=True, default=48.0)
    width_in = fields.Float(string='Width (in)', required=True, default=40.0)
    height_in = fields.Float(string='Height (in)', required=True, default=48.0)
    weight_lbs = fields.Float(string='Weight (lb)', default=0.0)
    allow_rotate = fields.Boolean(string='Allow L/W Rotation', default=True)
    stackable = fields.Boolean(default=True)
    max_stack = fields.Integer(default=0, help='0 means no explicit stack limit.')
