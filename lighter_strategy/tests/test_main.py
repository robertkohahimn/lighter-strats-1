"""
Unit tests for Main Strategy module
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
import asyncio
import json
from pathlib import Path
import argparse

from lighter_strategy.main import LighterStrategy, main
from lighter_strategy.utils.exceptions import (
    InsufficientBalanceError,
    OrderCreationError,
    EmergencyShutdownError
)


class TestLighterStrategy:
    """Test cases for LighterStrategy class"""
    
    @pytest.fixture
    def strategy(self, mock_config):
        """Create strategy instance for testing"""
        return LighterStrategy(mock_config)
    
    @pytest.mark.asyncio
    async def test_strategy_initialization(self, mock_config):
        """Test strategy initialization"""
        strategy = LighterStrategy(mock_config)
        
        assert strategy.config == mock_config
        assert strategy.wallet_manager is not None
        assert strategy.balance_checker is not None
        assert strategy.order_manager is not None
        assert strategy.liquidation_monitor is not None
        assert strategy.running is False
        assert strategy.orders_placed == 0
        assert strategy.orders_filled == 0
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, strategy, sample_wallet_data):
        """Test successful strategy initialization with wallets"""
        with patch.object(strategy.wallet_manager, 'initialize_wallets') as mock_init:
            with patch.object(strategy, 'validate_balances') as mock_validate:
                mock_wallet_pair = Mock()
                mock_init.return_value = [mock_wallet_pair]
                mock_validate.return_value = {"0xabc": 1000.0}
                
                result = await strategy.initialize(sample_wallet_data)
                
                assert result is True
                assert strategy.wallet_pairs == [mock_wallet_pair]
                mock_init.assert_called_once_with(sample_wallet_data)
                mock_validate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_initialize_no_wallets(self, strategy, sample_wallet_data):
        """Test initialization fails with no wallets"""
        with patch.object(strategy.wallet_manager, 'initialize_wallets') as mock_init:
            mock_init.return_value = []
            
            result = await strategy.initialize(sample_wallet_data)
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_validate_balances_success(self, strategy, mock_wallet_pair):
        """Test successful balance validation"""
        strategy.wallet_pairs = [mock_wallet_pair]
        
        with patch.object(strategy.balance_checker, 'check_all_balances') as mock_check:
            with patch.object(strategy.balance_checker, 'validate_all_balances') as mock_validate:
                mock_balance_info = Mock(usdc_balance=1000.0)
                mock_check.return_value = {
                    "0xabc": mock_balance_info,
                    "0xdef": mock_balance_info
                }
                mock_validate.return_value = (True, [])
                
                balances = await strategy.validate_balances()
                
                assert balances == {"0xabc": 1000.0, "0xdef": 1000.0}
    
    @pytest.mark.asyncio
    async def test_validate_balances_insufficient(self, strategy, mock_wallet_pair):
        """Test balance validation with insufficient funds"""
        strategy.wallet_pairs = [mock_wallet_pair]
        
        with patch.object(strategy.balance_checker, 'check_all_balances') as mock_check:
            with patch.object(strategy.balance_checker, 'validate_all_balances') as mock_validate:
                with patch.object(strategy.balance_checker, 'format_balance_report') as mock_report:
                    mock_balance_info = Mock(usdc_balance=100.0)
                    mock_check.return_value = {"0xabc": mock_balance_info}
                    mock_validate.return_value = (False, ["0xabc"])
                    mock_report.return_value = "Balance report"
                    
                    with pytest.raises(InsufficientBalanceError):
                        await strategy.validate_balances()
    
    @pytest.mark.asyncio
    async def test_setup_orders_success(self, strategy, mock_wallet_pair):
        """Test successful order setup"""
        strategy.wallet_pairs = [mock_wallet_pair]
        mock_wallet_pair.client_a = AsyncMock()
        mock_wallet_pair.client_b = AsyncMock()
        
        with patch.object(strategy.order_manager, 'create_limit_buy_order') as mock_buy:
            with patch.object(strategy.order_manager, 'create_limit_sell_order') as mock_sell:
                mock_order = Mock(order_id="test_order")
                mock_buy.return_value = mock_order
                mock_sell.return_value = mock_order
                
                count = await strategy.setup_orders(50.0, 55.0, 10.0)
                
                assert count == 2
                assert strategy.orders_placed == 2
                mock_buy.assert_called_once()
                mock_sell.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_setup_orders_with_error(self, strategy, mock_wallet_pair):
        """Test order setup with some failures"""
        strategy.wallet_pairs = [mock_wallet_pair]
        mock_wallet_pair.client_a = AsyncMock()
        mock_wallet_pair.client_b = AsyncMock()
        
        with patch.object(strategy.order_manager, 'create_limit_buy_order') as mock_buy:
            with patch.object(strategy.order_manager, 'create_limit_sell_order') as mock_sell:
                mock_order = Mock(order_id="test_order")
                mock_buy.return_value = mock_order
                mock_sell.side_effect = OrderCreationError("Failed")
                
                count = await strategy.setup_orders(50.0, 55.0, 10.0)
                
                assert count == 1
                assert strategy.orders_placed == 1
    
    @pytest.mark.asyncio
    async def test_monitor_loop(self, strategy):
        """Test monitoring loop execution"""
        strategy.running = True
        strategy.start_time = Mock()
        
        with patch.object(strategy.order_manager, 'get_filled_orders') as mock_filled:
            with patch.object(strategy, '_log_status') as mock_log:
                mock_filled.return_value = []
                
                # Run loop for a short time
                monitor_task = asyncio.create_task(strategy.monitor_loop())
                await asyncio.sleep(0.1)
                strategy.shutdown_event.set()
                await asyncio.sleep(0.1)
                monitor_task.cancel()
                
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
                
                mock_log.assert_called()
    
    @pytest.mark.asyncio
    async def test_on_liquidation_with_shutdown(self, strategy):
        """Test liquidation handler with emergency shutdown"""
        strategy.settings.emergency_shutdown_enabled = True
        event = Mock()
        
        with patch.object(strategy, 'emergency_shutdown') as mock_shutdown:
            await strategy._on_liquidation(event)
            
            assert strategy.liquidations_handled == 1
            mock_shutdown.assert_called_once_with("Liquidation detected")
    
    @pytest.mark.asyncio
    async def test_on_liquidation_without_shutdown(self, strategy):
        """Test liquidation handler without emergency shutdown"""
        strategy.settings.emergency_shutdown_enabled = False
        event = Mock()
        
        with patch.object(strategy, 'emergency_shutdown') as mock_shutdown:
            await strategy._on_liquidation(event)
            
            assert strategy.liquidations_handled == 1
            mock_shutdown.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_emergency_shutdown(self, strategy, mock_wallet_pair):
        """Test emergency shutdown procedure"""
        strategy.wallet_pairs = [mock_wallet_pair]
        strategy.running = True
        mock_wallet_pair.client_a = AsyncMock()
        mock_wallet_pair.client_b = AsyncMock()
        
        with patch.object(strategy.order_manager, 'cancel_all_orders') as mock_cancel:
            with patch.object(strategy, '_log_status') as mock_log:
                await strategy.emergency_shutdown("Test reason")
                
                assert strategy.shutdown_event.is_set()
                assert strategy.running is False
                assert mock_cancel.call_count == 2
                mock_log.assert_called()
    
    @pytest.mark.asyncio
    async def test_withdraw_all_funds(self, strategy, mock_wallet_pair):
        """Test withdrawal of all funds"""
        strategy.wallet_pairs = [mock_wallet_pair]
        mock_wallet_pair.client_a = AsyncMock()
        mock_wallet_pair.client_b = AsyncMock()
        
        with patch.object(strategy, '_get_wallet_balance') as mock_balance:
            with patch.object(strategy, '_withdraw_usdc') as mock_withdraw:
                mock_balance.side_effect = [1000.0, 500.0]
                
                withdrawals = await strategy.withdraw_all_funds()
                
                assert len(withdrawals) == 2
                assert withdrawals[mock_wallet_pair.address_a] == 1000.0
                assert withdrawals[mock_wallet_pair.address_b] == 500.0
                assert mock_withdraw.call_count == 2
    
    @pytest.mark.asyncio
    async def test_withdraw_all_funds_with_error(self, strategy, mock_wallet_pair):
        """Test withdrawal with some failures"""
        strategy.wallet_pairs = [mock_wallet_pair]
        mock_wallet_pair.client_a = AsyncMock()
        mock_wallet_pair.client_b = AsyncMock()
        
        with patch.object(strategy, '_get_wallet_balance') as mock_balance:
            with patch.object(strategy, '_withdraw_usdc') as mock_withdraw:
                mock_balance.side_effect = [1000.0, Exception("Balance error")]
                
                withdrawals = await strategy.withdraw_all_funds()
                
                assert len(withdrawals) == 1
                assert withdrawals[mock_wallet_pair.address_a] == 1000.0
    
    @pytest.mark.asyncio
    async def test_run_strategy(self, strategy, mock_wallet_pair):
        """Test main strategy execution"""
        strategy.wallet_pairs = [mock_wallet_pair]
        
        with patch.object(strategy, 'setup_orders') as mock_setup:
            with patch.object(strategy.order_manager, 'monitor_order_fills') as mock_order_monitor:
                with patch.object(strategy.liquidation_monitor, 'monitor_liquidations') as mock_liq_monitor:
                    with patch.object(strategy.balance_checker, 'monitor_balances') as mock_bal_monitor:
                        with patch.object(strategy, 'monitor_loop') as mock_loop:
                            with patch.object(strategy, 'cleanup') as mock_cleanup:
                                mock_setup.return_value = 2
                                
                                # Set shutdown immediately
                                strategy.shutdown_event.set()
                                
                                await strategy.run_strategy(50.0, 55.0, 10.0)
                                
                                mock_setup.assert_called_once_with(50.0, 55.0, 10.0)
                                mock_cleanup.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_strategy_no_orders(self, strategy):
        """Test strategy execution with no orders placed"""
        with patch.object(strategy, 'setup_orders') as mock_setup:
            with patch.object(strategy, 'cleanup') as mock_cleanup:
                mock_setup.return_value = 0
                
                await strategy.run_strategy(50.0, 55.0, 10.0)
                
                mock_cleanup.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cleanup(self, strategy, mock_wallet_pair):
        """Test cleanup procedure"""
        strategy.wallet_pairs = [mock_wallet_pair]
        strategy.running = True
        
        # Create mock tasks
        mock_task = Mock()
        mock_task.done = Mock(return_value=False)
        mock_task.cancel = Mock()
        strategy.tasks = [mock_task]
        
        with patch.object(strategy.order_manager, 'stop_monitoring') as mock_stop_order:
            with patch.object(strategy.liquidation_monitor, 'stop_monitoring') as mock_stop_liq:
                with patch.object(strategy.wallet_manager, 'close_connections') as mock_close:
                    await strategy.cleanup()
                    
                    assert strategy.running is False
                    mock_task.cancel.assert_called_once()
                    mock_stop_order.assert_called_once()
                    mock_stop_liq.assert_called_once()
                    mock_close.assert_called_once()
    
    def test_signal_handler(self, strategy):
        """Test signal handler"""
        strategy.signal_handler(15, None)
        assert strategy.shutdown_event.is_set()


class TestMainCLI:
    """Test cases for CLI functionality"""
    
    @pytest.mark.asyncio
    async def test_main_with_wallet_file(self, tmp_path):
        """Test main function with wallet configuration file"""
        # Create temporary wallet file
        wallet_file = tmp_path / "wallets.json"
        wallet_data = [
            {
                "address_a": "0xabc",
                "address_b": "0xdef",
                "private_key_a": "key1",
                "private_key_b": "key2"
            }
        ]
        wallet_file.write_text(json.dumps(wallet_data))
        
        # Mock command line arguments
        test_args = [
            "main.py",
            "--wallet-pairs", str(wallet_file),
            "--buy-price", "50.0",
            "--sell-price", "55.0",
            "--order-size", "10.0"
        ]
        
        with patch('sys.argv', test_args):
            with patch('lighter_strategy.main.LighterStrategy') as mock_strategy_class:
                mock_strategy = AsyncMock()
                mock_strategy_class.return_value = mock_strategy
                mock_strategy.initialize.return_value = True
                mock_strategy.shutdown_event.wait = AsyncMock()
                
                await main()
                
                mock_strategy.initialize.assert_called_once()
                mock_strategy.run_strategy.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_main_withdraw_mode(self, tmp_path):
        """Test main function in withdrawal mode"""
        # Create temporary wallet file
        wallet_file = tmp_path / "wallets.json"
        wallet_data = [{"address_a": "0xabc", "address_b": "0xdef"}]
        wallet_file.write_text(json.dumps(wallet_data))
        
        test_args = [
            "main.py",
            "--wallet-pairs", str(wallet_file),
            "--buy-price", "50.0",
            "--sell-price", "55.0",
            "--order-size", "10.0",
            "--withdraw"
        ]
        
        with patch('sys.argv', test_args):
            with patch('lighter_strategy.main.LighterStrategy') as mock_strategy_class:
                mock_strategy = AsyncMock()
                mock_strategy_class.return_value = mock_strategy
                mock_strategy.initialize.return_value = True
                mock_strategy.withdraw_all_funds.return_value = {"0xabc": 1000.0}
                
                await main()
                
                mock_strategy.withdraw_all_funds.assert_called_once()
                mock_strategy.run_strategy.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_main_initialization_failure(self, tmp_path):
        """Test main function when initialization fails"""
        wallet_file = tmp_path / "wallets.json"
        wallet_file.write_text(json.dumps([]))
        
        test_args = [
            "main.py",
            "--wallet-pairs", str(wallet_file),
            "--buy-price", "50.0",
            "--sell-price", "55.0",
            "--order-size", "10.0"
        ]
        
        with patch('sys.argv', test_args):
            with patch('lighter_strategy.main.LighterStrategy') as mock_strategy_class:
                mock_strategy = AsyncMock()
                mock_strategy_class.return_value = mock_strategy
                mock_strategy.initialize.return_value = False
                
                with patch('sys.exit') as mock_exit:
                    await main()
                    mock_exit.assert_called_with(1)