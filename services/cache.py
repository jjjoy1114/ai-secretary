"""아주 단순한 '잠깐 기억해 두기'(TTL 캐시).

같은 계산을 짧은 시간 안에 다시 요청하면 Firestore를 또 읽지 않고 기억해 둔 결과를 돌려줘요.
  * 기본 60초가 지나면 자동으로 잊어요 (CACHE_TTL_SECONDS 환경변수로 조절, 0이면 끔)
  * 데이터를 추가·수정·삭제하면 clear_cache()로 바로 잊어서, 화면 요약이 곧바로 바뀌어요
  * 서버 메모리에만 저장해요 → 서버가 다시 시작되면 비워져요 (서버가 1대인 이 과제 규모에 맞는 단순한 방식)
"""
import copy
import functools
import time

from config import CACHE_TTL_SECONDS

_store = {}  # (함수 이름, 인자) -> (저장 시각, 결과)


def ttl_cache(func):
    """결과를 CACHE_TTL_SECONDS 동안 기억해요. 결과가 비어 있으면(None) 기억하지 않아요."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if CACHE_TTL_SECONDS <= 0:
            return func(*args, **kwargs)
        key = (func.__qualname__, args, tuple(sorted(kwargs.items())))
        hit = _store.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_SECONDS:
            return copy.deepcopy(hit[1])      # 받은 쪽이 값을 고쳐도 기억해 둔 원본은 안전하게
        result = func(*args, **kwargs)
        if result is not None:
            _store[key] = (time.monotonic(), copy.deepcopy(result))
        return result
    return wrapper


def clear_cache():
    """기억해 둔 계산 결과를 모두 지워요 (데이터가 바뀌었을 때 호출)."""
    _store.clear()
