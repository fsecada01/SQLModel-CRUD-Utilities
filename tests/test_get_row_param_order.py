"""
Positional-argument parity for ``get_row`` (issue #19).

``sync.get_row`` used to order its optional parameters differently from
``a_sync.get_row`` and both ``get_rows``, so a positional call bound the same
value to different parameters depending on the module.
"""

import inspect

from sqlmodel_crud_utils import a_sync, sync

from .models import MockModel

POSITIONAL_ARGS = (1, "session", MockModel, True, ["mock_models"], True, ["x"])


def _bound(func):
    return dict(inspect.signature(func).bind(*POSITIONAL_ARGS).arguments)


def test_positional_binding_is_identical_in_sync_and_async():
    assert _bound(sync.get_row) == _bound(a_sync.get_row)


def test_optional_parameter_order_matches_get_rows():
    def names(func):
        return [
            p
            for p in inspect.signature(func).parameters
            if p in {"selectin", "select_in_keys", "lazy", "lazy_load_keys"}
        ]

    expected = ["selectin", "select_in_keys", "lazy", "lazy_load_keys"]
    assert names(sync.get_row) == expected
    assert names(a_sync.get_row) == expected
    assert names(sync.get_rows) == expected
    assert names(a_sync.get_rows) == expected
