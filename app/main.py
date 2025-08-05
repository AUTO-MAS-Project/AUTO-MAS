#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import os
import sys
import ctypes

from utils import get_logger

logger = get_logger("主程序")


def is_admin() -> bool:
    """检查当前程序是否以管理员身份运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


# @logger.catch
def main():

    if is_admin():

        import asyncio
        import uvicorn
        from fastapi import FastAPI
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def lifespan(app: FastAPI):

            from core import Config, MainTimer

            await Config.init_config()
            main_timer = asyncio.create_task(MainTimer.second_task())

            yield

            main_timer.cancel()
            try:
                await main_timer
            except asyncio.CancelledError:
                logger.info("主业务定时器已关闭")

            logger.info("AUTO_MAA 后端程序关闭")
            logger.info("----------------END----------------")

        from fastapi.middleware.cors import CORSMiddleware
        from api import (
            info_router,
            scripts_router,
            plan_router,
            queue_router,
            setting_router,
        )

        app = FastAPI(
            title="AUTO_MAA",
            description="API for managing automation scripts, plans, and tasks",
            version="1.0.0",
            lifespan=lifespan,
        )

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # 允许所有域名跨域访问
            allow_credentials=True,
            allow_methods=["*"],  # 允许所有请求方法，如 GET、POST、PUT、DELETE
            allow_headers=["*"],  # 允许所有请求头
        )

        app.include_router(info_router)
        app.include_router(scripts_router)
        app.include_router(plan_router)
        app.include_router(queue_router)
        app.include_router(setting_router)

        uvicorn.run(app, host="0.0.0.0", port=8000)

    else:

        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, os.path.realpath(sys.argv[0]), None, 1
        )
        sys.exit(0)


if __name__ == "__main__":

    main()
