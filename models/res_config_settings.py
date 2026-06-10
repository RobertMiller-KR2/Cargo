# Copyright (C) 2026 KR Squared, Inc.
# License OPL-1 (Odoo Proprietary License v1.0)
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Report company/header options
    ca_report_show_company_logo = fields.Boolean(
        string='Show Company Logo',
        config_parameter='cargo_architect.report_show_company_logo',
        default=True,
    )
    ca_report_show_company_name = fields.Boolean(
        string='Show Company Name',
        config_parameter='cargo_architect.report_show_company_name',
        default=True,
    )
    ca_report_show_company_address = fields.Boolean(
        string='Show Company Address',
        config_parameter='cargo_architect.report_show_company_address',
        default=True,
    )

    # Report section options
    ca_report_show_quality_score = fields.Boolean(
        string='Show Load Quality Score',
        config_parameter='cargo_architect.report_show_quality_score',
        default=True,
    )
    ca_report_show_weight_heat_map = fields.Boolean(
        string='Show Weight Heat Map',
        config_parameter='cargo_architect.report_show_weight_heat_map',
        default=True,
    )
    ca_report_show_weight_distribution = fields.Boolean(
        string='Show Weight Distribution',
        config_parameter='cargo_architect.report_show_weight_distribution',
        default=True,
    )
    ca_report_show_axle_analysis = fields.Boolean(
        string='Show Axle Analysis',
        config_parameter='cargo_architect.report_show_axle_analysis',
        default=True,
    )
    ca_report_show_engineering_analysis = fields.Boolean(
        string='Show Engineering Analysis',
        config_parameter='cargo_architect.report_show_engineering_analysis',
        default=True,
    )
    ca_report_show_additional_capacity = fields.Boolean(
        string='Show Additional Capacity',
        config_parameter='cargo_architect.report_show_additional_capacity',
        default=True,
    )
    ca_report_show_layout_diagrams = fields.Boolean(
        string='Show Layout Diagrams',
        config_parameter='cargo_architect.report_show_layout_diagrams',
        default=True,
    )
    ca_report_show_loading_instructions = fields.Boolean(
        string='Show Loading Instructions',
        config_parameter='cargo_architect.report_show_loading_instructions',
        default=True,
    )
    ca_report_show_load_sequence = fields.Boolean(
        string='Show Load Sequence',
        config_parameter='cargo_architect.report_show_load_sequence',
        default=True,
    )
    ca_report_show_unload_sequence = fields.Boolean(
        string='Show Unload Sequence',
        config_parameter='cargo_architect.report_show_unload_sequence',
        default=True,
    )
    ca_report_show_forklift_accessibility = fields.Boolean(
        string='Show Forklift Accessibility',
        config_parameter='cargo_architect.report_show_forklift_accessibility',
        default=True,
    )
    ca_report_show_qr_passport = fields.Boolean(
        string='Show QR Load Passport',
        config_parameter='cargo_architect.report_show_qr_passport',
        default=True,
    )
    ca_report_show_business_intelligence = fields.Boolean(
        string='Show Business Intelligence',
        config_parameter='cargo_architect.report_show_business_intelligence',
        default=True,
    )
    ca_report_show_footer = fields.Boolean(
        string='Show Footer On Every Page',
        config_parameter='cargo_architect.report_show_footer',
        default=True,
    )

    ca_report_show_technical_coordinates = fields.Boolean(
        string='Show Technical Coordinates',
        config_parameter='cargo_architect.report_show_technical_coordinates',
        default=False,
    )

    _CA_REPORT_BOOLEAN_PARAMS = {
        'ca_report_show_company_logo': ('cargo_architect.report_show_company_logo', True),
        'ca_report_show_company_name': ('cargo_architect.report_show_company_name', True),
        'ca_report_show_company_address': ('cargo_architect.report_show_company_address', True),
        'ca_report_show_quality_score': ('cargo_architect.report_show_quality_score', True),
        'ca_report_show_weight_heat_map': ('cargo_architect.report_show_weight_heat_map', True),
        'ca_report_show_weight_distribution': ('cargo_architect.report_show_weight_distribution', True),
        'ca_report_show_axle_analysis': ('cargo_architect.report_show_axle_analysis', True),
        'ca_report_show_engineering_analysis': ('cargo_architect.report_show_engineering_analysis', True),
        'ca_report_show_additional_capacity': ('cargo_architect.report_show_additional_capacity', True),
        'ca_report_show_layout_diagrams': ('cargo_architect.report_show_layout_diagrams', True),
        'ca_report_show_loading_instructions': ('cargo_architect.report_show_loading_instructions', True),
        'ca_report_show_load_sequence': ('cargo_architect.report_show_load_sequence', True),
        'ca_report_show_unload_sequence': ('cargo_architect.report_show_unload_sequence', True),
        'ca_report_show_forklift_accessibility': ('cargo_architect.report_show_forklift_accessibility', True),
        'ca_report_show_qr_passport': ('cargo_architect.report_show_qr_passport', True),
        'ca_report_show_business_intelligence': ('cargo_architect.report_show_business_intelligence', True),
        'ca_report_show_footer': ('cargo_architect.report_show_footer', True),
        'ca_report_show_technical_coordinates': ('cargo_architect.report_show_technical_coordinates', False),
    }

    @api.model
    def _ca_bool_from_param(self, value, default=False):
        if value in (None, False, ''):
            return bool(default)
        return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 'on')

    @api.model
    def get_values(self):
        """Load Cargo Architect settings from ir.config_parameter.

        The explicit get/set methods are intentionally kept even though the
        fields also define config_parameter. Some hosted/Odoo versions can show
        transient defaults when the parameter has not been created yet; this
        guarantees unchecked boxes stay unchecked after Save.
        """
        res = super().get_values()
        params = self.env['ir.config_parameter'].sudo()
        for field_name, (param_name, default) in self._CA_REPORT_BOOLEAN_PARAMS.items():
            res[field_name] = self._ca_bool_from_param(params.get_param(param_name), default)
        return res

    def set_values(self):
        """Persist Cargo Architect report options to ir.config_parameter."""
        super().set_values()
        params = self.env['ir.config_parameter'].sudo()
        for field_name, (param_name, _default) in self._CA_REPORT_BOOLEAN_PARAMS.items():
            params.set_param(param_name, 'True' if bool(getattr(self, field_name)) else 'False')
