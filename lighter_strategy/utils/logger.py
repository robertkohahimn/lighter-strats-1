"""Logging utilities for Lighter Trading Strategy."""

import sys
from pathlib import Path
from loguru import logger
from lighter_strategy.config import get_settings


def setup_logger():
    """Configure and initialize the logger."""
    settings = get_settings()
    log_config = settings.logging
    
    # Remove default logger
    logger.remove()
    
    # Create log directory if it doesn't exist
    log_file = Path(log_config.file_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Add console handler
    logger.add(
        sys.stdout,
        format=log_config.format,
        level=log_config.level,
        colorize=True,
        backtrace=True,
        diagnose=True
    )
    
    # Add file handler with rotation
    logger.add(
        log_file,
        format=log_config.format,
        level=log_config.level,
        rotation=log_config.rotation,
        retention=log_config.retention,
        compression="zip",
        backtrace=True,
        diagnose=True,
        enqueue=True  # Thread-safe logging
    )
    
    # Add critical error handler
    logger.add(
        log_file.parent / "critical_errors.log",
        format=log_config.format,
        level="ERROR",
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        backtrace=True,
        diagnose=True,
        enqueue=True
    )
    
    logger.info("Logger initialized successfully")
    logger.info(f"Log level: {log_config.level}")
    logger.info(f"Log file: {log_file}")
    
    return logger


def get_logger(name: str = None):
    """Get a logger instance with optional name binding."""
    if name:
        return logger.bind(name=name)
    return logger


# Initialize logger on import
setup_logger()