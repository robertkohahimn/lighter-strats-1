"""Custom exceptions for Lighter Trading Strategy."""


class LighterStrategyError(Exception):
    """Base exception for all strategy-related errors."""
    pass


class InsufficientBalanceError(LighterStrategyError):
    """Raised when wallet has insufficient balance."""
    
    def __init__(self, message: str = None, wallet_address: str = None, current_balance: float = None, required_balance: float = None):
        if message:
            super().__init__(message)
        elif wallet_address and current_balance is not None and required_balance is not None:
            self.wallet_address = wallet_address
            self.current_balance = current_balance
            self.required_balance = required_balance
            super().__init__(
                f"Insufficient balance in wallet {wallet_address}: "
                f"current={current_balance:.2f}, required={required_balance:.2f}"
            )
        else:
            super().__init__("Insufficient balance")


class OrderCreationError(LighterStrategyError):
    """Raised when order creation fails."""
    
    def __init__(self, message: str = None, wallet_address: str = None, order_type: str = None, reason: str = None):
        if message:
            super().__init__(message)
        elif wallet_address and order_type and reason:
            self.wallet_address = wallet_address
            self.order_type = order_type
            self.reason = reason
            super().__init__(
                f"Failed to create {order_type} order for wallet {wallet_address}: {reason}"
            )
        else:
            super().__init__("Order creation failed")


class LiquidationDetectedError(LighterStrategyError):
    """Raised when a liquidation is detected."""
    
    def __init__(self, wallet_address: str, position_details: dict = None):
        self.wallet_address = wallet_address
        self.position_details = position_details or {}
        super().__init__(
            f"Liquidation detected for wallet {wallet_address}: {position_details}"
        )


class WithdrawalError(LighterStrategyError):
    """Raised when withdrawal fails."""
    
    def __init__(self, wallet_address: str, amount: float, reason: str):
        self.wallet_address = wallet_address
        self.amount = amount
        self.reason = reason
        super().__init__(
            f"Failed to withdraw {amount:.2f} USDC from wallet {wallet_address}: {reason}"
        )


class ConnectionError(LighterStrategyError):
    """Raised when API connection fails."""
    
    def __init__(self, endpoint: str, reason: str, retry_count: int = 0):
        self.endpoint = endpoint
        self.reason = reason
        self.retry_count = retry_count
        super().__init__(
            f"Connection failed to {endpoint} after {retry_count} retries: {reason}"
        )


class WalletConnectionError(LighterStrategyError):
    """Raised when wallet connection fails."""
    
    def __init__(self, message: str):
        super().__init__(message)


class AuthenticationError(LighterStrategyError):
    """Raised when authentication fails."""
    
    def __init__(self, wallet_address: str, reason: str):
        self.wallet_address = wallet_address
        self.reason = reason
        super().__init__(
            f"Authentication failed for wallet {wallet_address}: {reason}"
        )


class ConfigurationError(LighterStrategyError):
    """Raised when configuration is invalid."""
    
    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(
            f"Invalid configuration for {field}: {reason}"
        )


class OrderMonitoringError(LighterStrategyError):
    """Raised when order monitoring encounters an error."""
    
    def __init__(self, order_id: str, reason: str):
        self.order_id = order_id
        self.reason = reason
        super().__init__(
            f"Error monitoring order {order_id}: {reason}"
        )


class EmergencyShutdownError(LighterStrategyError):
    """Raised when emergency shutdown is triggered."""
    
    def __init__(self, reason: str, affected_wallets: list = None):
        self.reason = reason
        self.affected_wallets = affected_wallets or []
        super().__init__(
            f"Emergency shutdown triggered: {reason}. "
            f"Affected wallets: {', '.join(self.affected_wallets)}"
        )