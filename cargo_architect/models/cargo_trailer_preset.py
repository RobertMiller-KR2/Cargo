from odoo import fields, models


class CargoTrailerPreset(models.Model):
    _name = 'cargo.architect.trailer.preset'
    _description = 'Cargo Architect Trailer Preset'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    length_in = fields.Float(string='Length (in)', required=True, default=636.0)
    width_in = fields.Float(string='Width (in)', required=True, default=98.0)
    height_in = fields.Float(string='Height (in)', required=True, default=110.0)
    max_payload_lbs = fields.Float(string='Max Payload (lb)', default=45000.0)
    trailer_axle_position_in = fields.Float(string='Trailer Axle Position from Nose (in)', default=516.0)
    fifth_wheel_position_in = fields.Float(string='Kingpin/Fifth Wheel Position from Nose (in)', default=36.0)
