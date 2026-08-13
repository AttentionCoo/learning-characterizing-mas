import functools
import time
import logging
from typing import Callable, Type, Tuple, Any

logger = logging.getLogger(__name__)


def retry(
    max_retries: int = 2,
    delay: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    rate_limit_key: str = "RateQuota",
):
    """
    自动重试装饰器。

    对指定异常进行指数退避重试（网络抖动、超时、限流等临时性错误均可重试）；
    限流类错误（错误信息含 rate_limit_key）使用更保守的等待时间。
    重试耗尽后抛出最后一次异常。
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt >= max_retries:
                        raise
                    err_str = str(e)
                    wait = delay * (attempt + 1)
                    if rate_limit_key in err_str:
                        wait *= 2  # 限流退避更保守，避免触发更严格的配额限制
                    logger.warning(
                        f"重试 {func.__name__}: {type(e).__name__}，{wait:.1f}s 后重试 ({attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait)
            raise last_exc
        return wrapper
    return decorator


def timeit(func: Callable) -> Callable:
    """计时装饰器"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"{func.__name__} 执行耗时: {elapsed:.2f}s")
        return result
    return wrapper
