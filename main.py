import mockapi.get_cinema as cinema_api
def main():
    key = input("万达")
    places = cinema_api.get_place_list_by_key(key)
    print(f"找到 {len(places)} 个匹配的影院：")
    for place in places:
        print(f"影院名称: {place['name']}, 地址: {place['address']}")
if __name__ == "__main__":    
    main()