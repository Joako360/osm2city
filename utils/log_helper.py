import logging

def log_level_info_or_lower():
    return logging.getLogger().level <= logging.INFO


def log_level_debug_or_lower():
    return logging.getLogger().level <= logging.DEBUG
