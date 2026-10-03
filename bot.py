# ==================== ЗАПУСК ====================
# Файл: bot.py
# Главный файл — запускает ОБА бота одновременно.
# Бот-предложка: @predlozhka_Tobolsk_bot
# Бот-наблюдатель: @eye_observer_bot

import asyncio

from predlozhka import predlozhka_bot, predlozhka_dp
from observer import observer_bot, observer_dp, obs_init_db


async def main():
    await obs_init_db()
    print("🤖 Предложка и Observer запущены")
    await asyncio.gather(
        predlozhka_dp.start_polling(predlozhka_bot),
        observer_dp.start_polling(observer_bot),
    )


if __name__ == "__main__":
    asyncio.run(main())