# -*- coding: utf-8 -*-
# Code to export flowsheets from multiple tools into a standardized JSON format.
# Copyright (C) 2025-, Sarang S. Bhagwat <sarangbhagwat.developer@gmail.com>
#
# This module is under the MIT open-source license. See
# https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/main/LICENSE
# for license details.

import json
from pathlib import Path

__all__ = ('read_schema_version', 'SCHEMA_FILE')

#%% Schema location

# The schema is the product of this repository, so its "version" field is the
# single source of truth for the SFF version; the package version follows it.
SCHEMA_FILE = Path(__file__).parent / 'schema' / 'sff_schema.json'

#%%
def read_schema_version(schema_file=SCHEMA_FILE):
    """
    Read the SFF version declared by a JSON Schema file.

    This is what sets ``pisces_sff.__version__``, so that bumping ``"version"``
    in the schema is the only edit a version bump requires -- the package
    version cannot drift out of sync with the spec it describes.

    Parameters
    ----------
    schema_file : str or pathlib.Path, optional
        Path to the SFF JSON Schema file. Defaults to the schema shipped with
        this package (``SCHEMA_FILE``).

    Returns
    -------
    str
        The value of the schema's top-level ``"version"`` field, in semantic
        versioning notation; e.g., ``'0.0.5'``.

    Raises
    ------
    KeyError
        If the schema file does not declare a top-level ``"version"``.
    """
    with open(schema_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    try:
        return schema['version']
    except KeyError:
        raise KeyError(
            f"schema file {str(schema_file)!r} does not declare a top-level "
            '"version" field; it is the source of truth for the SFF version.'
        ) from None
