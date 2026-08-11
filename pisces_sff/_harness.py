# -*- coding: utf-8 -*-
# Code to export flowsheets from multiple tools into a standardized JSON format.
# Copyright (C) 2025-, Sarang S. Bhagwat <sarangbhagwat.developer@gmail.com>
#
# This module is under the MIT open-source license. See
# https://github.com/sustainability-software-lab/pisces-standard-flowsheet-format/blob/main/LICENSE
# for license details.

"""
Parent side of the reproducible export harness.

Reads a model's pinned environment specification, provisions the conda
environment it describes, and runs the export inside that environment via
:mod:`pisces_sff._runner`. Running in the provisioned environment (rather than
in whatever environment the caller happens to be in) is what makes the recorded
pins true rather than merely declared.

This module imports only the standard library and PyYAML, so it stays usable
from any environment -- including ones without a simulator installed.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

import yaml

__all__ = ('export_model', 'ensure_environment', 'environment_key',
           'environment_name', 'canonical_environment_text', 'pip_requirements',
           'parse_pip_requirement', 'package_record', 'sha256_bytes',
           'find_conda_exe')

#: Prefix for harness-created conda environments. The remainder of the name is
#: the first 12 hex characters of the environment key.
ENV_NAME_PREFIX = 'sff-'

#: Repository root; the only entry placed on the child's PYTHONPATH.
REPO_ROOT = Path(__file__).resolve().parents[1]

#: SFF schema version exports are written against by default.
DEFAULT_SFF_VERSION = '0.0.6'

#%% Recipe helpers


def sha256_bytes(data):
    """
    Return the SHA-256 hex digest of `data`.

    Parameters
    ----------
    data : bytes

    Returns
    -------
    str
        64-character lowercase hex digest.
    """
    return hashlib.sha256(data).hexdigest()


def canonical_environment_text(text):
    """
    Return a canonical form of an environment specification.

    ``name`` and ``prefix`` are dropped and mappings are dumped with sorted
    keys, so that cosmetic edits -- renaming the environment, reordering keys --
    do not change the environment key and strand the environment already built
    from the same dependencies.

    Parameters
    ----------
    text : str
        Contents of an ``environment.yml`` file.

    Returns
    -------
    str
    """
    specification = yaml.safe_load(text) or {}
    specification = {k: v for k, v in specification.items()
                     if k not in ('name', 'prefix')}
    return yaml.safe_dump(specification, sort_keys=True, default_flow_style=False)


def environment_key(text):
    """
    Return the content-derived identity of an environment specification.

    Parameters
    ----------
    text : str
        Contents of an ``environment.yml`` file.

    Returns
    -------
    str
        SHA-256 hex digest of the canonicalized specification. Two models with
        identical dependencies therefore share one environment, and any change
        to a dependency forks a new one.
    """
    return sha256_bytes(canonical_environment_text(text).encode('utf-8'))


def environment_name(text):
    """
    Return the conda environment name for an environment specification.

    Parameters
    ----------
    text : str
        Contents of an ``environment.yml`` file.

    Returns
    -------
    str
        ``'sff-'`` followed by the first 12 characters of the environment key.
    """
    return ENV_NAME_PREFIX + environment_key(text)[:12]


def pip_requirements(text):
    """
    Return the pip requirement entries of an environment specification.

    Parameters
    ----------
    text : str
        Contents of an ``environment.yml`` file.

    Returns
    -------
    list of str
        Entries of every ``pip:`` mapping under ``dependencies``, in order.
    """
    specification = yaml.safe_load(text) or {}
    entries = []
    for dependency in specification.get('dependencies') or ():
        if isinstance(dependency, dict):
            entries.extend(dependency.get('pip') or ())
    return entries


def parse_pip_requirement(entry):
    """
    Parse one pip requirement entry into a package record.

    Parameters
    ----------
    entry : str
        A pip requirement, e.g. ``'numpy==1.26.4'`` or
        ``'biorefineries @ git+https://host/org/repo@<sha>'``.

    Returns
    -------
    dict or None
        ``{'name', 'version'}`` for a released pin, ``{'name', 'url', 'commit'}``
        for a VCS pin, or ``None`` for a blank line, an option directive, or a
        requirement this parser does not recognize.
    """
    entry = (entry or '').strip()
    if not entry or entry.startswith('-'):
        return None
    if ' @ ' in entry:
        name, _, reference = entry.partition(' @ ')
        return _vcs_record(name.strip(), reference.strip())
    if entry.startswith('git+'):
        return _vcs_record(None, entry)
    if '==' in entry:
        name, _, version = entry.partition('==')
        return {'name': name.strip(), 'version': version.strip()}
    return None


def _vcs_record(name, reference):
    """Build a package record from a ``git+`` reference; None if not one."""
    if not reference.startswith('git+'):
        return None
    url = reference[len('git+'):]
    url, _, fragment = url.partition('#')
    commit = None
    # Split on '@' only within the final path segment, so that a 'user@host'
    # style URL is not mistaken for a commit pin.
    if '@' in url.rsplit('/', 1)[-1]:
        url, _, commit = url.rpartition('@')
    if name is None:
        for part in fragment.split('&'):
            if part.startswith('egg='):
                name = part[len('egg='):]
        if name is None:
            name = url.rstrip('/').rsplit('/', 1)[-1]
            if name.endswith('.git'):
                name = name[:-len('.git')]
    record = {'name': name, 'url': url}
    if commit:
        record['commit'] = commit
    return record


def _normalized(name):
    """Normalize a distribution name for comparison (PEP 503-ish)."""
    return name.strip().lower().replace('_', '-').replace('.', '-')


def package_record(env_text, package_name, branch=None):
    """
    Return the pinned package record for `package_name`.

    Derived from the environment specification rather than declared separately,
    so the provenance recorded in an exported flowsheet cannot disagree with the
    environment the export ran in.

    Parameters
    ----------
    env_text : str
        Contents of an ``environment.yml`` file.
    package_name : str
        Distribution name to look up; matched ignoring case and ``-``/``_``.
    branch : str, optional
        Branch the pinned commit is reachable from, recorded when given.

    Returns
    -------
    dict
        Suitable for ``metadata.reproducibility.simulator_package`` and
        ``.flowsheet_model_package``.

    Raises
    ------
    ValueError
        If no pip requirement in the specification names `package_name`.
    """
    for entry in pip_requirements(env_text):
        record = parse_pip_requirement(entry)
        if record and _normalized(record['name']) == _normalized(package_name):
            if branch:
                record = dict(record, branch=branch)
            return record
    raise ValueError(
        f'no pip requirement for package {package_name!r} in the environment '
        'specification; every package recorded in metadata.reproducibility must '
        'be pinned there.'
    )
