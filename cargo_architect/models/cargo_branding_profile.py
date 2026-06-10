from odoo import fields, models


class CargoBrandingProfile(models.Model):
    _name = 'cargo.architect.branding.profile'
    _description = 'Cargo Architect Customer Branding Profile'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one('res.partner', string='Customer')
    logo = fields.Binary(string='Report Logo')
    primary_color = fields.Char(default='#0b2f6b')
    secondary_color = fields.Char(default='#bfdbfe')
    footer_text = fields.Char(default='Cargo Architect Load Report')
