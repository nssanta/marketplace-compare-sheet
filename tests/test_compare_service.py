"""
Unit тесты на compare_service в demo режиме.
Demo должен работать стабильно end-to-end без внешних зависимостей.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.compare import CompareRequest
from app.services.compare_service import run_comparison

client = TestClient(app)


# ─── HTTP тесты ───────────────────────────────────────────

def test_compare_demo_wb_ozon():
    """Полный demo запрос WB + Ozon возвращает корректный ответ."""
    response = client.post("/api/v1/compare", json={
        "query": "iphone 15 case",
        "marketplaces": ["wb", "ozon"],
        "top_n": 5,
        "mode": "demo"
    })
    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["source_mode_used"] == "demo"
    assert len(data["wb_items"]) == 5
    assert len(data["ozon_items"]) == 5
    assert data["summary"]["wb_count"] == 5
    assert data["summary"]["ozon_count"] == 5
    assert data["summary"]["price_winner"] in ("wb", "ozon", "tie")


def test_compare_demo_wb_only():
    """Запрос только WB возвращает ozon_items пустым."""
    response = client.post("/api/v1/compare", json={
        "query": "наушники",
        "marketplaces": ["wb"],
        "top_n": 3,
        "mode": "demo"
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["wb_items"]) == 3
    assert len(data["ozon_items"]) == 0


def test_compare_demo_has_run_id():
    """Каждый ответ содержит run_id."""
    r1 = client.post("/api/v1/compare", json={"query": "test", "mode": "demo"})
    r2 = client.post("/api/v1/compare", json={"query": "test", "mode": "demo"})
    assert r1.json()["run_id"] != r2.json()["run_id"]


def test_compare_invalid_empty_query():
    """Пустой query должен вернуть 422."""
    response = client.post("/api/v1/compare", json={
        "query": "",
        "mode": "demo"
    })
    assert response.status_code == 422


def test_compare_live_public_fallback():
    """live_public без реального источника должен сделать fallback в demo."""
    response = client.post("/api/v1/compare", json={
        "query": "iphone case",
        "marketplaces": ["ozon"],
        "top_n": 3,
        "mode": "live_public"
    })
    assert response.status_code == 200
    data = response.json()
    # Ozon без ключа → fallback
    assert data["source_mode_used"] == "demo"
    assert len(data["errors"]) > 0


# ─── Unit тесты на сервис напрямую ────────────────────────

@pytest.mark.asyncio
async def test_service_summary_winner():
    """Summary правильно определяет победителя по цене."""
    request = CompareRequest(
        query="тест",
        marketplaces=["wb", "ozon"],
        top_n=10,
        mode="demo",
    )
    result = await run_comparison(request)
    assert result.summary.price_winner in ("wb", "ozon", "tie", "n/a")
    assert result.summary.wb_min_price > 0
    assert result.summary.ozon_min_price > 0
