import psutil


def memory_usage_mb():
    process = psutil.Process()
    return process.memory_info().rss / 1024 / 1024


def is_memory_high(limit_mb=1500):
    return memory_usage_mb() > limit_mb