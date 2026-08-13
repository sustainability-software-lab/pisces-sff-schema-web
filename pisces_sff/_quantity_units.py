# -*- coding: utf-8 -*-
# Code to export flowsheets from multiple tools into a standardized JSON format.
# Copyright (C) 2025-, Sarang S. Bhagwat <sarangbhagwat.developer@gmail.com>
#
# This module is under the MIT open-source license. See
# https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/main/LICENSE
# for license details.

"""
Quantity-unit vocabulary and version-gated scalar shape for the SFF exporter.

Deliberately import-light — no biosteam/thermosteam — so schema-level tests and
the exporter share one source of truth for units without paying the simulator
import cost. 'units' in SFF always means unit operations; unit-of-measure
information is always called 'quantity units'.
"""

__all__ = (
    "QUANTITY_UNITS_GLOBAL",
    "scalar",
    "version_tuple",
    "uses_inline_scalar_style",
    "quantity_units_for_design_results",
)

#: First schema version that reports scalars as bare numbers (units resolved via
#: QUANTITY_UNITS_GLOBAL) instead of inline {"value", "units"} pairs.
_BARE_SCALAR_SINCE = (0, 0, 7)

#: Global default quantity units, keyed by canonical quantity name. `aliases`
#: lists every field name the quantity appears under across a flowsheet (so a
#: consumer can resolve, e.g., 'T' or 'total_mass_flow' to its unit); values are
#: BioSTEAM-native unit strings.
QUANTITY_UNITS_GLOBAL = {
    "temperature":             {"aliases": ["temperature", "T", "temperature_limit"], "quantity_units": "K"},
    "pressure":                {"aliases": ["pressure", "P"], "quantity_units": "Pa"},
    "mass_flow":               {"aliases": ["mass_flow", "total_mass_flow", "F_mass"], "quantity_units": "kg/hr"},
    "molar_flow":              {"aliases": ["molar_flow", "total_molar_flow", "F_mol"], "quantity_units": "kmol/hr"},
    "volumetric_flow":         {"aliases": ["volumetric_flow", "total_volumetric_flow", "F_vol"], "quantity_units": "m3/hr"},
    "molar_mass":              {"aliases": ["molar_mass", "MW"], "quantity_units": "g/mol"},
    "price":                   {"aliases": ["price"], "quantity_units": "USD/kg"},
    "electrical_energy_price": {"aliases": ["electrical_energy_price"], "quantity_units": "USD/kWh"},
    "regeneration_price":      {"aliases": ["regeneration_price"], "quantity_units": "USD/kmol"},
    "heat_transfer_price":     {"aliases": ["heat_transfer_price"], "quantity_units": "USD/kJ"},
}


def scalar(value, units, inline):
    """
    Format a scalar quantity for an SFF document.

    Parameters
    ----------
    value : number
        The scalar value.
    units : str
        Unit string, used only in the inline shape.
    inline : bool
        If True, return the pre-0.0.7 ``{"value", "units"}`` pair; otherwise
        return the bare ``value`` (its units come from ``QUANTITY_UNITS_GLOBAL``).

    Returns
    -------
    dict or number
    """
    return {"value": value, "units": units} if inline else value


def version_tuple(version):
    """
    Parse a semantic-version string into a tuple of ints; e.g. ``'0.0.7'`` ->
    ``(0, 0, 7)``.
    """
    return tuple(int(part) for part in str(version).split("."))


def uses_inline_scalar_style(version):
    """
    Return True if `version` predates the bare-number scalar shape (i.e. is
    older than 0.0.7 and must emit inline ``{"value", "units"}`` pairs).
    """
    return version_tuple(version) < _BARE_SCALAR_SINCE


def quantity_units_for_design_results(unit):
    """
    Map each of a unit operation's ``design_results`` keys to its unit string.

    Sourced from the simulator's per-design-result units (BioSTEAM ``_units``).
    A key present in ``design_results`` but absent from ``_units`` maps to ``''``
    (dimensionless or unspecified).

    Parameters
    ----------
    unit : object
        A unit operation exposing ``design_results`` and ``_units`` mappings.

    Returns
    -------
    dict of str -> str
    """
    units_map = getattr(unit, "_units", {}) or {}
    design = getattr(unit, "design_results", {}) or {}
    return {key: units_map.get(key, "") for key in design}
