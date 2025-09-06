"""
Pytest configuration and shared fixtures for Lighter Strategy tests
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from lighter_strategy.config import Config
from lighter_strategy.wallet_manager import WalletPair, WalletManager
from lighter_strategy.balance_checker import BalanceChecker, BalanceInfo
from lighter_strategy.order_manager import OrderManager, Order, OrderType, OrderStatus
from lighter_strategy.liquidation_monitor import LiquidationMonitor, PositionInfo, PositionStatus


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_config():
    """Mock configuration object"""
    config = Mock(spec=Config)
    config.api_endpoint = "https://api.lighter.xyz"
    config.chain_id = 1
    config.minimum_usdc = 500.0
    config.default_market = "SOL"
    return config


@pytest.fixture
def mock_lighter_client():
    """Mock Lighter API client"""
    client = AsyncMock()
    client.get_balance = AsyncMock(return_value={'balance': '1000.0'})
    client.get_position = AsyncMock(return_value={
        'market': 'SOL',
        'side': 'long',
        'size': '10.0',
        'entry_price': '50.0',
        'mark_price': '52.0',
        'liquidation_price': '45.0',
        'margin': '100.0',
        'unrealized_pnl': '20.0',
        'health_ratio': '0.8',
        'is_liquidated': False
    })
    client.create_order = AsyncMock(return_value={'order_id': 'test_order_123'})
    client.get_order = AsyncMock(return_value={
        'order_id': 'test_order_123',
        'status': 'open',
        'filled_size': '0'
    })
    client.cancel_order = AsyncMock(return_value={'success': True})
    client.close = AsyncMock()
    return client


@pytest.fixture
def sample_wallet_data():
    """Sample wallet configuration data"""
    return [
        {
            'address_a': '0x1234567890abcdef1234567890abcdef12345678',
            'address_b': '0xabcdef1234567890abcdef1234567890abcdef12',
            'private_key_a': 'private_key_a_test',
            'private_key_b': 'private_key_b_test'
        },
        {
            'address_a': '0x2234567890abcdef1234567890abcdef12345678',
            'address_b': '0xbbcdef1234567890abcdef1234567890abcdef12',
            'private_key_a': 'private_key_a_test2',
            'private_key_b': 'private_key_b_test2'
        }
    ]


@pytest.fixture
def mock_wallet_pair(mock_lighter_client):
    """Mock wallet pair with clients"""
    wallet_pair = WalletPair(
        address_a='0x1234567890abcdef1234567890abcdef12345678',
        address_b='0xabcdef1234567890abcdef1234567890abcdef12',
        private_key_a='test_key_a',
        private_key_b='test_key_b'
    )
    wallet_pair.client_a = mock_lighter_client
    wallet_pair.client_b = mock_lighter_client
    return wallet_pair


@pytest.fixture
def wallet_manager(mock_config):
    """Wallet manager instance"""
    return WalletManager(mock_config)


@pytest.fixture
def balance_checker():
    """Balance checker instance"""
    return BalanceChecker(cache_duration_seconds=60)


@pytest.fixture
def order_manager():
    """Order manager instance"""
    return OrderManager()


@pytest.fixture
def liquidation_monitor(order_manager):
    """Liquidation monitor instance"""
    return LiquidationMonitor(order_manager)


@pytest.fixture
def sample_order():
    """Sample order object"""
    return Order(
        order_id='test_order_123',
        wallet_address='0x1234567890abcdef1234567890abcdef12345678',
        market='SOL',
        order_type=OrderType.LIMIT_BUY,
        price=50.0,
        size=10.0,
        status=OrderStatus.OPEN
    )


@pytest.fixture
def sample_balance_info():
    """Sample balance info object"""
    return BalanceInfo(
        address='0x1234567890abcdef1234567890abcdef12345678',
        usdc_balance=1000.0,
        timestamp=datetime.now(),
        meets_minimum=True
    )


@pytest.fixture
def sample_position_info():
    """Sample position info object"""
    return PositionInfo(
        wallet_address='0x1234567890abcdef1234567890abcdef12345678',
        market='SOL',
        side='long',
        size=10.0,
        entry_price=50.0,
        mark_price=52.0,
        liquidation_price=45.0,
        margin=100.0,
        unrealized_pnl=20.0,
        health_ratio=0.8,
        status=PositionStatus.HEALTHY
    )


@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection"""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock(return_value='{"type": "update", "data": {}}')
    ws.close = AsyncMock()
    return ws