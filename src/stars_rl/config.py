"""Strict YAML serialization of explicit inputs; loading never samples or solves."""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path
from types import UnionType
from typing import get_args, get_origin, get_type_hints

import yaml

from .models import Deployment, Scenario, WindowOutcome, check_type, validate_deployment_structure


class _UniqueSafeLoader(yaml.SafeLoader):
    """SafeLoader normally accepts duplicate keys and silently keeps the last."""


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str):
            raise ValueError("YAML mapping keys must be strings")
        if key in result:
            raise ValueError(f"duplicate YAML field: {key}")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


_UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _decode(data, annotation, path: str):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is UnionType:
        errors = []
        for option in args:
            try:
                return _decode(data, option, path)
            except ValueError as exc:
                errors.append(str(exc))
        raise ValueError(f"{path}: no matching type; {'; '.join(errors)}")
    if origin is tuple:
        if type(data) is not list:
            raise ValueError(f"{path}: expected YAML/JSON sequence")
        return tuple(_decode(item,args[0],f"{path}[{i}]") for i,item in enumerate(data))
    if is_dataclass(annotation):
        if type(data) is not dict:
            raise ValueError(f"{path}: expected mapping")
        if not all(isinstance(key,str) for key in data):
            raise ValueError(f"{path}: field names must be strings")
        names = {f.name for f in fields(annotation)}
        if names != data.keys():
            raise ValueError(f"{path}: missing fields {sorted(names-data.keys())}; "
                             f"unknown fields {sorted(data.keys()-names)}")
        hints = get_type_hints(annotation)
        values = {name:_decode(data[name],hints[name],f"{path}.{name}") for name in data}
        try:
            return annotation(**values)
        except ValueError as exc:
            raise ValueError(f"{path}: {exc}") from exc
    check_type(data,annotation,path)
    return data


def _encode(record):
    if is_dataclass(record):
        return {f.name:_encode(getattr(record,f.name)) for f in fields(record)}
    if isinstance(record,tuple):
        return [_encode(item) for item in record]
    return record


def scenario_from_dict(data: dict) -> Scenario:
    return _decode(data,Scenario,"scenario")


def scenario_to_dict(scenario: Scenario) -> dict:
    check_type(scenario,Scenario,"scenario")
    return _encode(scenario)


def load_scenario(path: str | Path) -> Scenario:
    try:
        data = yaml.load(Path(path).read_text(encoding="utf-8"),Loader=_UniqueSafeLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid or unsupported YAML: {exc}") from exc
    return scenario_from_dict(data)


def dump_scenario(scenario: Scenario, path: str | Path) -> None:
    Path(path).write_text(yaml.safe_dump(scenario_to_dict(scenario),sort_keys=False),encoding="utf-8")


def deployment_to_dict(deployment: Deployment) -> dict:
    check_type(deployment,Deployment,"deployment")
    return _encode(deployment)


def deployment_from_dict(data: dict, scenario: Scenario) -> Deployment:
    deployment = _decode(data,Deployment,"deployment")
    validate_deployment_structure(deployment,scenario)
    return deployment


def outcome_to_dict(outcome: WindowOutcome) -> dict:
    check_type(outcome,WindowOutcome,"outcome")
    return _encode(outcome)


def outcome_from_dict(data: dict, scenario: Scenario) -> WindowOutcome:
    outcome = _decode(data,WindowOutcome,"outcome")
    if outcome.window_index >= scenario.window_count:
        raise ValueError("outcome: window_index outside scenario")
    if outcome.deployment is not None:
        validate_deployment_structure(outcome.deployment,scenario)
    return outcome
