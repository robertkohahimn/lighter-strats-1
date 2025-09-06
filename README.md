# Lighter Trading Strategy

Automated trading strategy for Lighter platform that manages multiple wallet pairs with limit orders, liquidation monitoring, and automated withdrawals.

## Features

- Multiple wallet pair management
- Automated limit buy/sell order placement
- Real-time order fill monitoring
- Liquidation detection and emergency response
- Automated USDC withdrawal
- Comprehensive logging and error handling

## Installation

1. Clone the repository
2. Create virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

## Usage

### Basic Command

```bash
python lighter_strategy/main.py \
  --wallet-pairs "wallet1a,wallet1b;wallet2a,wallet2b" \
  --market SOL \
  --buy-price 100.50 \
  --sell-price 105.00 \
  --min-usdc 500
```

### Configuration

Edit `.env` file or pass parameters via CLI:

- `API_BASE_URL`: Lighter API endpoint
- `MIN_USDC_BALANCE`: Minimum USDC required per wallet (default: 500)
- `DRY_RUN`: Test mode without executing trades
- `LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)

## Project Structure

```
lighter_strategy/
├── config.py              # Configuration management
├── wallet_manager.py      # Wallet pair operations
├── order_manager.py       # Order creation and monitoring
├── liquidation_monitor.py # Liquidation detection
├── balance_checker.py     # Balance validation
├── main.py               # Main orchestrator
└── utils/
    ├── logger.py         # Logging utilities
    └── exceptions.py     # Custom exceptions
```

## Testing

Run tests with:
```bash
pytest tests/
```

## Safety Features

- Minimum balance validation before trading
- Automatic position closing on liquidation detection
- Emergency shutdown capability
- Comprehensive error handling and retry logic
- Detailed logging for audit trail

## Development Status

Phase 1 ✅ - Setup and configuration complete
Phase 2 🚧 - Core components in development
Phase 3 ⏳ - Main strategy implementation pending
Phase 4 ⏳ - Monitoring system pending
Phase 5 ⏳ - Withdrawal system pending
Phase 6 ⏳ - Testing pending

## License

Proprietary - All rights reserved