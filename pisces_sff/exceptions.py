# -*- coding: utf-8 -*-
# Code to export flowsheets from multiple tools into a standardized JSON format.
# Copyright (C) 2025-, Sarang S. Bhagwat <sarangbhagwat.developer@gmail.com>
#
# This module is under the MIT open-source license. See
# https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/main/LICENSE
# for license details.

"""
Exception hierarchy for pisces_sff.

Deliberately import-light — no biosteam/thermosteam — so it can be imported (and
tested) without paying the simulator import cost. These types replace the bare
``breakpoint()`` traps that previously sat in the exporter's error branches: a
``breakpoint()`` hangs forever in a TTY-less or CI run instead of surfacing the
failure, whereas raising one of these exceptions fails loudly with context and
chains the underlying cause via ``raise ... from``.

Hierarchy::

    SFFError                     (base for everything this package raises)
    └── SFFExportError           (a flowsheet export could not be completed)
        ├── FlowsheetWriteError  (the assembled document could not be written)
        └── DesignInputSpecError (a unit's design input spec could not be read)

Catch a specific subclass to handle one failure mode, ``SFFExportError`` to
handle any export failure, or ``SFFError`` to handle anything this package
raises.
"""

__all__ = (
    "SFFError",
    "SFFExportError",
    "FlowsheetWriteError",
    "DesignInputSpecError",
)


class SFFError(Exception):
    """Base class for all exceptions raised by pisces_sff."""


class SFFExportError(SFFError):
    """
    A flowsheet export could not be completed.

    Base class for the specific failures the BioSTEAM exporter can hit while
    assembling or writing an SFF document.
    """


class FlowsheetWriteError(SFFExportError):
    """
    The assembled SFF document could not be serialized or written to disk.

    Raised when ``json.dump`` or the file write in the exporter's write step
    fails (e.g., a non-serializable value slipped into the document, or the
    output path is not writable).
    """


class DesignInputSpecError(SFFExportError):
    """
    A unit operation's design input spec could not be read.

    Raised when reading one of a unit's design-input attributes fails while
    building its ``design_input_specs`` block.
    """
