"""
Balance Checker Module for Lighter Trading Strategy
Handles balance verification and reporting for trading wallets
"""

import asyncio
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from lighter_client import LighterClient
from .utils.logger import logger
from .utils.exceptions import InsufficientBalanceError


@dataclass
class BalanceInfo:
    """Contains balance information for a wallet"""
    address: str
    usdc_balance: float
    timestamp: datetime = field(default_factory=datetime.now)
    meets_minimum: bool = False
    
    def __str__(self):
        return f"{self.address[:8]}... USDC: {self.usdc_balance:.2f} @ {self.timestamp.strftime('%H:%M:%S')}"


class BalanceChecker:
    """Manages balance checking and validation for trading wallets"""
    
    def __init__(self, cache_duration_seconds: int = 60):
        """
        Initialize the balance checker
        
        Args:
            cache_duration_seconds: How long to cache balance data before refreshing
        """
        self.cache_duration = cache_duration_seconds
        self.balance_cache: Dict[str, BalanceInfo] = {}
        self.last_check_time: Optional[datetime] = None
        
    async def get_usdc_balance(self, wallet_address: str, client: LighterClient) -> float:
        """
        Get USDC balance for a specific wallet
        
        Args:
            wallet_address: The wallet address to check
            client: Lighter API client for the wallet
            
        Returns:
            USDC balance as float
        """
        try:
            cached_balance = self._get_cached_balance(wallet_address)
            if cached_balance is not None:
                logger.debug(f"Using cached balance for {wallet_address[:8]}...")
                return cached_balance
            
            logger.debug(f"Fetching fresh balance for {wallet_address[:8]}...")
            balance_data = await client.get_balance(
                address=wallet_address,
                token="USDC"
            )
            
            balance = float(balance_data.get('balance', 0))
            
            balance_info = BalanceInfo(
                address=wallet_address,
                usdc_balance=balance
            )
            self.balance_cache[wallet_address] = balance_info
            
            logger.info(f"Balance for {wallet_address[:8]}...: {balance:.2f} USDC")
            return balance
            
        except Exception as e:
            logger.error(f"Failed to get balance for {wallet_address}: {e}")
            raise
    
    async def check_all_balances(self, wallet_pairs: List) -> Dict[str, BalanceInfo]:
        """
        Check balances for all wallets in the provided wallet pairs
        
        Args:
            wallet_pairs: List of WalletPair objects
            
        Returns:
            Dictionary mapping wallet addresses to BalanceInfo objects
        """
        logger.info(f"Checking balances for {len(wallet_pairs)} wallet pairs")
        tasks = []
        
        for wallet_pair in wallet_pairs:
            if wallet_pair.client_a:
                tasks.append(self._check_wallet_balance(
                    wallet_pair.address_a, 
                    wallet_pair.client_a
                ))
            if wallet_pair.client_b:
                tasks.append(self._check_wallet_balance(
                    wallet_pair.address_b,
                    wallet_pair.client_b
                ))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_balances = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Balance check failed: {result}")
            elif result:
                all_balances[result.address] = result
        
        self.last_check_time = datetime.now()
        return all_balances
    
    async def _check_wallet_balance(self, address: str, client: LighterClient) -> BalanceInfo:
        """
        Check balance for a single wallet
        
        Args:
            address: Wallet address
            client: Lighter API client
            
        Returns:
            BalanceInfo object
        """
        try:
            balance = await self.get_usdc_balance(address, client)
            return BalanceInfo(
                address=address,
                usdc_balance=balance,
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.error(f"Failed to check balance for {address}: {e}")
            return BalanceInfo(
                address=address,
                usdc_balance=0.0,
                timestamp=datetime.now()
            )
    
    def validate_minimum_balance(self, balance: float, threshold: float) -> bool:
        """
        Validate if a balance meets the minimum threshold
        
        Args:
            balance: The balance to check
            threshold: The minimum required balance
            
        Returns:
            True if balance meets threshold, False otherwise
        """
        meets_minimum = balance >= threshold
        if not meets_minimum:
            logger.warning(f"Balance {balance:.2f} is below minimum threshold {threshold:.2f}")
        return meets_minimum
    
    def validate_all_balances(self, balances: Dict[str, BalanceInfo], threshold: float) -> Tuple[bool, List[str]]:
        """
        Validate all balances against minimum threshold
        
        Args:
            balances: Dictionary of wallet addresses to BalanceInfo
            threshold: Minimum required balance
            
        Returns:
            Tuple of (all_valid, list_of_insufficient_wallets)
        """
        insufficient_wallets = []
        
        for address, balance_info in balances.items():
            balance_info.meets_minimum = self.validate_minimum_balance(
                balance_info.usdc_balance,
                threshold
            )
            
            if not balance_info.meets_minimum:
                insufficient_wallets.append(address)
        
        all_valid = len(insufficient_wallets) == 0
        
        if not all_valid:
            logger.warning(f"{len(insufficient_wallets)} wallets have insufficient balance")
        else:
            logger.info("All wallets meet minimum balance requirement")
        
        return all_valid, insufficient_wallets
    
    def format_balance_report(self, balances: Dict[str, BalanceInfo], threshold: Optional[float] = None) -> str:
        """
        Format a readable balance report for logging
        
        Args:
            balances: Dictionary of wallet addresses to BalanceInfo
            threshold: Optional minimum threshold to highlight
            
        Returns:
            Formatted string report
        """
        if not balances:
            return "No balance data available"
        
        report_lines = [
            "\n" + "="*60,
            "BALANCE REPORT",
            f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "="*60
        ]
        
        if threshold:
            report_lines.append(f"Minimum Required: {threshold:.2f} USDC")
            report_lines.append("-"*60)
        
        total_balance = 0.0
        
        for address, balance_info in sorted(balances.items()):
            status = "✓" if balance_info.meets_minimum else "✗"
            line = f"{status} {address[:8]}...{address[-6:]}: {balance_info.usdc_balance:>12.2f} USDC"
            
            if not balance_info.meets_minimum and threshold:
                deficit = threshold - balance_info.usdc_balance
                line += f" (deficit: {deficit:.2f})"
            
            report_lines.append(line)
            total_balance += balance_info.usdc_balance
        
        report_lines.append("-"*60)
        report_lines.append(f"Total Balance: {total_balance:>12.2f} USDC")
        report_lines.append(f"Wallets: {len(balances)}")
        
        if threshold:
            valid_count = sum(1 for b in balances.values() if b.meets_minimum)
            report_lines.append(f"Meeting Minimum: {valid_count}/{len(balances)}")
        
        report_lines.append("="*60)
        
        return "\n".join(report_lines)
    
    def _get_cached_balance(self, wallet_address: str) -> Optional[float]:
        """
        Get cached balance if still valid
        
        Args:
            wallet_address: The wallet address to check
            
        Returns:
            Cached balance or None if cache is expired
        """
        if wallet_address not in self.balance_cache:
            return None
        
        cached_info = self.balance_cache[wallet_address]
        age_seconds = (datetime.now() - cached_info.timestamp).total_seconds()
        
        if age_seconds > self.cache_duration:
            logger.debug(f"Cache expired for {wallet_address[:8]}... (age: {age_seconds:.1f}s)")
            return None
        
        return cached_info.usdc_balance
    
    def clear_cache(self):
        """Clear the balance cache"""
        self.balance_cache.clear()
        self.last_check_time = None
        logger.debug("Balance cache cleared")
    
    async def monitor_balances(self, wallet_pairs: List, threshold: float, interval_seconds: int = 60):
        """
        Continuously monitor balances and alert on changes
        
        Args:
            wallet_pairs: List of WalletPair objects to monitor
            threshold: Minimum balance threshold
            interval_seconds: How often to check balances
        """
        logger.info(f"Starting balance monitoring (interval: {interval_seconds}s)")
        
        while True:
            try:
                balances = await self.check_all_balances(wallet_pairs)
                all_valid, insufficient = self.validate_all_balances(balances, threshold)
                
                report = self.format_balance_report(balances, threshold)
                logger.info(report)
                
                if not all_valid:
                    logger.warning(f"ALERT: {len(insufficient)} wallets below minimum balance!")
                    for wallet in insufficient:
                        balance_info = balances[wallet]
                        deficit = threshold - balance_info.usdc_balance
                        logger.warning(
                            f"Wallet {wallet[:8]}... needs {deficit:.2f} more USDC "
                            f"(current: {balance_info.usdc_balance:.2f}, required: {threshold:.2f})"
                        )
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in balance monitoring: {e}")
                await asyncio.sleep(interval_seconds)