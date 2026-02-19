"""Tests that QueryParser and ResultFusion reuse aiohttp.ClientSession."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_query_parser_has_session_attribute():
    from d4bl.query.parser import QueryParser
    p = QueryParser()
    assert hasattr(p, "_session")
    assert p._session is None


def test_query_parser_has_close_method():
    from d4bl.query.parser import QueryParser
    p = QueryParser()
    assert callable(getattr(p, "close", None))


@pytest.mark.asyncio
async def test_query_parser_close_is_noop_when_no_session():
    from d4bl.query.parser import QueryParser
    p = QueryParser()
    await p.close()  # Must not raise


def test_result_fusion_has_session_attribute():
    from d4bl.query.fusion import ResultFusion
    f = ResultFusion()
    assert hasattr(f, "_session")
    assert f._session is None


def test_result_fusion_has_close_method():
    from d4bl.query.fusion import ResultFusion
    f = ResultFusion()
    assert callable(getattr(f, "close", None))


def test_query_engine_has_close_method():
    from d4bl.query.engine import QueryEngine
    e = QueryEngine()
    assert callable(getattr(e, "close", None))


@pytest.mark.asyncio
async def test_query_engine_close_delegates_to_parser_and_fusion():
    from unittest.mock import AsyncMock
    from d4bl.query.engine import QueryEngine

    engine = QueryEngine()
    engine.parser.close = AsyncMock()
    engine.fusion.close = AsyncMock()

    await engine.close()

    engine.parser.close.assert_awaited_once()
    engine.fusion.close.assert_awaited_once()
