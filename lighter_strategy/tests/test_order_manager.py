"""
Unit tests for Order Manager module
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
import asyncio

from lighter_strategy.order_manager import (
    OrderManager, Order, OrderType, OrderStatus
)
from lighter_strategy.utils.exceptions import OrderCreationError


class TestOrder:
    """Test cases for Order dataclass"""
    
    def test_order_creation(self):
        """Test creating an order object"""
        order = Order(
            order_id="order_123",
            wallet_address="0xabc123",
            market="SOL",
            order_type=OrderType.LIMIT_BUY,
            price=50.0,
            size=10.0
        )
        
        assert order.order_id == "order_123"
        assert order.wallet_address == "0xabc123"
        assert order.market == "SOL"
        assert order.order_type == OrderType.LIMIT_BUY
        assert order.price == 50.0
        assert order.size == 10.0
        assert order.status == OrderStatus.PENDING
        assert order.filled_size == 0.0
        assert order.remaining_size == 10.0
    
    def test_order_update_fill(self):
        """Test updating order fill information"""
        order = Order(
            order_id="order_123",
            wallet_address="0xabc123",
            market="SOL",
            order_type=OrderType.LIMIT_BUY,
            price=50.0,
            size=10.0
        )
        
        order.update_fill(3.0)
        assert order.filled_size == 3.0
        assert order.remaining_size == 7.0
        assert order.status == OrderStatus.PARTIALLY_FILLED
        
        order.update_fill(7.0)
        assert order.filled_size == 10.0
        assert order.remaining_size == 0.0
        assert order.status == OrderStatus.FILLED
    
    def test_order_is_complete(self):
        """Test checking if order is complete"""
        order = Order(
            order_id="order_123",
            wallet_address="0xabc123",
            market="SOL",
            order_type=OrderType.LIMIT_BUY,
            price=50.0,
            size=10.0
        )
        
        assert order.is_complete() is False
        
        order.status = OrderStatus.FILLED
        assert order.is_complete() is True
        
        order.status = OrderStatus.CANCELLED
        assert order.is_complete() is True
        
        order.status = OrderStatus.FAILED
        assert order.is_complete() is True
    
    def test_order_string_representation(self):
        """Test string representation of order"""
        order = Order(
            order_id="order_123456789",
            wallet_address="0xabc123",
            market="SOL",
            order_type=OrderType.LIMIT_BUY,
            price=50.0,
            size=10.0,
            filled_size=3.0
        )
        
        str_repr = str(order)
        assert "order_12" in str_repr
        assert "limit_buy" in str_repr
        assert "SOL" in str_repr
        assert "50.0" in str_repr
        assert "3.0/10.0" in str_repr


class TestOrderManager:
    """Test cases for OrderManager class"""
    
    @pytest.mark.asyncio
    async def test_create_limit_buy_order_success(self, order_manager, mock_lighter_client):
        """Test successful limit buy order creation"""
        mock_lighter_client.create_order.return_value = {'order_id': 'buy_order_123'}
        
        order = await order_manager.create_limit_buy_order(
            client=mock_lighter_client,
            wallet_address="0xabc123",
            market="SOL",
            price=45.0,
            size=5.0
        )
        
        assert order.order_id == 'buy_order_123'
        assert order.order_type == OrderType.LIMIT_BUY
        assert order.price == 45.0
        assert order.size == 5.0
        assert order.status == OrderStatus.OPEN
        assert 'buy_order_123' in order_manager.orders
        assert 'buy_order_123' in order_manager.active_orders
    
    @pytest.mark.asyncio
    async def test_create_limit_buy_order_invalid_params(self, order_manager, mock_lighter_client):
        """Test buy order creation with invalid parameters"""
        with pytest.raises(OrderCreationError) as exc_info:
            await order_manager.create_limit_buy_order(
                client=mock_lighter_client,
                wallet_address="0xabc123",
                market="SOL",
                price=-10.0,
                size=5.0
            )
        assert "Invalid price" in str(exc_info.value)
        
        with pytest.raises(OrderCreationError) as exc_info:
            await order_manager.create_limit_buy_order(
                client=mock_lighter_client,
                wallet_address="0xabc123",
                market="SOL",
                price=50.0,
                size=0.0
            )
        assert "Invalid size" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_limit_sell_order_success(self, order_manager, mock_lighter_client):
        """Test successful limit sell order creation"""
        mock_lighter_client.create_order.return_value = {'order_id': 'sell_order_456'}
        
        order = await order_manager.create_limit_sell_order(
            client=mock_lighter_client,
            wallet_address="0xdef456",
            market="SOL",
            price=55.0,
            size=8.0
        )
        
        assert order.order_id == 'sell_order_456'
        assert order.order_type == OrderType.LIMIT_SELL
        assert order.price == 55.0
        assert order.size == 8.0
        assert order.status == OrderStatus.OPEN
    
    @pytest.mark.asyncio
    async def test_create_order_no_order_id_returned(self, order_manager, mock_lighter_client):
        """Test order creation when API doesn't return order ID"""
        mock_lighter_client.create_order.return_value = {}
        
        with pytest.raises(OrderCreationError) as exc_info:
            await order_manager.create_limit_buy_order(
                client=mock_lighter_client,
                wallet_address="0xabc123",
                market="SOL",
                price=50.0,
                size=10.0
            )
        assert "No order ID returned" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_order_status_open(self, order_manager, mock_lighter_client, sample_order):
        """Test getting status of open order"""
        order_manager.orders[sample_order.order_id] = sample_order
        mock_lighter_client.get_order.return_value = {
            'status': 'open',
            'filled_size': '0'
        }
        
        status = await order_manager.get_order_status(sample_order.order_id, mock_lighter_client)
        
        assert status == OrderStatus.OPEN
        assert sample_order.filled_size == 0.0
    
    @pytest.mark.asyncio
    async def test_get_order_status_partially_filled(self, order_manager, mock_lighter_client, sample_order):
        """Test getting status of partially filled order"""
        order_manager.orders[sample_order.order_id] = sample_order
        order_manager.active_orders[sample_order.order_id] = sample_order
        mock_lighter_client.get_order.return_value = {
            'status': 'open',
            'filled_size': '4.5'
        }
        
        status = await order_manager.get_order_status(sample_order.order_id, mock_lighter_client)
        
        assert status == OrderStatus.PARTIALLY_FILLED
        assert sample_order.filled_size == 4.5
        assert sample_order.remaining_size == 5.5
    
    @pytest.mark.asyncio
    async def test_get_order_status_filled(self, order_manager, mock_lighter_client, sample_order):
        """Test getting status of filled order"""
        order_manager.orders[sample_order.order_id] = sample_order
        order_manager.active_orders[sample_order.order_id] = sample_order
        mock_lighter_client.get_order.return_value = {
            'status': 'filled',
            'filled_size': '10.0'
        }
        
        status = await order_manager.get_order_status(sample_order.order_id, mock_lighter_client)
        
        assert status == OrderStatus.FILLED
        assert sample_order.order_id not in order_manager.active_orders
        assert sample_order in order_manager.filled_orders
    
    @pytest.mark.asyncio
    async def test_cancel_order_success(self, order_manager, mock_lighter_client, sample_order):
        """Test successful order cancellation"""
        order_manager.orders[sample_order.order_id] = sample_order
        order_manager.active_orders[sample_order.order_id] = sample_order
        mock_lighter_client.cancel_order.return_value = {'success': True}
        
        result = await order_manager.cancel_order(sample_order.order_id, mock_lighter_client)
        
        assert result is True
        assert sample_order.status == OrderStatus.CANCELLED
        assert sample_order.order_id not in order_manager.active_orders
    
    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, order_manager, mock_lighter_client):
        """Test failed order cancellation"""
        mock_lighter_client.cancel_order.return_value = {'success': False}
        
        result = await order_manager.cancel_order('nonexistent_order', mock_lighter_client)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_cancel_all_orders(self, order_manager, mock_lighter_client):
        """Test cancelling all orders"""
        order1 = Order(
            order_id="order_1",
            wallet_address="0xabc123",
            market="SOL",
            order_type=OrderType.LIMIT_BUY,
            price=50.0,
            size=10.0
        )
        order2 = Order(
            order_id="order_2",
            wallet_address="0xdef456",
            market="SOL",
            order_type=OrderType.LIMIT_SELL,
            price=55.0,
            size=5.0
        )
        
        order_manager.active_orders = {
            "order_1": order1,
            "order_2": order2
        }
        mock_lighter_client.cancel_order.return_value = {'success': True}
        
        cancelled_count = await order_manager.cancel_all_orders(mock_lighter_client)
        
        assert cancelled_count == 2
        assert mock_lighter_client.cancel_order.call_count == 2
    
    @pytest.mark.asyncio
    async def test_cancel_all_orders_filtered_by_wallet(self, order_manager, mock_lighter_client):
        """Test cancelling orders filtered by wallet address"""
        order1 = Order(
            order_id="order_1",
            wallet_address="0xabc123",
            market="SOL",
            order_type=OrderType.LIMIT_BUY,
            price=50.0,
            size=10.0
        )
        order2 = Order(
            order_id="order_2",
            wallet_address="0xdef456",
            market="SOL",
            order_type=OrderType.LIMIT_SELL,
            price=55.0,
            size=5.0
        )
        
        order_manager.active_orders = {
            "order_1": order1,
            "order_2": order2
        }
        mock_lighter_client.cancel_order.return_value = {'success': True}
        
        cancelled_count = await order_manager.cancel_all_orders(
            mock_lighter_client,
            wallet_address="0xabc123"
        )
        
        assert cancelled_count == 1
        assert mock_lighter_client.cancel_order.call_count == 1
    
    def test_get_filled_orders(self, order_manager, sample_order):
        """Test getting filled orders"""
        sample_order.status = OrderStatus.FILLED
        order_manager.filled_orders = [sample_order]
        
        filled = order_manager.get_filled_orders()
        
        assert len(filled) == 1
        assert filled[0] == sample_order
        assert filled is not order_manager.filled_orders
    
    def test_get_active_orders(self, order_manager):
        """Test getting active orders"""
        order1 = Order(
            order_id="order_1",
            wallet_address="0xabc123",
            market="SOL",
            order_type=OrderType.LIMIT_BUY,
            price=50.0,
            size=10.0
        )
        order2 = Order(
            order_id="order_2",
            wallet_address="0xdef456",
            market="SOL",
            order_type=OrderType.LIMIT_SELL,
            price=55.0,
            size=5.0
        )
        
        order_manager.active_orders = {
            "order_1": order1,
            "order_2": order2
        }
        
        active = order_manager.get_active_orders()
        assert len(active) == 2
        
        active_filtered = order_manager.get_active_orders(wallet_address="0xabc123")
        assert len(active_filtered) == 1
        assert active_filtered[0] == order1
    
    @pytest.mark.asyncio
    async def test_monitor_order_fills(self, order_manager, mock_lighter_client):
        """Test order fill monitoring"""
        order = Order(
            order_id="order_1",
            wallet_address="0xabc123",
            market="SOL",
            order_type=OrderType.LIMIT_BUY,
            price=50.0,
            size=10.0
        )
        
        order_manager.active_orders = {"order_1": order}
        mock_lighter_client.get_order.return_value = {
            'status': 'open',
            'filled_size': '0'
        }
        
        clients = {"0xabc123": mock_lighter_client}
        
        monitor_task = asyncio.create_task(
            order_manager.monitor_order_fills(clients, interval_seconds=0.1)
        )
        
        await asyncio.sleep(0.2)
        order_manager.stop_monitoring()
        await asyncio.sleep(0.15)
        
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        
        assert mock_lighter_client.get_order.call_count >= 1
    
    def test_get_order_summary(self, order_manager):
        """Test order summary generation"""
        order1 = Order(
            order_id="order_1",
            wallet_address="0xabc123",
            market="SOL",
            order_type=OrderType.LIMIT_BUY,
            price=50.0,
            size=10.0,
            status=OrderStatus.OPEN
        )
        order2 = Order(
            order_id="order_2",
            wallet_address="0xdef456",
            market="SOL",
            order_type=OrderType.LIMIT_SELL,
            price=55.0,
            size=5.0,
            status=OrderStatus.FILLED
        )
        
        order_manager.orders = {
            "order_1": order1,
            "order_2": order2
        }
        order_manager.active_orders = {"order_1": order1}
        order_manager.filled_orders = [order2]
        
        summary = order_manager.get_order_summary()
        
        assert "ORDER SUMMARY" in summary
        assert "Total Orders: 2" in summary
        assert "Active: 1" in summary
        assert "Filled: 1" in summary
        assert "ACTIVE ORDERS:" in summary
        assert "order_1" in summary