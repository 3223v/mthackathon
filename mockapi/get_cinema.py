import json
import os

HERE = os.path.dirname(__file__)
data_path = os.path.join(HERE, "mockdata", "cinema.json")
with open(data_path, 'r', encoding='utf-8') as f:
    cinema_data = json.load(f)

def get_place_list_by_key(key):
    result = []
    for place in cinema_data['data']:
        if key in place['name']:
            result.append(place)
    return result

