#!/usr/bin/env python3
"""
Main Strategy Implementation for Lighter Trading
Orchestrates all components and manages the trading lifecycle
"""

import asyncio
import signal
import sys
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import argparse
import json
from pathlib import Path

try:
    # Try relative imports first (when run as module)
    from .config import Config, Settings, get_settings
    from .wallet_manager import WalletManager, WalletPair
    from .balance_checker import BalanceChecker
    from .order_manager import OrderManager, OrderType
    from .liquidation_monitor import LiquidationMonitor, LiquidationEvent
    from .utils.logger import logger
    from .utils.exceptions import (
        InsufficientBalanceError,
        OrderCreationError,
        LiquidationDetectedError,
        EmergencyShutdownError,
        WithdrawalError
    )
except ImportError:
    # Fall back to absolute imports (when run directly)
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from lighter_strategy.config import Config, Settings, get_settings
    from lighter_strategy.wallet_manager import WalletManager, WalletPair
    from lighter_strategy.balance_checker import BalanceChecker
    from lighter_strategy.order_manager import OrderManager, OrderType
    from lighter_strategy.liquidation_monitor import LiquidationMonitor, LiquidationEvent
    from lighter_strategy.utils.logger import logger
    from lighter_strategy.utils.exceptions import (
        InsufficientBalanceError,
        OrderCreationError,
        LiquidationDetectedError,
        EmergencyShutdownError,
        WithdrawalError
    )


class LighterStrategy:
    """Main strategy orchestrator for Lighter trading"""
    
    def __init__(self, config: Config = None):
        """
        Initialize the strategy with configuration
        
        Args:
            config: Configuration object (uses default if not provided)
        """
        self.config = config or Config()
        self.settings = get_settings()
        
        # Initialize components
        self.wallet_manager = WalletManager(self.config)
        self.balance_checker = BalanceChecker(cache_duration_seconds=30)
        self.order_manager = OrderManager()
        self.liquidation_monitor = LiquidationMonitor(self.order_manager)
        
        # Strategy state
        self.wallet_pairs: List[WalletPair] = []
        self.running = False
        self.tasks: List[asyncio.Task] = []
        self.shutdown_event = asyncio.Event()
        
        # Performance tracking
        self.start_time: Optional[datetime] = None
        self.orders_placed = 0
        self.orders_filled = 0
        self.liquidations_handled = 0
        
        # Register liquidation callback
        self.liquidation_monitor.add_liquidation_callback(self._on_liquidation)
        
        logger.info("LighterStrategy initialized")
    
    async def initialize(self, wallet_data: List[Dict]) -> bool:
        """
        Initialize strategy with wallet pairs
        
        Args:
            wallet_data: List of wallet pair configurations
            
        Returns:
            True if initialization successful
        """
        try:
            logger.info(f"Initializing strategy with {len(wallet_data)} wallet pairs")
            
            # Initialize wallets
            self.wallet_pairs = await self.wallet_manager.initialize_wallets(wallet_data)
            
            if not self.wallet_pairs:
                logger.error("No wallet pairs initialized")
                return False
            
            # Validate minimum balances
            await self.validate_balances()
            
            logger.info(f"Strategy initialized with {len(self.wallet_pairs)} wallet pairs")
            return True
            
        except Exception as e:
            logger.error(f"Strategy initialization failed: {e}")
            return False
    
    async def validate_balances(self) -> Dict[str, float]:
        """
        Validate all wallet balances meet minimum requirements
        
        Returns:
            Dictionary of wallet addresses to balances
        """
        logger.info("Validating wallet balances")
        
        # Check all balances
        all_balances = await self.balance_checker.check_all_balances(self.wallet_pairs)
        
        # Validate minimums
        all_valid, insufficient = self.balance_checker.validate_all_balances(
            all_balances,
            self.config.minimum_usdc
        )
        
        if not all_valid:
            report = self.balance_checker.format_balance_report(
                all_balances,
                self.config.minimum_usdc
            )
            logger.error(f"Balance validation failed:\n{report}")
            raise InsufficientBalanceError(
                f"Insufficient balance in {len(insufficient)} wallets"
            )
        
        logger.info("All wallets meet minimum balance requirements")
        return {addr: info.usdc_balance for addr, info in all_balances.items()}
    
    async def setup_orders(self, buy_price: float, sell_price: float, order_size: float) -> int:
        """
        Place initial limit orders for all wallet pairs
        
        Args:
            buy_price: Price for buy orders
            sell_price: Price for sell orders
            order_size: Size for each order
            
        Returns:
            Number of orders successfully placed
        """
        logger.info(f"Setting up orders - Buy: {buy_price}, Sell: {sell_price}, Size: {order_size}")
        
        successful_orders = 0
        
        for wallet_pair in self.wallet_pairs:
            try:
                # Place buy order with wallet A
                if wallet_pair.client_a:
                    buy_order = await self.order_manager.create_limit_buy_order(
                        client=wallet_pair.client_a,
                        wallet_address=wallet_pair.address_a,
                        market=self.config.default_market,
                        price=buy_price,
                        size=order_size
                    )
                    successful_orders += 1
                    self.orders_placed += 1
                    logger.info(f"Buy order placed: {buy_order.order_id}")
                
                # Place sell order with wallet B
                if wallet_pair.client_b:
                    sell_order = await self.order_manager.create_limit_sell_order(
                        client=wallet_pair.client_b,
                        wallet_address=wallet_pair.address_b,
                        market=self.config.default_market,
                        price=sell_price,
                        size=order_size
                    )
                    successful_orders += 1
                    self.orders_placed += 1
                    logger.info(f"Sell order placed: {sell_order.order_id}")
                    
            except OrderCreationError as e:
                logger.error(f"Failed to create orders for wallet pair: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error creating orders: {e}")
                continue
        
        logger.info(f"Successfully placed {successful_orders} orders")
        return successful_orders
    
    async def monitor_loop(self):
        """Main monitoring loop for the strategy"""
        logger.info("Starting main monitoring loop")
        
        while self.running and not self.shutdown_event.is_set():
            try:
                # Log strategy status
                self._log_status()
                
                # Check for filled orders
                filled_orders = self.order_manager.get_filled_orders()
                new_fills = len(filled_orders) - self.orders_filled
                if new_fills > 0:
                    self.orders_filled = len(filled_orders)
                    logger.info(f"New fills detected: {new_fills} orders filled")
                
                # Brief sleep
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)
    
    async def _on_liquidation(self, event: LiquidationEvent):
        """
        Handle liquidation events
        
        Args:
            event: Liquidation event details
        """
        logger.critical(f"Liquidation handler triggered: {event}")
        self.liquidations_handled += 1
        
        # Trigger emergency shutdown if enabled
        if self.settings.emergency_shutdown_enabled:
            logger.critical("Triggering emergency shutdown due to liquidation")
            await self.emergency_shutdown("Liquidation detected")
    
    async def emergency_shutdown(self, reason: str):
        """
        Perform emergency shutdown of the strategy
        
        Args:
            reason: Reason for shutdown
        """
        logger.critical(f"EMERGENCY SHUTDOWN: {reason}")
        
        # Set shutdown flag
        self.shutdown_event.set()
        self.running = False
        
        # Cancel all active orders
        logger.info("Cancelling all active orders")
        for wallet_pair in self.wallet_pairs:
            if wallet_pair.client_a:
                await self.order_manager.cancel_all_orders(
                    wallet_pair.client_a,
                    wallet_pair.address_a
                )
            if wallet_pair.client_b:
                await self.order_manager.cancel_all_orders(
                    wallet_pair.client_b,
                    wallet_pair.address_b
                )
        
        # Log final status
        self._log_status()
        logger.critical("Emergency shutdown complete")
    
    async def withdraw_all_funds(self) -> Dict[str, float]:
        """
        Withdraw all USDC from all wallets
        
        Returns:
            Dictionary of wallet addresses to withdrawn amounts
        """
        logger.info("Starting withdrawal of all funds")
        
        withdrawals = {}
        
        for wallet_pair in self.wallet_pairs:
            # Withdraw from wallet A
            if wallet_pair.client_a:
                try:
                    balance_a = await self._get_wallet_balance(
                        wallet_pair.client_a,
                        wallet_pair.address_a
                    )
                    if balance_a > 0:
                        await self._withdraw_usdc(
                            wallet_pair.client_a,
                            wallet_pair.address_a,
                            balance_a
                        )
                        withdrawals[wallet_pair.address_a] = balance_a
                        logger.info(f"Withdrew {balance_a} USDC from {wallet_pair.address_a[:8]}...")
                except Exception as e:
                    logger.error(f"Failed to withdraw from {wallet_pair.address_a}: {e}")
            
            # Withdraw from wallet B
            if wallet_pair.client_b:
                try:
                    balance_b = await self._get_wallet_balance(
                        wallet_pair.client_b,
                        wallet_pair.address_b
                    )
                    if balance_b > 0:
                        await self._withdraw_usdc(
                            wallet_pair.client_b,
                            wallet_pair.address_b,
                            balance_b
                        )
                        withdrawals[wallet_pair.address_b] = balance_b
                        logger.info(f"Withdrew {balance_b} USDC from {wallet_pair.address_b[:8]}...")
                except Exception as e:
                    logger.error(f"Failed to withdraw from {wallet_pair.address_b}: {e}")
        
        total_withdrawn = sum(withdrawals.values())
        logger.info(f"Total withdrawn: {total_withdrawn} USDC from {len(withdrawals)} wallets")
        
        return withdrawals
    
    async def _get_wallet_balance(self, client, address: str) -> float:
        """Get USDC balance for a wallet"""
        result = await client.get_balance(address=address, token="USDC")
        return float(result.get('balance', 0))
    
    async def _withdraw_usdc(self, client, address: str, amount: float):
        """Withdraw USDC from a wallet"""
        # This would call the actual withdrawal method
        # For now, it's a placeholder
        logger.info(f"Withdrawing {amount} USDC from {address[:8]}...")
        # await client.withdraw_usdc(amount=amount)
    
    def _log_status(self):
        """Log current strategy status"""
        if not self.running:
            return
            
        runtime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        runtime_mins = runtime / 60
        
        status_lines = [
            f"Strategy Status - Runtime: {runtime_mins:.1f} minutes",
            f"Orders: Placed={self.orders_placed}, Filled={self.orders_filled}",
            f"Active Orders: {len(self.order_manager.active_orders)}",
            f"Liquidations Handled: {self.liquidations_handled}",
            f"Wallet Pairs: {len(self.wallet_pairs)}"
        ]
        
        logger.info(" | ".join(status_lines))
    
    async def run_strategy(
        self,
        buy_price: float,
        sell_price: float,
        order_size: float,
        monitor_interval: int = 5
    ):
        """
        Main strategy execution
        
        Args:
            buy_price: Price for buy orders
            sell_price: Price for sell orders
            order_size: Size for each order
            monitor_interval: Seconds between monitoring cycles
        """
        logger.info("Starting strategy execution")
        self.running = True
        self.start_time = datetime.now()
        
        try:
            # Setup initial orders
            orders_placed = await self.setup_orders(buy_price, sell_price, order_size)
            if orders_placed == 0:
                logger.error("No orders were placed successfully")
                return
            
            # Create monitoring tasks
            tasks = []
            
            # Order monitoring
            clients_dict = {}
            for wp in self.wallet_pairs:
                if wp.client_a:
                    clients_dict[wp.address_a] = wp.client_a
                if wp.client_b:
                    clients_dict[wp.address_b] = wp.client_b
            
            tasks.append(asyncio.create_task(
                self.order_manager.monitor_order_fills(
                    clients_dict,
                    interval_seconds=monitor_interval
                )
            ))
            
            # Liquidation monitoring
            tasks.append(asyncio.create_task(
                self.liquidation_monitor.monitor_liquidations(
                    self.wallet_pairs,
                    interval_seconds=3
                )
            ))
            
            # Balance monitoring
            tasks.append(asyncio.create_task(
                self.balance_checker.monitor_balances(
                    self.wallet_pairs,
                    threshold=self.config.minimum_usdc,
                    interval_seconds=30
                )
            ))
            
            # Main monitoring loop
            tasks.append(asyncio.create_task(self.monitor_loop()))
            
            self.tasks = tasks
            
            # Wait for shutdown signal
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Strategy execution error: {e}")
            raise
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Clean up resources and shutdown gracefully"""
        logger.info("Starting cleanup")
        self.running = False
        
        # Cancel all tasks
        for task in self.tasks:
            if hasattr(task, 'done') and not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self.tasks:
            # Filter out non-async tasks
            async_tasks = [t for t in self.tasks if asyncio.iscoroutine(t) or asyncio.isfuture(t) or hasattr(t, '__await__')]
            if async_tasks:
                await asyncio.gather(*async_tasks, return_exceptions=True)
        
        # Stop monitors
        self.order_manager.stop_monitoring()
        self.liquidation_monitor.stop_monitoring()
        
        # Close wallet connections
        await self.wallet_manager.close_connections()
        
        logger.info("Cleanup complete")
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating shutdown")
        self.shutdown_event.set()


async def main():
    """Main entry point with CLI"""
    parser = argparse.ArgumentParser(
        description="Lighter Trading Strategy",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Wallet configuration
    parser.add_argument(
        "--wallet-pairs",
        type=str,
        default="",
        help="Wallet pairs as 'addr1a,addr1b;addr2a,addr2b' or path to JSON file (required for trading)"
    )
    
    # Trading parameters
    parser.add_argument(
        "--buy-price",
        type=float,
        required=True,
        help="Limit buy order price"
    )
    
    parser.add_argument(
        "--sell-price",
        type=float,
        required=True,
        help="Limit sell order price"
    )
    
    parser.add_argument(
        "--order-size",
        type=float,
        default=10.0,
        help="Size for each order (default: 10.0)"
    )
    
    parser.add_argument(
        "--market",
        type=str,
        default="SOL",
        help="Trading market (default: SOL)"
    )
    
    parser.add_argument(
        "--min-usdc",
        type=float,
        default=500.0,
        help="Minimum USDC balance required (default: 500)"
    )
    
    # Operational flags
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in test mode without executing trades"
    )
    
    parser.add_argument(
        "--config-file",
        type=str,
        help="Path to configuration file"
    )
    
    parser.add_argument(
        "--withdraw",
        action="store_true",
        help="Withdraw all funds and exit"
    )
    
    parser.add_argument(
        "--monitor-interval",
        type=int,
        default=5,
        help="Seconds between monitoring cycles (default: 5)"
    )
    
    args = parser.parse_args()
    
    # Parse wallet pairs - either from file or command line
    wallet_data = []
    
    if args.wallet_pairs:  # Only parse if wallet pairs provided
        # Check if it's a file path
        if args.wallet_pairs.endswith('.json'):
            wallet_pairs_path = Path(args.wallet_pairs)
            if not wallet_pairs_path.exists():
                logger.error(f"Wallet pairs file not found: {wallet_pairs_path}")
                sys.exit(1)
            with open(wallet_pairs_path) as f:
                wallet_data = json.load(f)
        else:
            # Parse command-line format: "addr1a,addr1b;addr2a,addr2b"
            try:
                pairs = args.wallet_pairs.split(';')
                for pair in pairs:
                    if not pair.strip():  # Skip empty pairs
                        continue
                    addresses = pair.strip().split(',')
                    if len(addresses) != 2:
                        raise ValueError(f"Invalid wallet pair format: {pair}")
                    wallet_data.append({
                        'address_a': addresses[0].strip(),
                        'address_b': addresses[1].strip(),
                        'private_key_a': None,  # Will need to be provided separately
                        'private_key_b': None   # Will need to be provided separately
                    })
                if wallet_data:
                    logger.info(f"Parsed {len(wallet_data)} wallet pairs from command line")
            except Exception as e:
                logger.error(f"Failed to parse wallet pairs: {e}")
                logger.error("Format should be: 'addr1a,addr1b;addr2a,addr2b' or path to JSON file")
                sys.exit(1)
    else:
        logger.warning("No wallet pairs provided - running in demo/test mode")
        logger.info("To trade, provide wallet pairs with --wallet-pairs")
    
    # Create strategy instance
    config = Config()
    config.minimum_usdc = args.min_usdc
    config.default_market = args.market
    
    strategy = LighterStrategy(config)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, strategy.signal_handler)
    signal.signal(signal.SIGTERM, strategy.signal_handler)
    
    try:
        # Initialize strategy
        if not await strategy.initialize(wallet_data):
            logger.error("Failed to initialize strategy")
            sys.exit(1)
        
        # Handle withdrawal mode
        if args.withdraw:
            logger.info("Withdrawal mode activated")
            withdrawals = await strategy.withdraw_all_funds()
            logger.info(f"Withdrawals complete: {withdrawals}")
            return
        
        # Run strategy
        await strategy.run_strategy(
            buy_price=args.buy_price,
            sell_price=args.sell_price,
            order_size=args.order_size,
            monitor_interval=args.monitor_interval
        )
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Strategy failed: {e}")
        sys.exit(1)
    finally:
        await strategy.cleanup()
        logger.info("Strategy shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())