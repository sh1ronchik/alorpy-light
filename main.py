import sys
import logging
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from AlorPy import AlorPy
from stock_logger import StockLogger
from config import TOKEN

def setup_logging(ap_provider) -> logging.Logger:
    """Настройка логирования с московским временем"""
    logger = logging.getLogger('AlorPy')
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%d.%m.%Y %H:%M:%S',
        level=logging.INFO,
        handlers=[
            logging.FileHandler('trading.log'),
            logging.StreamHandler()
        ]
    )
    logging.Formatter.converter = lambda *args: datetime.now(
        tz=ap_provider.tz_msk
    ).timetuple()
    return logger

def main() -> None:
    ap_provider = AlorPy()
    logger = setup_logging(ap_provider)

    try:
        symbol = input("Введите тикер акции (например SBER): ").strip().upper()
        stock_logger = StockLogger(symbol, TOKEN, ap_provider)
    except Exception as e:
        logger.error(f"Ошибка инициализации: {e}")
        sys.exit(1)

    # Параметры подписки
    exchange = 'MOEX'
    tf = 300  # 5-минутные бары
    days_history = 2  # дней исторических данных

    # Подписка на бары
    ap_provider.on_new_bar = stock_logger.on_new_bar
    from_time = ap_provider.msk_datetime_to_utc_timestamp(
        datetime.now() - timedelta(days=days_history)
    )
    
    guid = ap_provider.bars_get_and_subscribe(
        exchange, 
        symbol, 
        tf, 
        from_time,
        frequency=1_000_000_000
    )
    
    logger.info(f"Подписка {guid} активирована")

    try:
        plt.ion()
        input("\nНажмите Enter для остановки...\n")
    finally:
        ap_provider.unsubscribe(guid)
        ap_provider.close_web_socket()
        plt.ioff()
        plt.close()

if __name__ == '__main__':
    main()