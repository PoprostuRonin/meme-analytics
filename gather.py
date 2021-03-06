import schedule
import time
import configparser
import requests
import json
from elasticsearch import Elasticsearch
from elasticsearch import NotFoundError

print("Meme analytics running")

# Debug
debug = False

# Sites to scan
sites = []

# Limit page index, so our app won't index like 20000 pages (but it could)
limit_pages = 10

# Memes API url
api = 'http://memes.pr0gramista.pl:8080/'

# Elasticsearch connection string
es_conn = None
es_index = 'test-index'
es = None

# Whether we should stop scanning site on already indexed meme
stop_on_existing = False


def read_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    global sites, es_conn, api, limit_pages, es_index, debug, stop_on_existing
    sites = config.get('main', 'sites', fallback=sites).split(',')
    es_conn = config.get('main', 'es_conn', fallback=es_conn)
    es_index = config.get('main', 'es_index', fallback=es_index)
    limit_pages = config.getint('main', 'limit_pages', fallback=limit_pages)
    debug = config.getboolean('main', 'debug', fallback=debug)
    stop_on_existing = config.getboolean('main', 'stop_on_existing', fallback=stop_on_existing)

    if es_conn is not None:
        es_conn = json.loads(es_conn)
    api = config.get('main', 'api', fallback=api)


def print_config():
    print('Sites to scan: ' + str(sites))
    if stop_on_existing:
        print('Stop on exitsting is enabled')
    print('Memes API url: ' + api)
    if es_conn is not None:
        print('Elasticsearch connection url: ' + es_conn)


def is_new(meme):
    global es
    try:
        response = es.search(
            index=es_index,
            body={
                "query": {
                    "constant_score": {
                        "filter": {"match_phrase": {"url": meme['url']}}
                    }
                }
            })

        if debug:
            print(meme)
            print(response)

        if response['hits']['total'] > 0:
            return response['hits']['hits'][0]['_id']
        else:
            return None
    except NotFoundError:
        return None


def memes(site, max_page):
    page = "/" + site
    page_count = 0
    stop = False

    while stop is False:
        url = api + page
        page_count += 1

        data = requests.get(url).json()

        if 'memes' in data:
            for meme in data['memes']:
                yield meme
                # Set things for next iteration
                page = data['nextPage']

                if page_count > limit_pages:
                    stop = True
                    break
        else:
            print("Scanning ended too soon (no memes received)")
            break


def scan_site(site):
    # Counters
    memes_indexed = 0
    memes_new = 0

    for meme in memes(site, limit_pages):
        mid = is_new(meme)
        es.index(index=es_index, doc_type='meme', body=meme, id=mid)

        memes_indexed += 1
        if mid is None:
            memes_new += 1
        elif stop_on_existing:
            print(
            "Scanning {} stopped, because meme was already indexed and [stop_on_existing] is enabled".format(site))
            break

        if debug:
            print("Indexed {0} meme (id: {2}) with title: {1}".format(site, meme['title'], mid))
    print("Indexed {0} ({1} new) memes for site {2}".format(memes_indexed, memes_new, site))


def scan():
    print("Scanning...")
    for site in sites:
        scan_site(site)


read_config()
print_config()

es = Elasticsearch(hosts=es_conn)

scan()

print("Standby mode")
schedule.every(15).minutes.do(scan)

while True:
    schedule.run_pending()
    time.sleep(1)
