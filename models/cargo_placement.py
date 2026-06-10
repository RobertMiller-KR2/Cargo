# Copyright (C) 2026 KR Squared, Inc.
# License OPL-1 (Odoo Proprietary License v1.0)
from odoo import fields, models, _


class CargoPlacement(models.Model):
    _name = 'cargo.architect.placement'
    _description = 'Cargo Architect Placement'
    _order = 'sequence, id'

    plan_id = fields.Many2one('cargo.architect.load.plan', required=True, ondelete='cascade')
    line_id = fields.Many2one('cargo.architect.load.line', ondelete='set null')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    x_in = fields.Float()
    y_in = fields.Float()
    z_in = fields.Float()
    length_in = fields.Float()
    width_in = fields.Float()
    height_in = fields.Float()
    weight_lbs = fields.Float()
    locked = fields.Boolean(default=False)
    rotated = fields.Boolean(string='Rotated', compute='_compute_rotated')

    def _compute_rotated(self):
        for placement in self:
            rotated = False
            line = placement.line_id
            if line and placement.length_in and placement.width_in and line.length_in and line.width_in:
                same = abs((placement.length_in or 0.0) - (line.length_in or 0.0)) <= 0.01 and abs((placement.width_in or 0.0) - (line.width_in or 0.0)) <= 0.01
                swapped = abs((placement.length_in or 0.0) - (line.width_in or 0.0)) <= 0.01 and abs((placement.width_in or 0.0) - (line.length_in or 0.0)) <= 0.01
                rotated = bool(swapped and not same)
            placement.rotated = rotated


    def action_unlock_placement(self):
        """Unlock this placement from the placement list or planner.

        v2.0.18 lets users unlock individual manually positioned blocks
        without unlocking the entire load.  Approved/released/loaded plans
        still respect the normal modification lock.
        """
        for placement in self:
            placement.plan_id._ensure_can_modify()
        for placement in self:
            if placement.locked:
                placement.plan_id._push_placement_history(label=_('Before Unlock Placement'))
        self.write({'locked': False})
        if len(self) == 1:
            return self.plan_id._approval_notification(
                _('Placement Unlocked'),
                _('%s is unlocked. The optimizer may move it on the next run.') % (self.name or _('Placement')),
                'success'
            )
        return True
