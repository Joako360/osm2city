"""
Module to query data from WikiData

https://wiki.openstreetmap.org/wiki/Key:wikidata?uselang=en-GB
https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/Wikidata_Query_Help
https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual#SPARQL_endpoint

E.g. https://www.wikidata.org/wiki/Q1425473

Population property: https://www.wikidata.org/wiki/Property:P1082

select * where {
  wd:Q1425473 wdt:P1082 ?o .
  }

"""

import json
import logging
import time

import requests


def query_population(entity_id: str) -> int:
    """Queries WikiData for population data of a given entity.
    Might raise all sorts of exceptions. In any case of problem the return value i < 0.
    Errors will be logged.
    """
    query = 'https://query.wikidata.org/sparql?query=SELECT%20*%20WHERE%20{wd:' + entity_id
    query += '%20wdt:P1082%20?o%20.}&format=json'
    status_code = 0
    reason = None
    error_value = -1

    # Currently there is a limit of 60 requests to WikiData -> throttle
    # See https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual#Query_limits
    time.sleep(1.0)
    try:
        r = requests.get(url=query, timeout=1.)
        status_code = r.status_code
        r.raise_for_status()
    except ConnectionError:
        logging.warning('Network connection error occurred in fetching data from WikiData')
        return error_value
    except requests.HTTPError:
        logging.warning('Response error in fetching data from WikiData: code = %i, reason = %s', status_code, reason)
        return error_value
    # We should be good to parse the content
    try:
        data = json.loads(r.content.decode())
        bindings = data['results']['bindings']
        value_dict = bindings[0]
        return int(value_dict['o']['value'])
    except (ValueError, KeyError):
        logging.warning('Error in interpreting data from WikiData with id=' + entity_id, exc_info=1)
        return error_value


if __name__ == '__main__':
    my_entity_id = 'Q1425473'
    print(query_population(my_entity_id))
