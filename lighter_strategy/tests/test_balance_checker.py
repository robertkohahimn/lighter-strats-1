"""
Unit tests for Balance Checker module
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
import asyncio

from lighter_strategy.balance_checker import BalanceChecker, BalanceInfo


class TestBalanceInfo:
    """Test cases for BalanceInfo dataclass"""
    
    def test_balance_info_creation(self):
        """Test creating balance info object"""
        balance_info = BalanceInfo(
            address="0xabc123",
            usdc_balance=1000.0
        )
        
        assert balance_info.address == "0xabc123"
        assert balance_info.usdc_balance == 1000.0
        assert balance_info.meets_minimum is False
        assert isinstance(balance_info.timestamp, datetime)
    
    def test_balance_info_string_representation(self):
        """Test string representation of balance info"""
        balance_info = BalanceInfo(
            address="0xabc123def456",
            usdc_balance=500.25
        )
        
        str_repr = str(balance_info)
        assert "0xabc123" in str_repr
        assert "500.25" in str_repr
        assert "USDC" in str_repr


class TestBalanceChecker:
    """Test cases for BalanceChecker class"""
    
    @pytest.mark.asyncio
    async def test_get_usdc_balance_fresh(self, balance_checker, mock_lighter_client):
        """Test getting fresh balance from API"""
        mock_lighter_client.get_balance.return_value = {'balance': '1500.0'}
        
        balance = await balance_checker.get_usdc_balance(
            "0xabc123",
            mock_lighter_client
        )
        
        assert balance == 1500.0
        mock_lighter_client.get_balance.assert_called_once()
        assert "0xabc123" in balance_checker.balance_cache
    
    @pytest.mark.asyncio
    async def test_get_usdc_balance_cached(self, balance_checker, mock_lighter_client):
        """Test getting cached balance"""
        balance_info = BalanceInfo(
            address="0xabc123",
            usdc_balance=2000.0,
            timestamp=datetime.now()
        )
        balance_checker.balance_cache["0xabc123"] = balance_info
        
        balance = await balance_checker.get_usdc_balance(
            "0xabc123",
            mock_lighter_client
        )
        
        assert balance == 2000.0
        mock_lighter_client.get_balance.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_usdc_balance_expired_cache(self, balance_checker, mock_lighter_client):
        """Test cache expiration triggers fresh fetch"""
        old_timestamp = datetime.now() - timedelta(seconds=120)
        balance_info = BalanceInfo(
            address="0xabc123",
            usdc_balance=1000.0,
            timestamp=old_timestamp
        )
        balance_checker.balance_cache["0xabc123"] = balance_info
        mock_lighter_client.get_balance.return_value = {'balance': '1500.0'}
        
        balance = await balance_checker.get_usdc_balance(
            "0xabc123",
            mock_lighter_client
        )
        
        assert balance == 1500.0
        mock_lighter_client.get_balance.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_all_balances(self, balance_checker, mock_wallet_pair, mock_lighter_client):
        """Test checking balances for all wallet pairs"""
        mock_lighter_client.get_balance.side_effect = [
            {'balance': '1000.0'},
            {'balance': '2000.0'}
        ]
        
        balances = await balance_checker.check_all_balances([mock_wallet_pair])
        
        assert len(balances) == 2
        assert mock_wallet_pair.address_a in balances
        assert mock_wallet_pair.address_b in balances
        assert balances[mock_wallet_pair.address_a].usdc_balance == 1000.0
        assert balances[mock_wallet_pair.address_b].usdc_balance == 2000.0
    
    @pytest.mark.asyncio
    async def test_check_all_balances_with_error(self, balance_checker, mock_wallet_pair, mock_lighter_client):
        """Test balance checking handles individual errors"""
        mock_lighter_client.get_balance.side_effect = [
            {'balance': '1000.0'},
            Exception("API Error")
        ]
        
        balances = await balance_checker.check_all_balances([mock_wallet_pair])
        
        assert len(balances) == 2
        assert balances[mock_wallet_pair.address_a].usdc_balance == 1000.0
        assert balances[mock_wallet_pair.address_b].usdc_balance == 0.0
    
    def test_validate_minimum_balance(self, balance_checker):
        """Test minimum balance validation"""
        assert balance_checker.validate_minimum_balance(600.0, 500.0) is True
        assert balance_checker.validate_minimum_balance(400.0, 500.0) is False
        assert balance_checker.validate_minimum_balance(500.0, 500.0) is True
    
    def test_validate_all_balances_all_valid(self, balance_checker):
        """Test validating all balances when all meet threshold"""
        balances = {
            "0xabc": BalanceInfo(address="0xabc", usdc_balance=600.0),
            "0xdef": BalanceInfo(address="0xdef", usdc_balance=700.0)
        }
        
        all_valid, insufficient = balance_checker.validate_all_balances(balances, 500.0)
        
        assert all_valid is True
        assert len(insufficient) == 0
        assert balances["0xabc"].meets_minimum is True
        assert balances["0xdef"].meets_minimum is True
    
    def test_validate_all_balances_some_invalid(self, balance_checker):
        """Test validating balances with some below threshold"""
        balances = {
            "0xabc": BalanceInfo(address="0xabc", usdc_balance=400.0),
            "0xdef": BalanceInfo(address="0xdef", usdc_balance=700.0),
            "0xghi": BalanceInfo(address="0xghi", usdc_balance=300.0)
        }
        
        all_valid, insufficient = balance_checker.validate_all_balances(balances, 500.0)
        
        assert all_valid is False
        assert len(insufficient) == 2
        assert "0xabc" in insufficient
        assert "0xghi" in insufficient
        assert balances["0xabc"].meets_minimum is False
        assert balances["0xdef"].meets_minimum is True
    
    def test_format_balance_report_empty(self, balance_checker):
        """Test formatting empty balance report"""
        report = balance_checker.format_balance_report({})
        assert "No balance data available" in report
    
    def test_format_balance_report_with_data(self, balance_checker):
        """Test formatting balance report with data"""
        balances = {
            "0xabc123def456": BalanceInfo(
                address="0xabc123def456",
                usdc_balance=1000.0,
                meets_minimum=True
            ),
            "0xdef456abc123": BalanceInfo(
                address="0xdef456abc123",
                usdc_balance=400.0,
                meets_minimum=False
            )
        }
        
        report = balance_checker.format_balance_report(balances, threshold=500.0)
        
        assert "BALANCE REPORT" in report
        assert "1000.00 USDC" in report
        assert "400.00 USDC" in report
        assert "deficit: 100.00" in report
        assert "Total Balance:" in report
        assert "1400.00" in report
        assert "Meeting Minimum: 1/2" in report
    
    def test_clear_cache(self, balance_checker):
        """Test clearing the balance cache"""
        balance_checker.balance_cache = {
            "0xabc": BalanceInfo(address="0xabc", usdc_balance=1000.0)
        }
        balance_checker.last_check_time = datetime.now()
        
        balance_checker.clear_cache()
        
        assert len(balance_checker.balance_cache) == 0
        assert balance_checker.last_check_time is None
    
    @pytest.mark.asyncio
    async def test_monitor_balances(self, balance_checker, mock_wallet_pair, mock_lighter_client):
        """Test continuous balance monitoring"""
        mock_lighter_client.get_balance.return_value = {'balance': '600.0'}
        
        monitor_task = asyncio.create_task(
            balance_checker.monitor_balances(
                [mock_wallet_pair],
                threshold=500.0,
                interval_seconds=0.1
            )
        )
        
        await asyncio.sleep(0.2)
        monitor_task.cancel()
        
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        
        assert mock_lighter_client.get_balance.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_monitor_balances_alerts_insufficient(self, balance_checker, mock_wallet_pair, mock_lighter_client):
        """Test monitoring alerts on insufficient balance"""
        mock_lighter_client.get_balance.return_value = {'balance': '400.0'}
        
        with patch('lighter_strategy.balance_checker.logger') as mock_logger:
            monitor_task = asyncio.create_task(
                balance_checker.monitor_balances(
                    [mock_wallet_pair],
                    threshold=500.0,
                    interval_seconds=0.1
                )
            )
            
            await asyncio.sleep(0.2)
            monitor_task.cancel()
            
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            
            mock_logger.warning.assert_called()
            warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
            assert any("below minimum balance" in str(call) for call in warning_calls)