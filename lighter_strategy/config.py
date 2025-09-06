"""Configuration module for Lighter Trading Strategy."""

from typing import List, Optional, Tuple
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()


class WalletPairConfig(BaseModel):
    """Configuration for a wallet pair."""
    
    address_a: str = Field(..., description="Address A for buy orders")
    address_b: str = Field(..., description="Address B for sell orders")
    api_key_a: Optional[str] = Field(None, description="API key for address A")
    api_key_b: Optional[str] = Field(None, description="API key for address B")
    
    @validator('address_a', 'address_b')
    def validate_address(cls, v):
        if not v or len(v) < 10:
            raise ValueError("Invalid wallet address")
        return v


class TradingParameters(BaseModel):
    """Trading strategy parameters."""
    
    market: str = Field(default="SOL", description="Trading market")
    buy_price: float = Field(default=50.0, gt=0, description="Limit buy order price")
    sell_price: float = Field(default=55.0, gt=0, description="Limit sell order price")
    order_size: Optional[float] = Field(None, gt=0, description="Order size")
    min_usdc_balance: float = Field(default=500.0, gt=0, description="Minimum USDC balance required")
    
    @validator('sell_price')
    def validate_prices(cls, v, values):
        if 'buy_price' in values and v <= values['buy_price']:
            raise ValueError("Sell price must be greater than buy price")
        return v


class RetryConfig(BaseModel):
    """Retry configuration for API calls."""
    
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_delay: float = Field(default=1.0, gt=0)
    max_retry_delay: float = Field(default=30.0, gt=0)
    exponential_backoff: bool = Field(default=True)


class MonitoringConfig(BaseModel):
    """Monitoring configuration."""
    
    order_check_interval: float = Field(default=5.0, gt=0, description="Seconds between order status checks")
    liquidation_check_interval: float = Field(default=2.0, gt=0, description="Seconds between liquidation checks")
    balance_check_interval: float = Field(default=30.0, gt=0, description="Seconds between balance checks")
    enable_websocket: bool = Field(default=True, description="Use WebSocket for real-time updates")
    websocket_reconnect_delay: float = Field(default=5.0, gt=0)


class LoggingConfig(BaseModel):
    """Logging configuration."""
    
    level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    file_path: Path = Field(default=Path("logs/lighter_strategy.log"))
    rotation: str = Field(default="1 day")
    retention: str = Field(default="7 days")
    format: str = Field(
        default="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}"
    )


class Settings(BaseSettings):
    """Main application settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # API Configuration
    api_base_url: str = Field(
        default="https://mainnet.zklighter.elliot.ai",
        description="Lighter API base URL"
    )
    api_version: str = Field(default="v1", description="API version")
    api_timeout: float = Field(default=30.0, gt=0, description="API request timeout in seconds")
    
    # Strategy Configuration
    dry_run: bool = Field(default=False, description="Run in test mode without executing trades")
    emergency_shutdown_enabled: bool = Field(default=True, description="Enable emergency shutdown")
    
    # Wallet Configuration
    wallet_pairs: List[WalletPairConfig] = Field(default_factory=list)
    
    # Trading Parameters
    trading: TradingParameters = Field(default_factory=TradingParameters)
    
    # Retry Configuration
    retry: RetryConfig = Field(default_factory=RetryConfig)
    
    # Monitoring Configuration
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    
    # Logging Configuration
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    
    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables."""
        try:
            return cls()
        except Exception:
            # If loading from env fails, return with defaults
            return cls(wallet_pairs=[])
    
    @classmethod
    def from_file(cls, config_file: Path) -> "Settings":
        """Load settings from a configuration file."""
        if config_file.suffix == ".json":
            import json
            with open(config_file) as f:
                data = json.load(f)
            return cls(**data)
        elif config_file.suffix in [".yaml", ".yml"]:
            import yaml
            with open(config_file) as f:
                data = yaml.safe_load(f)
            return cls(**data)
        else:
            raise ValueError(f"Unsupported config file format: {config_file.suffix}")
    
    def add_wallet_pair(self, address_a: str, address_b: str, 
                       api_key_a: Optional[str] = None, 
                       api_key_b: Optional[str] = None):
        """Add a wallet pair to the configuration."""
        pair = WalletPairConfig(
            address_a=address_a,
            address_b=address_b,
            api_key_a=api_key_a,
            api_key_b=api_key_b
        )
        self.wallet_pairs.append(pair)
    
    def validate_configuration(self) -> bool:
        """Validate the entire configuration."""
        if not self.wallet_pairs:
            raise ValueError("No wallet pairs configured")
        
        if self.trading.buy_price >= self.trading.sell_price:
            raise ValueError("Buy price must be less than sell price")
        
        return True
    
    def get_api_url(self, endpoint: str) -> str:
        """Get full API URL for an endpoint."""
        return f"{self.api_base_url}/{self.api_version}/{endpoint.lstrip('/')}"
    
    def to_dict(self) -> dict:
        """Convert settings to dictionary."""
        return self.model_dump()


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reset_settings():
    """Reset the global settings instance."""
    global _settings
    _settings = None


# Export commonly used configurations
def get_api_config() -> dict:
    """Get API configuration as dictionary."""
    settings = get_settings()
    return {
        "base_url": settings.api_base_url,
        "version": settings.api_version,
        "timeout": settings.api_timeout,
    }


def get_trading_params() -> TradingParameters:
    """Get trading parameters."""
    return get_settings().trading


def get_monitoring_config() -> MonitoringConfig:
    """Get monitoring configuration."""
    return get_settings().monitoring


# Simplified Config class for backward compatibility
class Config:
    """Simplified configuration class for testing and compatibility."""
    
    def __init__(self):
        try:
            settings = get_settings()
            self.api_endpoint = settings.api_base_url
            self.chain_id = 1
            # Handle case where trading is not initialized
            try:
                self.minimum_usdc = settings.trading.min_usdc_balance
            except:
                self.minimum_usdc = 500.0
            self.default_market = "SOL"
        except:
            # Default values for testing
            self.api_endpoint = "https://api.lighter.xyz"
            self.chain_id = 1
            self.minimum_usdc = 500.0
            self.default_market = "SOL"