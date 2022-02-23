import logging
import shutil
import sys
from logging import Logger

import jsonpickle


def safe_json_dump(fpath: str, obj: object) -> None:
    """
    Utility function used to avoid json file corruption in case of abrupt termination of the script.
    :param fpath: path where the json has to be saved
    :param obj: the content to be saved
    """
    safe_path = fpath + "_safe"
    with open(safe_path, "w") as f:
        js = jsonpickle.encode(obj, indent=4)
        f.write(js)
    shutil.move(safe_path, fpath)


def get_logger(name: str, level: int = logging.INFO) -> Logger:
    logger = Logger(name)
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('[%(asctime)s|%(name)s|%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


seconds_per_unit = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(string_duration: str):
    return int(string_duration[:-1]) * seconds_per_unit[string_duration[-1]]


def auto_str_and_repr(cls: type):
    def _values(self):
        return ", ".join([f"{key}={value}" for (key, value) in vars(self).items()])

    def __repr__(self):
        return f"{type(self).__name__}({_values(self)})"

    def __str__(self):
        return __repr__(self)

    cls.__repr__ = __repr__
    cls.__str__ = __str__
    return cls
