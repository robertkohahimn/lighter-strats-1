"""
Wallet Manager Module for Lighter Trading Strategy
Manages wallet pairs and their interactions with the Lighter API
"""

import asyncio
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
# Mock LighterClient for now - will be replaced with actual implementation
class LighterClient:
    def __init__(self, **kwargs):
        pass
    
    async def get_balance(self, **kwargs):
        return {'balance': '0'}
    
    async def close(self):
        pass
from .config import Config
from .utils.logger import logger
from .utils.exceptions import WalletConnectionError, InsufficientBalanceError


@dataclass
class WalletPair:
    """Represents a pair of trading wallets"""
    address_a: str
    address_b: str
    private_key_a: Optional[str] = None
    private_key_b: Optional[str] = None
    client_a: Optional[LighterClient] = None
    client_b: Optional[LighterClient] = None
    
    def __post_init__(self):
        """Initialize API clients for each wallet"""
        if self.private_key_a:
            self.client_a = self._create_client(self.private_key_a)
        if self.private_key_b:
            self.client_b = self._create_client(self.private_key_b)
    
    def _create_client(self, private_key: str) -> LighterClient:
        """Create a Lighter API client"""
        try:
            config = Config()
            client = LighterClient(
                api_endpoint=config.api_endpoint,
                private_key=private_key,
                chain_id=config.chain_id
            )
            return client
        except Exception as e:
            logger.error(f"Failed to create client: {e}")
            raise WalletConnectionError(f"Could not initialize client: {e}")
    
    def validate(self) -> bool:
        """Validate that both wallets are properly configured"""
        if not self.address_a or not self.address_b:
            return False
        if not self.client_a or not self.client_b:
            return False
        return True


class WalletManager:
    """Manages multiple wallet pairs for trading operations"""
    
    def __init__(self, config: Config):
        """Initialize the wallet manager"""
        self.config = config
        self.wallet_pairs: List[WalletPair] = []
        self.balances: Dict[str, float] = {}
        
    async def initialize_wallets(self, wallet_data: List[Dict]) -> List[WalletPair]:
        """
        Initialize wallet pairs from configuration data
        
        Args:
            wallet_data: List of dictionaries containing wallet information
                       Each dict should have: address_a, address_b, private_key_a, private_key_b
        
        Returns:
            List of initialized WalletPair objects
        """
        logger.info(f"Initializing {len(wallet_data)} wallet pairs")
        
        for data in wallet_data:
            try:
                wallet_pair = WalletPair(
                    address_a=data['address_a'],
                    address_b=data['address_b'],
                    private_key_a=data.get('private_key_a'),
                    private_key_b=data.get('private_key_b')
                )
                
                if wallet_pair.validate():
                    self.wallet_pairs.append(wallet_pair)
                    logger.info(f"Initialized wallet pair: {wallet_pair.address_a[:8]}.../{wallet_pair.address_b[:8]}...")
                else:
                    logger.warning(f"Invalid wallet pair configuration for {data['address_a']}/{data['address_b']}")
                    
            except Exception as e:
                logger.error(f"Failed to initialize wallet pair: {e}")
                raise WalletConnectionError(f"Wallet initialization failed: {e}")
        
        logger.info(f"Successfully initialized {len(self.wallet_pairs)} wallet pairs")
        return self.wallet_pairs
    
    async def check_balances(self) -> Dict[str, float]:
        """
        Check USDC balances for all wallets
        
        Returns:
            Dictionary mapping wallet addresses to USDC balances
        """
        logger.info("Checking balances for all wallets")
        tasks = []
        
        for wallet_pair in self.wallet_pairs:
            if wallet_pair.client_a:
                tasks.append(self._get_balance(wallet_pair.client_a, wallet_pair.address_a))
            if wallet_pair.client_b:
                tasks.append(self._get_balance(wallet_pair.client_b, wallet_pair.address_b))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Balance check failed: {result}")
            elif result:
                address, balance = result
                self.balances[address] = balance
                logger.debug(f"Wallet {address[:8]}... balance: {balance} USDC")
        
        return self.balances
    
    async def _get_balance(self, client: LighterClient, address: str) -> Tuple[str, float]:
        """
        Get USDC balance for a specific wallet
        
        Args:
            client: Lighter API client
            address: Wallet address
            
        Returns:
            Tuple of (address, balance)
        """
        try:
            balance_info = await client.get_balance(
                address=address,
                token="USDC"
            )
            balance = float(balance_info.get('balance', 0))
            return (address, balance)
        except Exception as e:
            logger.error(f"Failed to get balance for {address}: {e}")
            return (address, 0.0)
    
    async def validate_minimum_usdc(self, threshold: Optional[float] = None) -> Dict[str, bool]:
        """
        Validate that all wallets meet minimum USDC requirements
        
        Args:
            threshold: Minimum USDC balance required (uses config default if not specified)
            
        Returns:
            Dictionary mapping wallet addresses to validation status
        """
        if threshold is None:
            threshold = self.config.minimum_usdc
            
        logger.info(f"Validating minimum USDC balance of {threshold}")
        
        if not self.balances:
            await self.check_balances()
        
        validation_results = {}
        insufficient_wallets = []
        
        for address, balance in self.balances.items():
            meets_minimum = balance >= threshold
            validation_results[address] = meets_minimum
            
            if not meets_minimum:
                insufficient_wallets.append(f"{address[:8]}... (balance: {balance})")
                logger.warning(f"Wallet {address[:8]}... has insufficient balance: {balance} < {threshold}")
            else:
                logger.info(f"Wallet {address[:8]}... meets minimum requirement: {balance} >= {threshold}")
        
        if insufficient_wallets:
            error_msg = f"Insufficient balance in wallets: {', '.join(insufficient_wallets)}"
            raise InsufficientBalanceError(error_msg)
        
        return validation_results
    
    def get_wallet_pairs(self) -> List[WalletPair]:
        """
        Get all configured wallet pairs
        
        Returns:
            List of WalletPair objects
        """
        return self.wallet_pairs
    
    async def get_wallet_pair_by_address(self, address: str) -> Optional[WalletPair]:
        """
        Find a wallet pair containing the specified address
        
        Args:
            address: Wallet address to search for
            
        Returns:
            WalletPair object if found, None otherwise
        """
        for wallet_pair in self.wallet_pairs:
            if wallet_pair.address_a == address or wallet_pair.address_b == address:
                return wallet_pair
        return None
    
    async def close_connections(self):
        """Close all wallet connections gracefully"""
        logger.info("Closing wallet connections")
        for wallet_pair in self.wallet_pairs:
            try:
                if wallet_pair.client_a:
                    await wallet_pair.client_a.close()
                if wallet_pair.client_b:
                    await wallet_pair.client_b.close()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
        
        self.wallet_pairs.clear()
        self.balances.clear()
        logger.info("All wallet connections closed")