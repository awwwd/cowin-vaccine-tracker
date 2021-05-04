import sys
import logging
import os
import time
import requests
import yaml
from pathlib import Path
from collections import namedtuple
from datetime import timedelta, datetime
from http import HTTPStatus
from random import randint


def _dict_to_namedtuple(_object, name):
    """Converts a single level dict to namedtuple"""

    return namedtuple(name, _object.keys())(**_object)


def _dict_to_namedtuple_builder(dict_object: dict, *, name='Config'):
    """Recursively converts a dict to a namedtuple"""

    if isinstance(dict_object, dict):
        for key, val in dict_object.items():
            dict_object[key] = _dict_to_namedtuple_builder(val)
        return _dict_to_namedtuple(dict_object, name)
    elif isinstance(dict_object, list):
        return [_dict_to_namedtuple_builder(item) for item in dict_object]
    return dict_object


class Config:
    @staticmethod
    def load(config_file):
        LOGGER.info(f"Loading {config_file} as configuration")
        with open(config_file, 'r') as conf:
            _config = yaml.safe_load(conf)
            named_config = _dict_to_namedtuple_builder(_config)
            return named_config


def collect_flatten_schedules():
    schedules = set()
    for day in range(config.check_for_next_days):
        next_day = (datetime.today() + timedelta(day)).strftime("%d-%m-%Y")
        for each_pincode in config.pin_codes:
            params = {
                'pincode': each_pincode,
                'date': next_day
            }

            resp = requests.get(
                config.COWIN_PUBLIC_CALENDAR_API,
                params=params,
                timeout=5)
            if resp.status_code == HTTPStatus.OK:
                resp_json = resp.json()
                centers = resp_json.get('centers', [])
                LOGGER.debug(
                    f"Found {len(centers)} centers for pin {each_pincode} and date {next_day}")
                for center in centers:
                    center_meta = (center.get('name'), center.get(
                        'address'), center.get('block_name'), center.get('fee_type'))
                    sessions = center.get('sessions', [])
                    LOGGER.debug(
                        f"Found {len(sessions)} sessions for the above center")
                    for session in sessions:
                        session_meta = (session.get('date'), session.get(
                            'available_capacity'), session.get('min_age_limit'), session.get('vaccine'))
                        schedules.add((*center_meta, *session_meta))
            else:
                LOGGER.error(f"Could not able to connect to {config.COWIN_PUBLIC_CALENDAR_API}")
                time.sleep(randint(5, 10))

    return schedules


def main():
    schedules = collect_flatten_schedules()
    filtered_schedules = filter(
        lambda s: s[6] == config.minimum_age, schedules)
    for fs in filtered_schedules:
        LOGGER.info(
            f"Matched - Name: {fs[0]} - Address: {fs[1]} - Age Limit: {fs[6]} - Vaccine: {fs[-1]}")
        if fs[5] > 0:
            LOGGER.info(
                f">> BINGO: {fs[5]} vaccines available for above on {fs[4]} <<")

if __name__ == '__main__':
    cwd = os.path.dirname(os.path.abspath(__file__))
    config_file = Path(f"{cwd}/config.yaml")
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
    LOGGER = logging.getLogger()
    if not config_file.exists() and not config_file.is_file():
        LOGGER.error(f"{config_file} missing from cwd.")
        exit(-1)
    config = Config.load(config_file)
    LOGGER.setLevel(config.log_level)
    while True:
        try:
            main()
            time.sleep(config.polling_interval)
        except KeyboardInterrupt:
            LOGGER.info("Exiting...")
            exit(0)
