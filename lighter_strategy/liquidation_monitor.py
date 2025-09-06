"""
Liquidation Monitor Module for Lighter Trading Strategy
Monitors positions for liquidations and handles emergency closures
"""

import asyncio
from typing import List, Dict, Optional, Callable, Set
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
# Mock LighterClient for now - will be replaced with actual implementation
class LighterClient:
    def __init__(self, **kwargs):
        pass
    
    async def get_position(self, **kwargs):
        return {'size': '0'}
    
    async def create_order(self, **kwargs):
        return {'order_id': 'mock_order_id'}
    
    async def close(self):
        pass
from .wallet_manager import WalletPair
from .order_manager import OrderManager
from .utils.logger import logger
from .utils.exceptions import LiquidationDetectedError


class PositionStatus(Enum):
    """Position health status"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    LIQUIDATED = "liquidated"


@dataclass
class PositionInfo:
    """Information about a trading position"""
    wallet_address: str
    market: str
    side: str  # "long" or "short"
    size: float
    entry_price: float
    mark_price: float
    liquidation_price: float
    margin: float
    unrealized_pnl: float
    health_ratio: float
    status: PositionStatus
    timestamp: datetime = field(default_factory=datetime.now)
    
    def get_distance_to_liquidation(self) -> float:
        """Calculate percentage distance to liquidation price"""
        if self.side == "long":
            distance = (self.mark_price - self.liquidation_price) / self.mark_price
        else:
            distance = (self.liquidation_price - self.mark_price) / self.mark_price
        return distance * 100
    
    def __str__(self):
        return (f"Position {self.wallet_address[:8]}... | {self.side} {self.size} @ {self.entry_price} | "
                f"Mark: {self.mark_price} | Liq: {self.liquidation_price} | "
                f"Health: {self.health_ratio:.2%} | Status: {self.status.value}")


@dataclass 
class LiquidationEvent:
    """Represents a liquidation event"""
    wallet_address: str
    wallet_pair: Optional[WalletPair]
    market: str
    side: str
    size: float
    liquidation_price: float
    timestamp: datetime = field(default_factory=datetime.now)
    action_taken: Optional[str] = None
    
    def __str__(self):
        return (f"LIQUIDATION: {self.wallet_address[:8]}... | {self.side} {self.size} | "
                f"Price: {self.liquidation_price} | Action: {self.action_taken or 'Pending'}")


class LiquidationMonitor:
    """Monitors positions for liquidations and manages emergency responses"""
    
    def __init__(self, order_manager: OrderManager):
        """
        Initialize the liquidation monitor
        
        Args:
            order_manager: OrderManager instance for handling emergency orders
        """
        self.order_manager = order_manager
        self.positions: Dict[str, PositionInfo] = {}
        self.liquidation_events: List[LiquidationEvent] = []
        self.monitoring_active = False
        self.liquidation_callbacks: List[Callable] = []
        self.liquidated_wallets: Set[str] = set()
        
        self.warning_threshold = 0.15  # Warn when 15% from liquidation
        self.critical_threshold = 0.05  # Critical when 5% from liquidation
    
    async def monitor_liquidations(
        self,
        wallet_pairs: List[WalletPair],
        interval_seconds: int = 3
    ):
        """
        Monitor wallet pairs for liquidations
        
        Args:
            wallet_pairs: List of WalletPair objects to monitor
            interval_seconds: How often to check positions
        """
        logger.info(f"Starting liquidation monitoring for {len(wallet_pairs)} wallet pairs")
        self.monitoring_active = True
        
        while self.monitoring_active:
            try:
                tasks = []
                for wallet_pair in wallet_pairs:
                    if wallet_pair.client_a:
                        tasks.append(self._check_position(
                            wallet_pair.client_a,
                            wallet_pair.address_a,
                            wallet_pair
                        ))
                    if wallet_pair.client_b:
                        tasks.append(self._check_position(
                            wallet_pair.client_b,
                            wallet_pair.address_b,
                            wallet_pair
                        ))
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Position check failed: {result}")
                
                await self._analyze_positions()
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in liquidation monitoring: {e}")
                await asyncio.sleep(interval_seconds)
    
    async def _check_position(
        self,
        client: LighterClient,
        wallet_address: str,
        wallet_pair: WalletPair
    ) -> Optional[PositionInfo]:
        """
        Check position health for a wallet
        
        Args:
            client: Lighter API client
            wallet_address: Wallet address to check
            wallet_pair: Associated wallet pair
            
        Returns:
            PositionInfo if position exists, None otherwise
        """
        try:
            position_data = await client.get_position(
                wallet_address=wallet_address,
                market="SOL"
            )
            
            if not position_data or float(position_data.get('size', 0)) == 0:
                return None
            
            position_info = PositionInfo(
                wallet_address=wallet_address,
                market=position_data.get('market', 'SOL'),
                side=position_data.get('side', 'long'),
                size=float(position_data.get('size', 0)),
                entry_price=float(position_data.get('entry_price', 0)),
                mark_price=float(position_data.get('mark_price', 0)),
                liquidation_price=float(position_data.get('liquidation_price', 0)),
                margin=float(position_data.get('margin', 0)),
                unrealized_pnl=float(position_data.get('unrealized_pnl', 0)),
                health_ratio=float(position_data.get('health_ratio', 1.0)),
                status=self._determine_position_status(position_data)
            )
            
            self.positions[wallet_address] = position_info
            
            if position_info.status == PositionStatus.LIQUIDATED:
                await self._handle_liquidation(position_info, wallet_pair)
            
            return position_info
            
        except Exception as e:
            logger.error(f"Failed to check position for {wallet_address}: {e}")
            return None
    
    def _determine_position_status(self, position_data: Dict) -> PositionStatus:
        """
        Determine the health status of a position
        
        Args:
            position_data: Position data from API
            
        Returns:
            PositionStatus enum value
        """
        if position_data.get('is_liquidated', False):
            return PositionStatus.LIQUIDATED
        
        health_ratio = float(position_data.get('health_ratio', 1.0))
        
        if health_ratio <= self.critical_threshold:
            return PositionStatus.CRITICAL
        elif health_ratio <= self.warning_threshold:
            return PositionStatus.WARNING
        else:
            return PositionStatus.HEALTHY
    
    async def _handle_liquidation(
        self,
        position_info: PositionInfo,
        wallet_pair: WalletPair
    ):
        """
        Handle a detected liquidation
        
        Args:
            position_info: Information about the liquidated position
            wallet_pair: The wallet pair involved
        """
        if position_info.wallet_address in self.liquidated_wallets:
            return
        
        self.liquidated_wallets.add(position_info.wallet_address)
        
        logger.critical(f"LIQUIDATION DETECTED: {position_info}")
        
        liquidation_event = LiquidationEvent(
            wallet_address=position_info.wallet_address,
            wallet_pair=wallet_pair,
            market=position_info.market,
            side=position_info.side,
            size=position_info.size,
            liquidation_price=position_info.mark_price
        )
        
        self.liquidation_events.append(liquidation_event)
        
        try:
            await self.trigger_emergency_close(wallet_pair, position_info)
            liquidation_event.action_taken = "Emergency close triggered"
        except Exception as e:
            logger.error(f"Failed to trigger emergency close: {e}")
            liquidation_event.action_taken = f"Emergency close failed: {e}"
        
        for callback in self.liquidation_callbacks:
            try:
                await callback(liquidation_event)
            except Exception as e:
                logger.error(f"Liquidation callback failed: {e}")
    
    async def check_liquidation_status(self, wallet_address: str, client: LighterClient) -> bool:
        """
        Check if a specific wallet has been liquidated
        
        Args:
            wallet_address: Wallet address to check
            client: Lighter API client
            
        Returns:
            True if liquidated, False otherwise
        """
        try:
            position_data = await client.get_position(
                wallet_address=wallet_address,
                market="SOL"
            )
            
            is_liquidated = position_data.get('is_liquidated', False)
            
            if is_liquidated:
                logger.warning(f"Wallet {wallet_address[:8]}... is liquidated")
            
            return is_liquidated
            
        except Exception as e:
            logger.error(f"Failed to check liquidation status: {e}")
            return False
    
    async def trigger_emergency_close(
        self,
        wallet_pair: WalletPair,
        liquidated_position: PositionInfo
    ):
        """
        Trigger emergency closure of opposite position
        
        Args:
            wallet_pair: The wallet pair with liquidation
            liquidated_position: Information about the liquidated position
        """
        logger.critical(f"Triggering emergency close for wallet pair")
        
        opposite_address = (wallet_pair.address_b 
                          if liquidated_position.wallet_address == wallet_pair.address_a 
                          else wallet_pair.address_a)
        opposite_client = (wallet_pair.client_b 
                         if liquidated_position.wallet_address == wallet_pair.address_a 
                         else wallet_pair.client_a)
        
        if not opposite_client:
            logger.error("No client available for opposite wallet")
            return
        
        try:
            await self.order_manager.cancel_all_orders(opposite_client, opposite_address)
            
            await self.close_opposite_trade(
                wallet_pair,
                liquidated_position.side,
                opposite_client,
                opposite_address
            )
            
            logger.info(f"Emergency close completed for {opposite_address[:8]}...")
            
        except Exception as e:
            logger.error(f"Emergency close failed: {e}")
            raise
    
    async def close_opposite_trade(
        self,
        wallet_pair: WalletPair,
        liquidated_side: str,
        client: LighterClient,
        wallet_address: str
    ):
        """
        Close the opposite side of a liquidated trade
        
        Args:
            wallet_pair: The wallet pair involved
            liquidated_side: The side that was liquidated ("long" or "short")
            client: Lighter API client for the opposite wallet
            wallet_address: Address of the opposite wallet
        """
        logger.info(f"Closing opposite trade for {wallet_address[:8]}...")
        
        try:
            position_data = await client.get_position(
                wallet_address=wallet_address,
                market="SOL"
            )
            
            if not position_data or position_data.get('size', 0) == 0:
                logger.warning(f"No position to close for {wallet_address[:8]}...")
                return
            
            position_size = float(position_data.get('size', 0))
            position_side = position_data.get('side', '')
            
            if liquidated_side == "long" and position_side == "short":
                await client.create_order(
                    market="SOL",
                    side="buy",
                    order_type="market",
                    size=str(position_size),
                    wallet_address=wallet_address
                )
                logger.info(f"Closed short position of {position_size} for {wallet_address[:8]}...")
                
            elif liquidated_side == "short" and position_side == "long":
                await client.create_order(
                    market="SOL",
                    side="sell",
                    order_type="market",
                    size=str(position_size),
                    wallet_address=wallet_address
                )
                logger.info(f"Closed long position of {position_size} for {wallet_address[:8]}...")
            else:
                logger.warning(f"Unexpected position configuration for emergency close")
                
        except Exception as e:
            logger.error(f"Failed to close opposite trade: {e}")
            raise
    
    async def _analyze_positions(self):
        """Analyze all positions and log warnings"""
        critical_positions = []
        warning_positions = []
        
        for position in self.positions.values():
            if position.status == PositionStatus.CRITICAL:
                critical_positions.append(position)
            elif position.status == PositionStatus.WARNING:
                warning_positions.append(position)
        
        if critical_positions:
            logger.critical(f"⚠️ {len(critical_positions)} positions in CRITICAL state!")
            for pos in critical_positions:
                distance = pos.get_distance_to_liquidation()
                logger.critical(
                    f"CRITICAL: {pos.wallet_address[:8]}... is {distance:.2f}% from liquidation"
                )
        
        if warning_positions:
            logger.warning(f"⚠️ {len(warning_positions)} positions in WARNING state")
            for pos in warning_positions:
                distance = pos.get_distance_to_liquidation()
                logger.warning(
                    f"WARNING: {pos.wallet_address[:8]}... is {distance:.2f}% from liquidation"
                )
    
    def add_liquidation_callback(self, callback: Callable):
        """
        Add a callback to be called on liquidation events
        
        Args:
            callback: Async function to call on liquidation
        """
        self.liquidation_callbacks.append(callback)
        logger.debug(f"Added liquidation callback: {callback.__name__}")
    
    def stop_monitoring(self):
        """Stop liquidation monitoring"""
        self.monitoring_active = False
        logger.info("Liquidation monitoring stopped")
    
    def get_position_summary(self) -> str:
        """
        Get a summary of all monitored positions
        
        Returns:
            Formatted string summary
        """
        if not self.positions:
            return "No positions being monitored"
        
        summary_lines = [
            "\n" + "="*70,
            "POSITION MONITORING SUMMARY",
            f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "="*70
        ]
        
        healthy_count = sum(1 for p in self.positions.values() 
                          if p.status == PositionStatus.HEALTHY)
        warning_count = sum(1 for p in self.positions.values() 
                          if p.status == PositionStatus.WARNING)
        critical_count = sum(1 for p in self.positions.values() 
                           if p.status == PositionStatus.CRITICAL)
        liquidated_count = len(self.liquidated_wallets)
        
        summary_lines.extend([
            f"Total Positions: {len(self.positions)}",
            f"Healthy: {healthy_count} | Warning: {warning_count} | "
            f"Critical: {critical_count} | Liquidated: {liquidated_count}",
            "-"*70
        ])
        
        for position in self.positions.values():
            status_icon = {
                PositionStatus.HEALTHY: "✅",
                PositionStatus.WARNING: "⚠️",
                PositionStatus.CRITICAL: "🚨",
                PositionStatus.LIQUIDATED: "💀"
            }.get(position.status, "❓")
            
            distance = position.get_distance_to_liquidation()
            summary_lines.append(
                f"{status_icon} {position.wallet_address[:8]}... | "
                f"{position.side} {position.size:.4f} | "
                f"Entry: {position.entry_price:.2f} | Mark: {position.mark_price:.2f} | "
                f"Liq: {position.liquidation_price:.2f} ({distance:+.2f}%) | "
                f"PnL: {position.unrealized_pnl:+.2f}"
            )
        
        if self.liquidation_events:
            summary_lines.extend([
                "-"*70,
                "LIQUIDATION EVENTS:"
            ])
            for event in self.liquidation_events[-5:]:
                summary_lines.append(f"  {event}")
        
        summary_lines.append("="*70)
        
        return "\n".join(summary_lines)