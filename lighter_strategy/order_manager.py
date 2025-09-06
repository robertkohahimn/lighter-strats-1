"""
Order Manager Module for Lighter Trading Strategy
Handles order creation, monitoring, and management
"""

import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from lighter_client import LighterClient
from .utils.logger import logger
from .utils.exceptions import OrderCreationError


class OrderType(Enum):
    """Order types supported by the system"""
    LIMIT_BUY = "limit_buy"
    LIMIT_SELL = "limit_sell"
    MARKET_BUY = "market_buy"
    MARKET_SELL = "market_sell"


class OrderStatus(Enum):
    """Order status states"""
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Order:
    """Represents a trading order"""
    order_id: str
    wallet_address: str
    market: str
    order_type: OrderType
    price: float
    size: float
    status: OrderStatus = OrderStatus.PENDING
    filled_size: float = 0.0
    remaining_size: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        self.remaining_size = self.size - self.filled_size
    
    def update_fill(self, filled_amount: float):
        """Update order fill information"""
        self.filled_size += filled_amount
        self.remaining_size = self.size - self.filled_size
        self.updated_at = datetime.now()
        
        if self.remaining_size <= 0:
            self.status = OrderStatus.FILLED
        elif self.filled_size > 0:
            self.status = OrderStatus.PARTIALLY_FILLED
    
    def is_complete(self) -> bool:
        """Check if order is complete (filled or cancelled)"""
        return self.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.FAILED]
    
    def __str__(self):
        return (f"Order {self.order_id[:8]}... | {self.order_type.value} | "
                f"{self.market} | Price: {self.price} | Size: {self.size} | "
                f"Filled: {self.filled_size}/{self.size} | Status: {self.status.value}")


class OrderManager:
    """Manages order creation, monitoring, and lifecycle"""
    
    def __init__(self):
        """Initialize the order manager"""
        self.orders: Dict[str, Order] = {}
        self.active_orders: Dict[str, Order] = {}
        self.filled_orders: List[Order] = []
        self.monitoring_active = False
        
    async def create_limit_buy_order(
        self,
        client: LighterClient,
        wallet_address: str,
        market: str,
        price: float,
        size: float
    ) -> Order:
        """
        Create a limit buy order
        
        Args:
            client: Lighter API client
            wallet_address: Wallet address placing the order
            market: Market symbol (e.g., "SOL")
            price: Order price
            size: Order size
            
        Returns:
            Created Order object
        """
        logger.info(f"Creating limit buy order: {market} @ {price} x {size}")
        
        try:
            await self._validate_order_params(price, size)
            
            response = await client.create_order(
                market=market,
                side="buy",
                order_type="limit",
                price=str(price),
                size=str(size),
                wallet_address=wallet_address
            )
            
            order_id = response.get('order_id')
            if not order_id:
                raise OrderCreationError("No order ID returned from API")
            
            order = Order(
                order_id=order_id,
                wallet_address=wallet_address,
                market=market,
                order_type=OrderType.LIMIT_BUY,
                price=price,
                size=size,
                status=OrderStatus.OPEN
            )
            
            self.orders[order_id] = order
            self.active_orders[order_id] = order
            
            logger.info(f"Created buy order {order_id[:8]}... for {wallet_address[:8]}...")
            return order
            
        except Exception as e:
            logger.error(f"Failed to create buy order: {e}")
            raise OrderCreationError(f"Buy order creation failed: {e}")
    
    async def create_limit_sell_order(
        self,
        client: LighterClient,
        wallet_address: str,
        market: str,
        price: float,
        size: float
    ) -> Order:
        """
        Create a limit sell order
        
        Args:
            client: Lighter API client
            wallet_address: Wallet address placing the order
            market: Market symbol (e.g., "SOL")
            price: Order price
            size: Order size
            
        Returns:
            Created Order object
        """
        logger.info(f"Creating limit sell order: {market} @ {price} x {size}")
        
        try:
            await self._validate_order_params(price, size)
            
            response = await client.create_order(
                market=market,
                side="sell",
                order_type="limit",
                price=str(price),
                size=str(size),
                wallet_address=wallet_address
            )
            
            order_id = response.get('order_id')
            if not order_id:
                raise OrderCreationError("No order ID returned from API")
            
            order = Order(
                order_id=order_id,
                wallet_address=wallet_address,
                market=market,
                order_type=OrderType.LIMIT_SELL,
                price=price,
                size=size,
                status=OrderStatus.OPEN
            )
            
            self.orders[order_id] = order
            self.active_orders[order_id] = order
            
            logger.info(f"Created sell order {order_id[:8]}... for {wallet_address[:8]}...")
            return order
            
        except Exception as e:
            logger.error(f"Failed to create sell order: {e}")
            raise OrderCreationError(f"Sell order creation failed: {e}")
    
    async def get_order_status(self, order_id: str, client: LighterClient) -> OrderStatus:
        """
        Get the current status of an order
        
        Args:
            order_id: The order ID to check
            client: Lighter API client
            
        Returns:
            Current OrderStatus
        """
        try:
            response = await client.get_order(order_id=order_id)
            
            status_str = response.get('status', 'unknown').lower()
            filled_size = float(response.get('filled_size', 0))
            
            order = self.orders.get(order_id)
            if order:
                order.filled_size = filled_size
                order.remaining_size = order.size - filled_size
                order.updated_at = datetime.now()
                
                if status_str == 'filled':
                    order.status = OrderStatus.FILLED
                    self._move_to_filled(order)
                elif status_str == 'cancelled':
                    order.status = OrderStatus.CANCELLED
                    self._remove_from_active(order_id)
                elif filled_size > 0:
                    order.status = OrderStatus.PARTIALLY_FILLED
                else:
                    order.status = OrderStatus.OPEN
                
                logger.debug(f"Order {order_id[:8]}... status: {order.status.value}")
                return order.status
            
            return OrderStatus.OPEN
            
        except Exception as e:
            logger.error(f"Failed to get order status for {order_id}: {e}")
            return OrderStatus.FAILED
    
    async def cancel_order(self, order_id: str, client: LighterClient) -> bool:
        """
        Cancel an active order
        
        Args:
            order_id: The order ID to cancel
            client: Lighter API client
            
        Returns:
            True if cancellation successful, False otherwise
        """
        try:
            logger.info(f"Cancelling order {order_id[:8]}...")
            
            response = await client.cancel_order(order_id=order_id)
            
            if response.get('success'):
                order = self.orders.get(order_id)
                if order:
                    order.status = OrderStatus.CANCELLED
                    order.updated_at = datetime.now()
                    self._remove_from_active(order_id)
                
                logger.info(f"Successfully cancelled order {order_id[:8]}...")
                return True
            else:
                logger.warning(f"Failed to cancel order {order_id[:8]}...")
                return False
                
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    async def cancel_all_orders(self, client: LighterClient, wallet_address: Optional[str] = None) -> int:
        """
        Cancel all active orders, optionally filtered by wallet
        
        Args:
            client: Lighter API client
            wallet_address: Optional wallet address filter
            
        Returns:
            Number of orders cancelled
        """
        orders_to_cancel = []
        
        for order_id, order in self.active_orders.items():
            if wallet_address is None or order.wallet_address == wallet_address:
                orders_to_cancel.append(order_id)
        
        logger.info(f"Cancelling {len(orders_to_cancel)} orders")
        
        tasks = [self.cancel_order(order_id, client) for order_id in orders_to_cancel]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        cancelled_count = sum(1 for r in results if r is True)
        logger.info(f"Cancelled {cancelled_count}/{len(orders_to_cancel)} orders")
        
        return cancelled_count
    
    def get_filled_orders(self) -> List[Order]:
        """
        Get all filled orders
        
        Returns:
            List of filled Order objects
        """
        return self.filled_orders.copy()
    
    def get_active_orders(self, wallet_address: Optional[str] = None) -> List[Order]:
        """
        Get active orders, optionally filtered by wallet
        
        Args:
            wallet_address: Optional wallet address filter
            
        Returns:
            List of active Order objects
        """
        if wallet_address:
            return [o for o in self.active_orders.values() if o.wallet_address == wallet_address]
        return list(self.active_orders.values())
    
    async def monitor_order_fills(self, clients: Dict[str, LighterClient], interval_seconds: int = 5):
        """
        Continuously monitor orders for fills
        
        Args:
            clients: Dictionary mapping wallet addresses to Lighter clients
            interval_seconds: How often to check order status
        """
        logger.info(f"Starting order fill monitoring (interval: {interval_seconds}s)")
        self.monitoring_active = True
        
        while self.monitoring_active:
            try:
                if not self.active_orders:
                    await asyncio.sleep(interval_seconds)
                    continue
                
                tasks = []
                for order_id, order in list(self.active_orders.items()):
                    client = clients.get(order.wallet_address)
                    if client:
                        tasks.append(self.get_order_status(order_id, client))
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                filled_count = len([o for o in self.active_orders.values() 
                                  if o.status == OrderStatus.FILLED])
                partial_count = len([o for o in self.active_orders.values() 
                                   if o.status == OrderStatus.PARTIALLY_FILLED])
                
                if filled_count > 0 or partial_count > 0:
                    logger.info(f"Order status: {filled_count} filled, {partial_count} partial, "
                              f"{len(self.active_orders)} active")
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in order monitoring: {e}")
                await asyncio.sleep(interval_seconds)
    
    def stop_monitoring(self):
        """Stop order monitoring"""
        self.monitoring_active = False
        logger.info("Order monitoring stopped")
    
    async def _validate_order_params(self, price: float, size: float):
        """
        Validate order parameters before submission
        
        Args:
            price: Order price
            size: Order size
            
        Raises:
            OrderCreationError if validation fails
        """
        if price <= 0:
            raise OrderCreationError(f"Invalid price: {price}")
        if size <= 0:
            raise OrderCreationError(f"Invalid size: {size}")
        
        if price > 1000000:
            raise OrderCreationError(f"Price too high: {price}")
        if size > 1000000:
            raise OrderCreationError(f"Size too large: {size}")
    
    def _move_to_filled(self, order: Order):
        """Move order from active to filled"""
        if order.order_id in self.active_orders:
            del self.active_orders[order.order_id]
            self.filled_orders.append(order)
            logger.debug(f"Moved order {order.order_id[:8]}... to filled")
    
    def _remove_from_active(self, order_id: str):
        """Remove order from active orders"""
        if order_id in self.active_orders:
            del self.active_orders[order_id]
            logger.debug(f"Removed order {order_id[:8]}... from active")
    
    def get_order_summary(self) -> str:
        """
        Get a summary of all orders
        
        Returns:
            Formatted string summary
        """
        total_orders = len(self.orders)
        active_count = len(self.active_orders)
        filled_count = len(self.filled_orders)
        cancelled_count = len([o for o in self.orders.values() 
                              if o.status == OrderStatus.CANCELLED])
        
        summary_lines = [
            "\n" + "="*60,
            "ORDER SUMMARY",
            f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "="*60,
            f"Total Orders: {total_orders}",
            f"Active: {active_count}",
            f"Filled: {filled_count}",
            f"Cancelled: {cancelled_count}",
            "-"*60
        ]
        
        if self.active_orders:
            summary_lines.append("\nACTIVE ORDERS:")
            for order in self.active_orders.values():
                summary_lines.append(f"  {order}")
        
        if self.filled_orders and len(self.filled_orders) <= 10:
            summary_lines.append("\nRECENT FILLS:")
            for order in self.filled_orders[-5:]:
                summary_lines.append(f"  {order}")
        
        summary_lines.append("="*60)
        
        return "\n".join(summary_lines)