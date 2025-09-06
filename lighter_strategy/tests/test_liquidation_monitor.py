"""
Unit tests for Liquidation Monitor module
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, call
from datetime import datetime
import asyncio

from lighter_strategy.liquidation_monitor import (
    LiquidationMonitor, PositionInfo, PositionStatus, LiquidationEvent
)
from lighter_strategy.wallet_manager import WalletPair


class TestPositionInfo:
    """Test cases for PositionInfo dataclass"""
    
    def test_position_info_creation(self):
        """Test creating position info object"""
        position = PositionInfo(
            wallet_address="0xabc123",
            market="SOL",
            side="long",
            size=10.0,
            entry_price=50.0,
            mark_price=52.0,
            liquidation_price=45.0,
            margin=100.0,
            unrealized_pnl=20.0,
            health_ratio=0.8,
            status=PositionStatus.HEALTHY
        )
        
        assert position.wallet_address == "0xabc123"
        assert position.side == "long"
        assert position.size == 10.0
        assert position.mark_price == 52.0
        assert position.status == PositionStatus.HEALTHY
    
    def test_get_distance_to_liquidation_long(self):
        """Test calculating distance to liquidation for long position"""
        position = PositionInfo(
            wallet_address="0xabc123",
            market="SOL",
            side="long",
            size=10.0,
            entry_price=50.0,
            mark_price=52.0,
            liquidation_price=45.0,
            margin=100.0,
            unrealized_pnl=20.0,
            health_ratio=0.8,
            status=PositionStatus.HEALTHY
        )
        
        distance = position.get_distance_to_liquidation()
        expected_distance = ((52.0 - 45.0) / 52.0) * 100
        assert abs(distance - expected_distance) < 0.01
    
    def test_get_distance_to_liquidation_short(self):
        """Test calculating distance to liquidation for short position"""
        position = PositionInfo(
            wallet_address="0xabc123",
            market="SOL",
            side="short",
            size=10.0,
            entry_price=50.0,
            mark_price=48.0,
            liquidation_price=55.0,
            margin=100.0,
            unrealized_pnl=20.0,
            health_ratio=0.8,
            status=PositionStatus.HEALTHY
        )
        
        distance = position.get_distance_to_liquidation()
        expected_distance = ((55.0 - 48.0) / 48.0) * 100
        assert abs(distance - expected_distance) < 0.01


class TestLiquidationEvent:
    """Test cases for LiquidationEvent dataclass"""
    
    def test_liquidation_event_creation(self, mock_wallet_pair):
        """Test creating liquidation event"""
        event = LiquidationEvent(
            wallet_address="0xabc123",
            wallet_pair=mock_wallet_pair,
            market="SOL",
            side="long",
            size=10.0,
            liquidation_price=45.0
        )
        
        assert event.wallet_address == "0xabc123"
        assert event.wallet_pair == mock_wallet_pair
        assert event.market == "SOL"
        assert event.action_taken is None
    
    def test_liquidation_event_string(self, mock_wallet_pair):
        """Test string representation of liquidation event"""
        event = LiquidationEvent(
            wallet_address="0xabc123def456",
            wallet_pair=mock_wallet_pair,
            market="SOL",
            side="long",
            size=10.0,
            liquidation_price=45.0,
            action_taken="Emergency close triggered"
        )
        
        str_repr = str(event)
        assert "LIQUIDATION" in str_repr
        assert "0xabc123" in str_repr
        assert "long 10.0" in str_repr
        assert "45.0" in str_repr
        assert "Emergency close triggered" in str_repr


class TestLiquidationMonitor:
    """Test cases for LiquidationMonitor class"""
    
    @pytest.mark.asyncio
    async def test_monitor_liquidations_healthy(self, liquidation_monitor, mock_wallet_pair, mock_lighter_client):
        """Test monitoring healthy positions"""
        mock_lighter_client.get_position.return_value = {
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
        }
        
        monitor_task = asyncio.create_task(
            liquidation_monitor.monitor_liquidations(
                [mock_wallet_pair],
                interval_seconds=0.1
            )
        )
        
        await asyncio.sleep(0.2)
        liquidation_monitor.stop_monitoring()
        await asyncio.sleep(0.15)
        
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        
        assert len(liquidation_monitor.positions) == 2
        assert all(p.status == PositionStatus.HEALTHY 
                  for p in liquidation_monitor.positions.values())
    
    @pytest.mark.asyncio
    async def test_check_position_no_position(self, liquidation_monitor, mock_wallet_pair, mock_lighter_client):
        """Test checking when no position exists"""
        mock_lighter_client.get_position.return_value = {'size': '0'}
        
        position = await liquidation_monitor._check_position(
            mock_lighter_client,
            "0xabc123",
            mock_wallet_pair
        )
        
        assert position is None
    
    @pytest.mark.asyncio
    async def test_check_position_liquidated(self, liquidation_monitor, mock_wallet_pair, mock_lighter_client):
        """Test detecting liquidated position"""
        mock_lighter_client.get_position.return_value = {
            'market': 'SOL',
            'side': 'long',
            'size': '10.0',
            'entry_price': '50.0',
            'mark_price': '44.0',
            'liquidation_price': '45.0',
            'margin': '100.0',
            'unrealized_pnl': '-60.0',
            'health_ratio': '0.0',
            'is_liquidated': True
        }
        
        with patch.object(liquidation_monitor, '_handle_liquidation') as mock_handle:
            position = await liquidation_monitor._check_position(
                mock_lighter_client,
                "0xabc123",
                mock_wallet_pair
            )
            
            assert position.status == PositionStatus.LIQUIDATED
            mock_handle.assert_called_once()
    
    def test_determine_position_status_healthy(self, liquidation_monitor):
        """Test determining healthy position status"""
        position_data = {'health_ratio': '0.5', 'is_liquidated': False}
        status = liquidation_monitor._determine_position_status(position_data)
        assert status == PositionStatus.HEALTHY
    
    def test_determine_position_status_warning(self, liquidation_monitor):
        """Test determining warning position status"""
        position_data = {'health_ratio': '0.10', 'is_liquidated': False}
        status = liquidation_monitor._determine_position_status(position_data)
        assert status == PositionStatus.WARNING
    
    def test_determine_position_status_critical(self, liquidation_monitor):
        """Test determining critical position status"""
        position_data = {'health_ratio': '0.03', 'is_liquidated': False}
        status = liquidation_monitor._determine_position_status(position_data)
        assert status == PositionStatus.CRITICAL
    
    def test_determine_position_status_liquidated(self, liquidation_monitor):
        """Test determining liquidated position status"""
        position_data = {'health_ratio': '0.0', 'is_liquidated': True}
        status = liquidation_monitor._determine_position_status(position_data)
        assert status == PositionStatus.LIQUIDATED
    
    @pytest.mark.asyncio
    async def test_handle_liquidation(self, liquidation_monitor, mock_wallet_pair, sample_position_info):
        """Test handling liquidation event"""
        sample_position_info.status = PositionStatus.LIQUIDATED
        
        with patch.object(liquidation_monitor, 'trigger_emergency_close') as mock_emergency:
            await liquidation_monitor._handle_liquidation(
                sample_position_info,
                mock_wallet_pair
            )
            
            assert sample_position_info.wallet_address in liquidation_monitor.liquidated_wallets
            assert len(liquidation_monitor.liquidation_events) == 1
            mock_emergency.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_liquidation_duplicate(self, liquidation_monitor, mock_wallet_pair, sample_position_info):
        """Test handling duplicate liquidation doesn't trigger again"""
        liquidation_monitor.liquidated_wallets.add(sample_position_info.wallet_address)
        
        with patch.object(liquidation_monitor, 'trigger_emergency_close') as mock_emergency:
            await liquidation_monitor._handle_liquidation(
                sample_position_info,
                mock_wallet_pair
            )
            
            mock_emergency.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_check_liquidation_status(self, liquidation_monitor, mock_lighter_client):
        """Test checking liquidation status of specific wallet"""
        mock_lighter_client.get_position.return_value = {'is_liquidated': True}
        
        is_liquidated = await liquidation_monitor.check_liquidation_status(
            "0xabc123",
            mock_lighter_client
        )
        
        assert is_liquidated is True
    
    @pytest.mark.asyncio
    async def test_trigger_emergency_close(self, liquidation_monitor, mock_wallet_pair, sample_position_info, mock_lighter_client):
        """Test triggering emergency close"""
        mock_wallet_pair.client_a = mock_lighter_client
        mock_wallet_pair.client_b = mock_lighter_client
        sample_position_info.wallet_address = mock_wallet_pair.address_a
        
        with patch.object(liquidation_monitor.order_manager, 'cancel_all_orders') as mock_cancel:
            with patch.object(liquidation_monitor, 'close_opposite_trade') as mock_close:
                await liquidation_monitor.trigger_emergency_close(
                    mock_wallet_pair,
                    sample_position_info
                )
                
                mock_cancel.assert_called_once_with(
                    mock_lighter_client,
                    mock_wallet_pair.address_b
                )
                mock_close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_opposite_trade_long_liquidated(self, liquidation_monitor, mock_wallet_pair, mock_lighter_client):
        """Test closing opposite trade when long is liquidated"""
        mock_lighter_client.get_position.return_value = {
            'size': '10.0',
            'side': 'short'
        }
        
        await liquidation_monitor.close_opposite_trade(
            mock_wallet_pair,
            "long",
            mock_lighter_client,
            "0xabc123"
        )
        
        mock_lighter_client.create_order.assert_called_once_with(
            market="SOL",
            side="buy",
            order_type="market",
            size="10.0",
            wallet_address="0xabc123"
        )
    
    @pytest.mark.asyncio
    async def test_close_opposite_trade_short_liquidated(self, liquidation_monitor, mock_wallet_pair, mock_lighter_client):
        """Test closing opposite trade when short is liquidated"""
        mock_lighter_client.get_position.return_value = {
            'size': '10.0',
            'side': 'long'
        }
        
        await liquidation_monitor.close_opposite_trade(
            mock_wallet_pair,
            "short",
            mock_lighter_client,
            "0xabc123"
        )
        
        mock_lighter_client.create_order.assert_called_once_with(
            market="SOL",
            side="sell",
            order_type="market",
            size="10.0",
            wallet_address="0xabc123"
        )
    
    @pytest.mark.asyncio
    async def test_analyze_positions(self, liquidation_monitor, sample_position_info):
        """Test analyzing positions for warnings"""
        healthy_position = PositionInfo(
            wallet_address="0xhealthy",
            market="SOL",
            side="long",
            size=10.0,
            entry_price=50.0,
            mark_price=52.0,
            liquidation_price=45.0,
            margin=100.0,
            unrealized_pnl=20.0,
            health_ratio=0.8,
            status=PositionStatus.HEALTHY
        )
        
        warning_position = PositionInfo(
            wallet_address="0xwarning",
            market="SOL",
            side="long",
            size=10.0,
            entry_price=50.0,
            mark_price=47.0,
            liquidation_price=45.0,
            margin=100.0,
            unrealized_pnl=-30.0,
            health_ratio=0.10,
            status=PositionStatus.WARNING
        )
        
        critical_position = PositionInfo(
            wallet_address="0xcritical",
            market="SOL",
            side="long",
            size=10.0,
            entry_price=50.0,
            mark_price=45.5,
            liquidation_price=45.0,
            margin=100.0,
            unrealized_pnl=-45.0,
            health_ratio=0.02,
            status=PositionStatus.CRITICAL
        )
        
        liquidation_monitor.positions = {
            "0xhealthy": healthy_position,
            "0xwarning": warning_position,
            "0xcritical": critical_position
        }
        
        with patch('lighter_strategy.liquidation_monitor.logger') as mock_logger:
            await liquidation_monitor._analyze_positions()
            
            critical_calls = [call for call in mock_logger.critical.call_args_list]
            warning_calls = [call for call in mock_logger.warning.call_args_list]
            
            assert len(critical_calls) >= 2
            assert len(warning_calls) >= 2
    
    def test_add_liquidation_callback(self, liquidation_monitor):
        """Test adding liquidation callback"""
        async def test_callback(event):
            pass
        
        liquidation_monitor.add_liquidation_callback(test_callback)
        assert test_callback in liquidation_monitor.liquidation_callbacks
    
    def test_get_position_summary(self, liquidation_monitor):
        """Test position summary generation"""
        healthy = PositionInfo(
            wallet_address="0xhealthy123",
            market="SOL",
            side="long",
            size=10.0,
            entry_price=50.0,
            mark_price=52.0,
            liquidation_price=45.0,
            margin=100.0,
            unrealized_pnl=20.0,
            health_ratio=0.8,
            status=PositionStatus.HEALTHY
        )
        
        warning = PositionInfo(
            wallet_address="0xwarning456",
            market="SOL",
            side="short",
            size=5.0,
            entry_price=50.0,
            mark_price=48.0,
            liquidation_price=55.0,
            margin=50.0,
            unrealized_pnl=10.0,
            health_ratio=0.12,
            status=PositionStatus.WARNING
        )
        
        liquidation_monitor.positions = {
            "0xhealthy123": healthy,
            "0xwarning456": warning
        }
        
        summary = liquidation_monitor.get_position_summary()
        
        assert "POSITION MONITORING SUMMARY" in summary
        assert "Total Positions: 2" in summary
        assert "Healthy: 1" in summary
        assert "Warning: 1" in summary
        assert "0xhealth" in summary
        assert "0xwarnin" in summary
        assert "✅" in summary
        assert "⚠️" in summary