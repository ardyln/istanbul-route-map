# make data   - download every İETT line and stop (İBB), each line's stop order (İETT), the minibüs/dolmuş data (İBB),
#               and the coastline and lakes (OpenStreetMap, via Overpass)
# make map    - compile the minibüs/dolmuş routes and draw the map (out/istanbul-route-map.svg)
# make images - the overview PNG and the 4×3 full-resolution tiles (needs: cd tools && npm install, and Google Chrome)
# make check  - measures every name and route tag as Chrome draws it and reports any that overlap
IBB := https://api.ibb.gov.tr/iett/UlasimAnaVeri/HatDurakGuzergah.asmx
DATA := https://data.ibb.gov.tr/dataset

data:
	mkdir -p data/lines data/dolmus
	./soap.sh $(IBB) GetHat_json "<HatKodu></HatKodu>" > data/hat.xml && sleep 10
	./soap.sh $(IBB) GetDurak_json "<DurakKodu></DurakKodu>" > data/durak.xml
	python3 unwrap.py data/hat.xml data/hat.json
	python3 unwrap.py data/durak.xml data/durak.json
	python3 fetch_orders.py
	cd data/dolmus && curl -sSO $(DATA)/07603812-6e3e-489f-96a0-2da9c3da3193/resource/ac77adc1-11ed-4f3e-a05d-136c9185e510/download/istanbul_taksidolmus_duraklari.geojson \
	  && curl -sSO $(DATA)/fc5f925a-0ee8-4e1f-a4e7-17ab272eac83/resource/1a1fdf1e-60c9-46a4-b169-ca51adcd9d6c/download/istanbul_taksidolmus_guzergahlari.geojson \
	  && curl -sSO $(DATA)/8dad4995-0071-44de-9b14-57288ec1de97/resource/9083216b-7afd-4eae-a242-cf5b09f748f4/download/istanbul_minibus_guzergahlari.geojson \
	  && curl -sSO $(DATA)/8b4391c0-e647-4635-aaf7-5baee24c6e81/resource/0d4fbb9f-cd5f-4005-aa57-6bb76db3fc58/download/istanbul_minibus_duraklari.geojson
	ln -sfn ../durak.json data/dolmus/iett_stops.json
	mkdir -p data/geo
	curl -sS -A "istanbul-route-map" -H "Accept: application/json" https://overpass-api.de/api/interpreter \
	  --data-urlencode 'data=[out:json][timeout:240];way[natural=coastline](40.70,27.90,41.62,30.00);out geom;' -o data/geo/coastline.json
	sleep 5
	curl -sS -A "istanbul-route-map" -H "Accept: application/json" https://overpass-api.de/api/interpreter \
	  --data-urlencode 'data=[out:json][timeout:240];(way[natural=water][water~"^(lake|reservoir|river|lagoon)$$"](40.70,27.90,41.62,30.00);relation[natural=water][water~"^(lake|reservoir|river|lagoon)$$"](40.70,27.90,41.62,30.00););out geom;' -o data/geo/water.json

map:
	python3 dolmus_compile.py data/dolmus data/dolmus.json data/dolmus_shapes.json
	mkdir -p out && python3 schematic.py out/istanbul-route-map.svg

images:
	tools/images.sh out/istanbul-route-map.svg out

check:
	node tools/check_overlaps.js out/istanbul-route-map.svg

.PHONY: data map images check
