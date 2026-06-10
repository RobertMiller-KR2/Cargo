# Cargo Architect Service Modules

This package is introduced in v2.0.33 as the target home for extracted optimizer, validation, stability, securement, and trailer-recommendation services.

The v2.0.33 release safely splits Odoo model classes into separate files first, while preserving behavior. Future releases should progressively move pure algorithm helpers from `models/cargo_load_plan.py` into these service modules with unit coverage.
