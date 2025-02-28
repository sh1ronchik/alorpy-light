import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import matplotlib.pyplot as plt
from tinkoff.invest import Client, CandleInterval
from tinkoff.invest.utils import quotation_to_decimal

class StockLogger:
    def __init__(self, symbol: str, token: str, ap_provider) -> None:
        self.symbol = symbol.upper()
        self.token = token
        self.ap_provider = ap_provider
        self.figi: Optional[str] = None
        self.issued_shares: Optional[int] = None
        self.last_update: Optional[datetime] = None
        self.times: List[datetime] = []
        self.prices: List[float] = []
        self._initialize_stock_data()

    def _initialize_stock_data(self) -> None:
        """Инициализация данных акции при старте"""
        with Client(self.token) as client:
            share = next(
                (s for s in client.instruments.shares().instruments 
                 if s.ticker == self.symbol),
                None
            )
            if not share:
                raise ValueError(f"Акция {self.symbol} не найдена")
            
            last_price = client.market_data.get_last_prices(figi=[share.figi]).last_prices[0]
            
            self.figi = share.figi
            self.issued_shares = share.issue_size
            self.last_price = float(quotation_to_decimal(last_price.price))
            self.last_update = datetime.now(self.ap_provider.tz_msk)
            logging.info(f"Инициализирован {self.symbol} (FIGI: {self.figi})")

    def _refresh_stock_data(self) -> None:
        """Ежесуточное обновление данных об акции"""
        if (datetime.now(self.ap_provider.tz_msk) - self.last_update) < timedelta(hours=23):
            return

        try:
            with Client(self.token) as client:
                share = next(s for s in client.instruments.shares().instruments 
                           if s.ticker == self.symbol)
                self.issued_shares = share.issue_size
                self.last_update = datetime.now(self.ap_provider.tz_msk)
                logging.debug("Данные акции обновлены")
        except Exception as e:
            logging.error(f"Ошибка обновления акции: {e}")

    def _get_daily_volume(self, target_dt: datetime) -> dict:
        """
        Получение поминутного объёма торгов с 06:50 МСК до времени target_dt.
        Возвращается словарь вида:
        {"06:50": volume, "06:51": volume, ..., "target_dt": volume}
        """
        if not self.figi:
            logging.error("FIGI не установлен")
            return {}

        try:
            # Определяем начало торгового дня в МСК
            start_local = target_dt.replace(hour=6, minute=50, second=0, microsecond=0)
            
            # Конец интервала — время target_dt
            end_local = target_dt

            # Переводим время в UTC (МСК = UTC+3)
            start = start_local.astimezone(timezone.utc)
            end = end_local.astimezone(timezone.utc)
            
            volumes_by_minute = {}
            
            with Client(self.token) as client:
                # Получаем свечи с минутным интервалом
                candles = client.get_all_candles(
                    figi=self.figi,
                    from_=start,
                    to=end,
                    interval=CandleInterval.CANDLE_INTERVAL_1_MIN
                )
                for candle in candles:
                    # Переводим время свечи из UTC в МСК
                    local_time = candle.time.astimezone(timezone(timedelta(hours=3)))
                    # Форматируем метку времени как "HH:MM"
                    time_label = local_time.strftime("%H:%M")
                    volumes_by_minute[time_label] = volumes_by_minute.get(time_label, 0) + candle.volume
            
            return volumes_by_minute

        except Exception as e:
            logging.error(f"Ошибка запроса объёма: {str(e)}")
            return {}

    def on_new_bar(self, response: dict) -> None:
        """Обработчик новых баров с привязкой к дате бара"""
        try:
            self._refresh_stock_data()
            
            # Получение времени бара в МСК
            sub = self.ap_provider.subscriptions[response['guid']]
            dt = self.ap_provider.utc_timestamp_to_msk_datetime(
                response['data']['time']
            )
            close_price = response['data']['close']

            # Логирование с временем бара
            log_time = dt.strftime('%d.%m.%Y %H:%M')
            logging.info(
                f"{sub['exchange']}.{self.symbol} | {log_time} | Цена: {close_price:.2f}"
            )

            # Обновление данных графика
            self.times.append(dt)
            self.prices.append(close_price)

            # Расчет капитализации
            if self.issued_shares:
                market_cap = self.issued_shares * close_price
                print(f"\nКапитализация: {market_cap:,.2f} RUB")
            
            # Получение объема для даты бара
            daily_volume = self._get_daily_volume(dt)
            print(f"Объём торгов за день (в лотах): {sum(daily_volume.values())}")

            # Отрисовка графика
            plt.clf()
            plt.plot(self.times, self.prices, 'b-', label='Цена закрытия')
            plt.title(f"{self.symbol} - {dt.strftime('%d.%m.%Y')}")
            plt.xlabel("Время (МСК)")
            plt.ylabel("Цена, RUB")
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.pause(0.01)

        except Exception as e:
            logging.error(f"Ошибка обработки: {str(e)}")