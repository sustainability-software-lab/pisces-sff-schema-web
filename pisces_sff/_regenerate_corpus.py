# -*- coding: utf-8 -*-
# Code to export flowsheets from multiple tools into a standardized JSON format.
# Copyright (C) 2025-, Sarang S. Bhagwat <sarangbhagwat.developer@gmail.com>
#
# This module is under the MIT open-source license. See
# https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/main/LICENSE
# for license details.

"""
Regenerate the committed reference corpus by exporting every model that has a
recipe under ``pisces_sff/models/``.

Two entry points share one loop:

* :func:`regenerate_corpus` -- exports each discovered model into a
  caller-chosen directory. The Tier 3 test calls it with a temporary directory,
  so running the test never touches the committed corpus.
* ``python -m pisces_sff._regenerate_corpus`` -- the one deliberate command that
  writes the committed corpus files in
  ``pisces_sff/exported_flowsheets/bioindustrial_park/``. Regenerating the
  committed corpus is an announced act, never a side effect of a test run.

Imports nothing heavy at module top: :func:`pisces_sff.export_model` is imported
lazily inside :func:`regenerate_corpus`, so this module stays loadable by a
Tier-1 test (which injects a fake exporter) without pulling in biosteam.
"""

from pathlib import Path

__all__ = ('regenerate_corpus', 'iter_model_dirs', 'MODELS_ROOT', 'CORPUS_DIR')

#: Root of the per-model recipes; every directory holding a load.py is a model.
MODELS_ROOT = Path(__file__).resolve().parent / 'models'

#: Destination for the committed reference corpus.
CORPUS_DIR = (Path(__file__).resolve().parent
              / 'exported_flowsheets' / 'bioindustrial_park')


def iter_model_dirs(models_root=MODELS_ROOT):
    """
    Return every directory holding a ``load.py``, at any depth under
    `models_root`, sorted for a stable order.

    Parameters
    ----------
    models_root : str or Path, optional

    Returns
    -------
    list of Path
    """
    return sorted(p.parent for p in Path(models_root).rglob('load.py'))


def regenerate_corpus(output_dir, models_root=MODELS_ROOT, export=None):
    """
    Export every discovered model into `output_dir` and return the written paths.

    Parameters
    ----------
    output_dir : str or Path
        Directory to write ``<model_name>.json`` files into; created if absent.
    models_root : str or Path, optional
        Root to discover model recipes under.
    export : callable, optional
        ``export(model_dir, output_path)`` used to export one model. Defaults to
        :func:`pisces_sff.export_model` (the full harness), imported lazily so
        this module stays import-light for Tier 1. Tests inject a fake here.

    Returns
    -------
    list of Path
        The written output files, one per discovered model, in discovery order.
    """
    if export is None:
        from ._harness import export_model
        export = export_model
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for model_dir in iter_model_dirs(models_root):
        output_path = output_dir / f'{model_dir.name}.json'
        export(model_dir, output_path)
        written.append(output_path)
    return written


def main(argv=None):
    """
    Regenerate the committed corpus in-place. See the module docstring.

    Returns
    -------
    int
        Process exit code.
    """
    written = regenerate_corpus(CORPUS_DIR)
    for path in written:
        print(f'wrote {path}')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
