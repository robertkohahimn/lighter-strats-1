"""
Unit tests for Wallet Manager module
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import asyncio

from lighter_strategy.wallet_manager import WalletPair, WalletManager
from lighter_strategy.utils.exceptions import WalletConnectionError, InsufficientBalanceError


class TestWalletPair:
    """Test cases for WalletPair class"""
    
    def test_wallet_pair_initialization(self):
        """Test basic wallet pair creation"""
        wallet_pair = WalletPair(
            address_a="0xabc123",
            address_b="0xdef456"
        )
        
        assert wallet_pair.address_a == "0xabc123"
        assert wallet_pair.address_b == "0xdef456"
        assert wallet_pair.private_key_a is None
        assert wallet_pair.private_key_b is None
        assert wallet_pair.client_a is None
        assert wallet_pair.client_b is None
    
    @patch('lighter_strategy.wallet_manager.LighterClient')
    def test_wallet_pair_with_private_keys(self, mock_lighter_client_class):
        """Test wallet pair with private keys creates clients"""
        mock_client = Mock()
        mock_lighter_client_class.return_value = mock_client
        
        wallet_pair = WalletPair(
            address_a="0xabc123",
            address_b="0xdef456",
            private_key_a="key_a",
            private_key_b="key_b"
        )
        
        assert wallet_pair.client_a is not None
        assert wallet_pair.client_b is not None
    
    def test_wallet_pair_validation_valid(self, mock_wallet_pair):
        """Test validation of valid wallet pair"""
        assert mock_wallet_pair.validate() is True
    
    def test_wallet_pair_validation_no_addresses(self):
        """Test validation fails without addresses"""
        wallet_pair = WalletPair(address_a="", address_b="")
        assert wallet_pair.validate() is False
    
    def test_wallet_pair_validation_no_clients(self):
        """Test validation fails without clients"""
        wallet_pair = WalletPair(
            address_a="0xabc123",
            address_b="0xdef456"
        )
        assert wallet_pair.validate() is False


class TestWalletManager:
    """Test cases for WalletManager class"""
    
    @pytest.mark.asyncio
    async def test_initialize_wallets_success(self, wallet_manager, sample_wallet_data):
        """Test successful wallet initialization"""
        with patch('lighter_strategy.wallet_manager.LighterClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            wallet_pairs = await wallet_manager.initialize_wallets(sample_wallet_data)
            
            assert len(wallet_pairs) == 2
            assert len(wallet_manager.wallet_pairs) == 2
            assert wallet_pairs[0].address_a == sample_wallet_data[0]['address_a']
    
    @pytest.mark.asyncio
    async def test_initialize_wallets_connection_error(self, wallet_manager, sample_wallet_data):
        """Test wallet initialization with connection error"""
        with patch('lighter_strategy.wallet_manager.LighterClient') as mock_client_class:
            mock_client_class.side_effect = Exception("Connection failed")
            
            with pytest.raises(WalletConnectionError):
                await wallet_manager.initialize_wallets(sample_wallet_data)
    
    @pytest.mark.asyncio
    async def test_check_balances(self, wallet_manager, mock_wallet_pair, mock_lighter_client):
        """Test balance checking for all wallets"""
        wallet_manager.wallet_pairs = [mock_wallet_pair]
        mock_lighter_client.get_balance.return_value = {'balance': '750.0'}
        
        balances = await wallet_manager.check_balances()
        
        assert len(balances) == 2
        assert mock_wallet_pair.address_a in balances
        assert mock_wallet_pair.address_b in balances
        assert balances[mock_wallet_pair.address_a] == 750.0
    
    @pytest.mark.asyncio
    async def test_check_balances_with_error(self, wallet_manager, mock_wallet_pair, mock_lighter_client):
        """Test balance checking handles errors gracefully"""
        wallet_manager.wallet_pairs = [mock_wallet_pair]
        mock_lighter_client.get_balance.side_effect = [
            {'balance': '1000.0'},
            Exception("API Error")
        ]
        
        balances = await wallet_manager.check_balances()
        
        assert len(balances) == 2
        assert mock_wallet_pair.address_a in balances
        assert mock_wallet_pair.address_b in balances
        assert balances[mock_wallet_pair.address_a] == 1000.0
        assert balances[mock_wallet_pair.address_b] == 0.0
    
    @pytest.mark.asyncio
    async def test_validate_minimum_usdc_all_sufficient(self, wallet_manager, mock_config):
        """Test validation when all wallets meet minimum"""
        wallet_manager.balances = {
            "0xabc123": 600.0,
            "0xdef456": 800.0
        }
        
        validation_results = await wallet_manager.validate_minimum_usdc(500.0)
        
        assert all(validation_results.values())
        assert len(validation_results) == 2
    
    @pytest.mark.asyncio
    async def test_validate_minimum_usdc_insufficient(self, wallet_manager):
        """Test validation raises error when wallets below minimum"""
        wallet_manager.balances = {
            "0xabc123": 400.0,
            "0xdef456": 800.0
        }
        
        with pytest.raises(InsufficientBalanceError) as exc_info:
            await wallet_manager.validate_minimum_usdc(500.0)
        
        assert "Insufficient balance" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_wallet_pair_by_address(self, wallet_manager, mock_wallet_pair):
        """Test finding wallet pair by address"""
        wallet_manager.wallet_pairs = [mock_wallet_pair]
        
        found_pair = await wallet_manager.get_wallet_pair_by_address(mock_wallet_pair.address_a)
        assert found_pair == mock_wallet_pair
        
        found_pair = await wallet_manager.get_wallet_pair_by_address(mock_wallet_pair.address_b)
        assert found_pair == mock_wallet_pair
        
        not_found = await wallet_manager.get_wallet_pair_by_address("0xnotfound")
        assert not_found is None
    
    @pytest.mark.asyncio
    async def test_close_connections(self, wallet_manager, mock_wallet_pair, mock_lighter_client):
        """Test closing all wallet connections"""
        wallet_manager.wallet_pairs = [mock_wallet_pair]
        wallet_manager.balances = {"0xabc": 100.0}
        
        await wallet_manager.close_connections()
        
        mock_lighter_client.close.assert_called()
        assert len(wallet_manager.wallet_pairs) == 0
        assert len(wallet_manager.balances) == 0
    
    @pytest.mark.asyncio
    async def test_close_connections_handles_errors(self, wallet_manager, mock_wallet_pair, mock_lighter_client):
        """Test connection closing handles errors gracefully"""
        wallet_manager.wallet_pairs = [mock_wallet_pair]
        mock_lighter_client.close.side_effect = Exception("Close failed")
        
        await wallet_manager.close_connections()
        
        assert len(wallet_manager.wallet_pairs) == 0